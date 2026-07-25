import secrets

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import get_optional_user
from app.database import get_db
from app.models.user import User


async def ensure_user(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Guarantee a user exists. JWT -> cookie -> create ghost."""
    user = await get_optional_user(request, db)
    if user:
        return user

    # Create ghost user
    session_token = secrets.token_urlsafe(48)
    user = User(
        is_anonymous=True,
        tier="ANONYMOUS",
        session_token=session_token,
        name=f"Guest-{secrets.token_hex(3)}",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    response.set_cookie(
        "piratex_session",
        session_token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=90 * 24 * 3600,
    )

    return user
