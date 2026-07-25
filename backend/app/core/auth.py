from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

AUTH_COOKIE_NAME = "piratex_auth"


def set_auth_cookie(response: Response, token: str) -> None:
    """Set httpOnly JWT cookie on the response."""
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not settings.debug,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
        path="/",
    )


def create_access_token(user_id: str, token_version: int = 1) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire, "v": token_version}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
            )
        return user_id
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )


def _extract_jwt(request: Request) -> str | None:
    """Extract JWT from Authorization header or httpOnly cookie."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get(AUTH_COOKIE_NAME)


def _extract_token_version(token: str) -> int | None:
    """Extract token version from JWT without raising on error."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload.get("v")
    except JWTError:
        return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_jwt(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    user_id = decode_token(token)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    # Validate token version (revocation check)
    # Old tokens without "v" field are treated as v=1 (backward compatible)
    token_version = _extract_token_version(token) or 1
    if token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked"
        )
    return user


async def get_current_user_from_cookie(
    request: Request, db: AsyncSession,
) -> User | None:
    """Find ghost user by cookie. None if no cookie or user not found."""
    session_token = request.cookies.get("piratex_session")
    if not session_token:
        return None
    result = await db.execute(
        select(User).where(User.session_token == session_token)
    )
    return result.scalar_one_or_none()


async def get_admin_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require authenticated user with admin privileges."""
    user = await get_current_user(request, db)
    admin_emails = [e.strip() for e in settings.admin_emails.split(",") if e.strip()]
    admin_tg_ids = [t.strip() for t in settings.admin_telegram_ids.split(",") if t.strip()]
    is_admin = (
        (user.email and user.email in admin_emails)
        or (user.telegram_user_id and user.telegram_user_id in admin_tg_ids)
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def get_optional_user(
    request: Request, db: AsyncSession = Depends(get_db),
) -> User | None:
    """JWT (header or cookie) -> session cookie -> None. Never raises 401."""
    # 1. Try JWT from Authorization header or httpOnly auth cookie
    token = _extract_jwt(request)
    if token:
        try:
            payload = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if user:
                    # Validate token version (old tokens without "v" = 1)
                    token_ver = payload.get("v") or 1
                    if token_ver != user.token_version:
                        return None  # Token revoked, treat as unauthenticated
                    return user
        except JWTError:
            pass

    # 2. Try session cookie (ghost user)
    return await get_current_user_from_cookie(request, db)
