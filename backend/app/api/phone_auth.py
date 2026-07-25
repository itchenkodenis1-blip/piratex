import logging
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import create_access_token, get_current_user_from_cookie, set_auth_cookie
from app.core.identity import find_or_create_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.services.sms import send_sms_code
from app.models.identity import PhoneAuthCode
from app.models.user import User
from app.schemas.auth import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter()

PHONE_RE = re.compile(r"^\+\d{10,15}$")


class PhoneSendRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not PHONE_RE.match(v):
            raise ValueError("Phone must start with + followed by 10-15 digits")
        return v


class PhoneVerifyRequest(BaseModel):
    phone: str
    code: str


@router.post("/send-code")
@limiter.limit("3/minute")
async def send_phone_code(
    request: Request,
    body: PhoneSendRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a 6-digit SMS verification code to the given phone number."""
    ghost = await get_current_user_from_cookie(request, db)
    ghost_user_id = ghost.id if ghost and ghost.is_anonymous else None

    # Invalidate old unconfirmed codes for this phone
    await db.execute(
        delete(PhoneAuthCode).where(
            PhoneAuthCode.phone == body.phone,
            PhoneAuthCode.confirmed == False,  # noqa: E712
        )
    )

    code = str(secrets.randbelow(900000) + 100000)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.phone_code_ttl_minutes)

    phone_code = PhoneAuthCode(
        phone=body.phone,
        code=code,
        ghost_user_id=ghost_user_id,
        expires_at=expires_at,
    )
    db.add(phone_code)
    await db.commit()

    await send_sms_code(body.phone, code)

    result = {"sent": True, "expires_in_minutes": settings.phone_code_ttl_minutes}
    if settings.debug:
        result["code"] = code
    return result


@router.post("/verify")
@limiter.limit("10/minute")
async def verify_phone_code(
    request: Request,
    response: Response,
    body: PhoneVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify the SMS code and authenticate the user."""
    result = await db.execute(
        select(PhoneAuthCode)
        .where(
            PhoneAuthCode.phone == body.phone,
            PhoneAuthCode.confirmed == False,  # noqa: E712
        )
        .order_by(PhoneAuthCode.created_at.desc())
        .limit(1)
    )
    phone_code = result.scalar_one_or_none()

    if not phone_code:
        raise HTTPException(status_code=404, detail="Code not found")

    if datetime.utcnow() > phone_code.expires_at:
        raise HTTPException(
            status_code=410,
            detail={"verified": False, "expired": True},
        )

    if phone_code.attempts >= settings.phone_code_max_attempts:
        raise HTTPException(
            status_code=429,
            detail={"verified": False, "too_many_attempts": True},
        )

    phone_code.attempts += 1

    if phone_code.code != body.code:
        await db.commit()
        remaining = settings.phone_code_max_attempts - phone_code.attempts
        return {"verified": False, "attempts_remaining": remaining}

    # Code matches — authenticate
    ghost = None
    if phone_code.ghost_user_id:
        ghost_result = await db.execute(
            select(User).where(User.id == phone_code.ghost_user_id)
        )
        ghost = ghost_result.scalar_one_or_none()

    user, identity, is_new = await find_or_create_user(
        db,
        provider="phone",
        provider_user_id=phone_code.phone,
        ghost_user=ghost,
    )
    user.auth_provider = user.auth_provider or "phone"

    phone_code.confirmed = True
    await db.commit()

    token = create_access_token(user.id, user.token_version or 1)
    set_auth_cookie(response, token)

    return {
        "verified": True,
        "token": token,
        "user": UserResponse.model_validate(user).model_dump(),
    }
