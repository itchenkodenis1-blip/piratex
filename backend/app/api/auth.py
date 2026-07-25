import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.anonymous import ensure_user
from app.core.rate_limit import limiter
from app.core.auth import create_access_token, get_current_user_from_cookie, set_auth_cookie
from app.database import get_db
from app.models.identity import AuthIdentity
from app.models.user import TelegramAuthCode, User
from app.schemas.auth import UserResponse
from app.services.usage import check_can_create_analysis

router = APIRouter()

AUTH_CODE_TTL_MINUTES = 10


@router.get("/me")
async def get_me(
    request: Request,
    response: Response,
    user: User = Depends(ensure_user),
    db: AsyncSession = Depends(get_db),
):
    # Sync httpOnly auth cookie from JWT header (needed for <img> tag requests)
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        set_auth_cookie(response, auth_header[7:])

    _, used, limit, _ = await check_can_create_analysis(db, user, enforce=False)
    admin_emails = [e.strip() for e in settings.admin_emails.split(",") if e.strip()]
    admin_tg_ids = [t.strip() for t in settings.admin_telegram_ids.split(",") if t.strip()]
    is_admin = bool(
        (user.email and user.email in admin_emails)
        or (user.telegram_user_id and user.telegram_user_id in admin_tg_ids)
    )

    # Fetch linked auth providers
    identity_rows = await db.execute(
        select(AuthIdentity.provider).where(AuthIdentity.user_id == user.id)
    )
    auth_providers = [row[0] for row in identity_rows.fetchall()]

    # Fetch subscription status for in-app banners (past_due warning)
    from app.models.subscription import Subscription
    sub_result = await db.execute(
        select(Subscription.status).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["active", "past_due", "cancelled"]),
        ).order_by(Subscription.updated_at.desc().nulls_last()).limit(1)
    )
    subscription_status = sub_result.scalar_one_or_none()

    user_data = UserResponse.model_validate(user).model_dump()
    user_data["auth_providers"] = auth_providers
    resp: dict = {
        "user": {**user_data, "is_admin": is_admin, "subscription_status": subscription_status},
        "usage": {"used": used, "limit": limit},
    }

    # Issue JWT for anonymous users so WebSocket can connect
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer ") and user.is_anonymous:
        token = create_access_token(user.id, user.token_version or 1)
        resp["token"] = token
        set_auth_cookie(response, token)

    return resp


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Revoke all tokens and clear auth cookies."""
    from app.core.auth import get_optional_user
    user = await get_optional_user(request, db)
    if user and not user.is_anonymous:
        user.token_version = (user.token_version or 1) + 1
        await db.commit()
    response.delete_cookie("piratex_auth", path="/")
    response.delete_cookie("piratex_session", path="/")
    return {"ok": True}


@router.post("/telegram-code")
@limiter.limit("5/minute")
async def create_telegram_code(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate a one-time auth code for Telegram deep link login."""
    ghost = await get_current_user_from_cookie(request, db)
    ghost_user_id = ghost.id if ghost and ghost.is_anonymous else None

    # Invalidate old unconfirmed codes for this ghost
    if ghost_user_id:
        await db.execute(
            delete(TelegramAuthCode).where(
                TelegramAuthCode.ghost_user_id == ghost_user_id,
                TelegramAuthCode.confirmed == False,  # noqa: E712
            )
        )

    code = secrets.token_urlsafe(12)
    expires_at = datetime.utcnow() + timedelta(minutes=AUTH_CODE_TTL_MINUTES)

    auth_code = TelegramAuthCode(
        code=code,
        ghost_user_id=ghost_user_id,
        expires_at=expires_at,
    )
    db.add(auth_code)
    await db.commit()

    bot_name = settings.telegram_bot_name
    deep_link = f"https://t.me/{bot_name}?start={code}"

    return {
        "code": code,
        "deep_link": deep_link,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/telegram-check")
@limiter.limit("30/minute")
async def check_telegram_code(
    request: Request,
    response: Response,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """Poll to check if Telegram auth code has been confirmed."""
    result = await db.execute(
        select(TelegramAuthCode).where(TelegramAuthCode.code == code)
    )
    auth_code = result.scalar_one_or_none()

    if not auth_code:
        raise HTTPException(status_code=404, detail="Code not found")

    if datetime.utcnow() > auth_code.expires_at:
        return {"confirmed": False, "expired": True}

    if auth_code.confirmed and auth_code.token and auth_code.confirmed_user_id:
        user_result = await db.execute(
            select(User).where(User.id == auth_code.confirmed_user_id)
        )
        user = user_result.scalar_one_or_none()
        set_auth_cookie(response, auth_code.token)
        return {
            "confirmed": True,
            "token": auth_code.token,
            "user": UserResponse.model_validate(user).model_dump() if user else None,
        }

    return {"confirmed": False, "expired": False}
