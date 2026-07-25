import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import create_access_token, get_current_user_from_cookie, set_auth_cookie
from app.core.identity import find_or_create_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.services.email_sender import send_magic_link_email
from app.models.identity import AuthIdentity, MagicLinkCode
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


class MagicLinkRequest(BaseModel):
    email: EmailStr
    lang: str = "en"
    brand: str = "Piratex.ai"


# ---------------------------------------------------------------------------
# Send magic link
# ---------------------------------------------------------------------------


@router.post("/send")
@limiter.limit("3/minute")
async def send_magic_link(
    request: Request,
    body: MagicLinkRequest,
    db: AsyncSession = Depends(get_db),
):
    """Generate a magic-link code and (TODO) send it via email."""
    ghost = await get_current_user_from_cookie(request, db)
    ghost_user_id = ghost.id if ghost and ghost.is_anonymous else None

    # Invalidate old unconfirmed codes for this email
    await db.execute(
        delete(MagicLinkCode).where(
            MagicLinkCode.email == body.email,
            MagicLinkCode.confirmed == False,  # noqa: E712
        )
    )

    code = secrets.token_urlsafe(32)
    pin = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.utcnow() + timedelta(minutes=settings.magic_link_ttl_minutes)

    magic_code = MagicLinkCode(
        email=body.email,
        code=code,
        pin=pin,
        ghost_user_id=ghost_user_id,
        expires_at=expires_at,
    )
    db.add(magic_code)
    await db.commit()

    magic_link_url = f"{settings.app_url}/api/auth/magic-link/verify?code={code}"

    sent = await send_magic_link_email(body.email, magic_link_url, pin=pin, lang=body.lang, brand=body.brand)
    if not sent:
        raise HTTPException(status_code=502, detail="Failed to send email")

    result = {
        "sent": True,
        "expires_in_minutes": settings.magic_link_ttl_minutes,
    }

    if settings.debug:
        result["link"] = magic_link_url

    return result


# ---------------------------------------------------------------------------
# Verify magic link code (user clicks the email link)
# ---------------------------------------------------------------------------


