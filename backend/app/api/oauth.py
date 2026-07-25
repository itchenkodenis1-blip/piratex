import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import create_access_token, get_current_user_from_cookie
from app.core.identity import find_or_create_user
from app.core.oauth_providers import OAUTH_PROVIDERS, get_provider
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.identity import OAuthState
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

OAUTH_STATE_TTL_MINUTES = 10


# ---------------------------------------------------------------------------
# List providers
# ---------------------------------------------------------------------------


@router.get("/providers")
async def list_providers():
    """Return list of configured OAuth providers."""
    return {
        "providers": [
            {"name": name, "configured": provider.is_configured()}
            for name, provider in OAUTH_PROVIDERS.items()
        ]
    }


# ---------------------------------------------------------------------------
# Start OAuth flow
# ---------------------------------------------------------------------------


@router.get("/{provider}/start")
@limiter.limit("10/minute")
async def oauth_start(
    request: Request,
    provider: str,
    redirect_url: str | None = None,
    origin: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Initiate OAuth flow — return the provider's authorize URL."""
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown OAuth provider")

    oauth_provider = get_provider(provider)
    if not oauth_provider.is_configured():
        raise HTTPException(status_code=503, detail="OAuth provider not configured")

    # Use origin from frontend (most reliable behind proxy),
    # but validate against app_url to prevent open-redirect token theft.
    if origin:
        from urllib.parse import urlparse
        allowed_host = urlparse(settings.app_url).netloc
        origin_host = urlparse(origin).netloc
        base_url = origin if origin_host == allowed_host else settings.app_url
    else:
        base_url = settings.app_url

    # Try to get ghost user from cookie (same pattern as telegram-code)
    ghost = await get_current_user_from_cookie(request, db)
    ghost_user_id = ghost.id if ghost and ghost.is_anonymous else None

    state = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=OAUTH_STATE_TTL_MINUTES)

    # Sanitize frontend redirect: must be a relative path starting with /
    # Block // (protocol-relative URLs that browsers may treat as absolute)
    frontend_path = (
        redirect_url
        if redirect_url and redirect_url.startswith("/") and not redirect_url.startswith("//")
        else None
    )

    oauth_state = OAuthState(
        state=state,
        provider=provider,
        ghost_user_id=ghost_user_id,
        redirect_url=base_url,
        frontend_redirect=frontend_path,
        expires_at=expires_at,
    )
    db.add(oauth_state)
    await db.commit()

    authorize_url = oauth_provider.build_authorize_url(state, base_url=base_url)
    return {"authorize_url": authorize_url}


# ---------------------------------------------------------------------------
# OAuth callback
# ---------------------------------------------------------------------------


@router.get("/{provider}/callback")
@limiter.limit("20/minute")
async def oauth_callback(
    request: Request,
    provider: str,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback — exchange code, create/find user, redirect."""
    provider_name = provider

    try:
        if provider_name not in OAUTH_PROVIDERS:
            raise HTTPException(status_code=404, detail="Unknown OAuth provider")

        oauth_provider = get_provider(provider_name)

        # Look up and validate OAuthState
        result = await db.execute(
            select(OAuthState).where(OAuthState.state == state)
        )
        oauth_state = result.scalar_one_or_none()

        if not oauth_state:
            raise HTTPException(status_code=400, detail="Invalid OAuth state")

        if datetime.utcnow() > oauth_state.expires_at:
            await db.delete(oauth_state)
            await db.commit()
            raise HTTPException(status_code=400, detail="OAuth state expired")

        # Extract data before deleting state
        ghost_user_id = oauth_state.ghost_user_id
        base_url = oauth_state.redirect_url or settings.app_url
        frontend_redirect = oauth_state.frontend_redirect

        # Delete used state
        await db.delete(oauth_state)
        await db.flush()

        # Exchange code for tokens (must use same redirect_uri as authorize)
        tokens = await oauth_provider.exchange_code(code, base_url=base_url)
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")

        if not access_token:
            raise HTTPException(status_code=502, detail="No access token from provider")

        # Get user info from provider
        user_info = await oauth_provider.get_user_info(access_token)

        # Load ghost user if present
        ghost_user = None
        if ghost_user_id:
            ghost_result = await db.execute(
                select(User).where(
                    User.id == ghost_user_id,
                    User.is_anonymous == True,  # noqa: E712
                )
            )
            ghost_user = ghost_result.scalar_one_or_none()

        # Find or create user via identity system
        user, identity, is_new = await find_or_create_user(
            db,
            provider=user_info.provider,
            provider_user_id=user_info.provider_user_id,
            email=user_info.email,
            display_name=user_info.display_name,
            avatar_url=user_info.avatar_url,
            ghost_user=ghost_user,
            raw_profile=user_info.raw_profile,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        if is_new:
            user.auth_provider = provider_name

        await db.commit()

        # Generate JWT
        jwt_token = create_access_token(user.id, user.token_version or 1)

        # Always redirect to /auth/callback with token;
        # pass the original frontend path so the frontend can navigate there after auth.
        callback_params: dict[str, str] = {"token": jwt_token}
        if frontend_redirect:
            callback_params["redirect"] = frontend_redirect
        callback_url = f"{base_url}/auth/callback?{urlencode(callback_params)}"

        return RedirectResponse(url=callback_url)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("OAuth callback failed for provider=%s: %s", provider_name, exc)
        # Use base_url if available, otherwise fall back to request origin
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        err_base = f"{scheme}://{host}"
        error_url = f"{err_base}/auth/error?provider={provider_name}&detail=authentication_failed"
        return RedirectResponse(url=error_url)