@router.get("/verify")
@limiter.limit("10/minute")
async def verify_magic_link(
    request: Request,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """Verify a magic-link code and authenticate the user."""
    result = await db.execute(
        select(MagicLinkCode).where(MagicLinkCode.code == code)
    )
    magic_code = result.scalar_one_or_none()

    if not magic_code:
        return RedirectResponse(
            url=f"{settings.app_url}/auth/callback?error=not_found",
            status_code=302,
        )

    if datetime.utcnow() > magic_code.expires_at:
        return RedirectResponse(
            url=f"{settings.app_url}/auth/callback?error=expired",
            status_code=302,
        )

    if magic_code.confirmed:
        return RedirectResponse(
            url=f"{settings.app_url}/auth/callback?error=already_used",
            status_code=302,
        )

    # Load ghost user if present
    ghost = None
    if magic_code.ghost_user_id:
        ghost_result = await db.execute(
            select(User).where(
                User.id == magic_code.ghost_user_id,
                User.is_anonymous == True,  # noqa: E712
            )
        )
        ghost = ghost_result.scalar_one_or_none()

    user, identity, is_new = await find_or_create_user(
        db,
        provider="email",
        provider_user_id=magic_code.email,
        email=magic_code.email,
        ghost_user=ghost,
    )

    user.email_verified = True
    user.auth_provider = user.auth_provider or "email"

    magic_code.confirmed = True
    await db.commit()

    token = create_access_token(user.id, user.token_version or 1)

    logger.info("[magic-link] verified code=%s… user=%s", code[:8], user.id)

    # Use fragment (#) instead of query (?) so token never reaches server logs/Referer
    return RedirectResponse(
        url=f"{settings.app_url}/auth/callback#token={token}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Verify by PIN code (user types 6-digit code from email)
# ---------------------------------------------------------------------------


MAX_PIN_ATTEMPTS = 5


class PinVerifyRequest(BaseModel):
    email: EmailStr
    pin: str

    @field_validator("pin")
    @classmethod
    def pin_must_be_6_digits(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("PIN must be exactly 6 digits")
        return v


@router.post("/verify-pin")
@limiter.limit("10/minute")
async def verify_magic_link_pin(
    request: Request,
    response: Response,
    body: PinVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify a magic-link by 6-digit PIN code entered manually."""
    # Find the latest unconfirmed, non-expired code for this email
    result = await db.execute(
        select(MagicLinkCode).where(
            MagicLinkCode.email == body.email,
            MagicLinkCode.confirmed == False,  # noqa: E712
            MagicLinkCode.expires_at > datetime.utcnow(),
        ).order_by(MagicLinkCode.created_at.desc()).limit(1)
    )
    magic_code = result.scalar_one_or_none()

    if not magic_code:
        raise HTTPException(status_code=400, detail="Invalid code")

    # Brute-force protection: increment attempts before checking PIN
    magic_code.attempts = (magic_code.attempts or 0) + 1
    if magic_code.attempts > MAX_PIN_ATTEMPTS:
        magic_code.confirmed = True  # burn the code
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many attempts, request a new code")

    if magic_code.pin != body.pin:
        await db.commit()  # persist incremented attempt count
        raise HTTPException(status_code=400, detail="Invalid code")

    # Atomically mark as confirmed to prevent race condition
    confirm_result = await db.execute(
        update(MagicLinkCode)
        .where(
            MagicLinkCode.id == magic_code.id,
            MagicLinkCode.confirmed == False,  # noqa: E712
        )
        .values(confirmed=True)
        .returning(MagicLinkCode.id)
    )
    if not confirm_result.scalar_one_or_none():
        # Another request already confirmed this code
        raise HTTPException(status_code=400, detail="Invalid code")

    # Load ghost user if present
    ghost = None
    if magic_code.ghost_user_id:
        ghost_result = await db.execute(
            select(User).where(
                User.id == magic_code.ghost_user_id,
                User.is_anonymous == True,  # noqa: E712
            )
        )
        ghost = ghost_result.scalar_one_or_none()

    user, identity, is_new = await find_or_create_user(
        db,
        provider="email",
        provider_user_id=magic_code.email,
        email=magic_code.email,
        ghost_user=ghost,
    )

    user.email_verified = True
    user.auth_provider = user.auth_provider or "email"
    await db.commit()

    token = create_access_token(user.id, user.token_version or 1)
    set_auth_cookie(response, token)

    logger.info("[magic-link] verified pin for email=%s user=%s", magic_code.email, user.id)

    return {"verified": True, "token": token}


# ---------------------------------------------------------------------------
# Poll for confirmation (frontend polls while user clicks email)
# ---------------------------------------------------------------------------


@router.get("/check")
@limiter.limit("30/minute")
async def check_magic_link(
    request: Request,
    response: Response,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """Poll to check if magic-link code has been confirmed."""
    result = await db.execute(
        select(MagicLinkCode).where(MagicLinkCode.code == code)
    )
    magic_code = result.scalar_one_or_none()

    if not magic_code:
        raise HTTPException(status_code=404, detail="Code not found")

    expired = datetime.utcnow() > magic_code.expires_at

    if magic_code.confirmed:
        # Look up the user via their email identity
        identity_result = await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "email",
                AuthIdentity.provider_user_id == magic_code.email,
            )
        )
        identity = identity_result.scalar_one_or_none()
        if identity:
            user_result = await db.execute(select(User).where(User.id == identity.user_id))
            check_user = user_result.scalar_one_or_none()
            token = create_access_token(identity.user_id, check_user.token_version or 1 if check_user else 1)
            set_auth_cookie(response, token)
            return {"confirmed": True, "expired": False, "token": token}
        # Identity was confirmed but user record is missing — treat as not confirmed
        return {"confirmed": False, "expired": expired}

    return {"confirmed": False, "expired": expired}
