"""
Shared async fixtures for Piratex.ai backend tests.

Usage:
    async def test_something(client, db_session, make_user):
        user = await make_user(tier="PRO")
        resp = await client.get("/api/users/me", headers=auth_headers(user))
        assert resp.status_code == 200
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.rate_limit import limiter
from app.database import Base, get_db
from app.main import app

# Disable rate limiting in tests
limiter.enabled = False

# Prevent tests from sending real Telegram messages
_tg_mock = patch("app.services.telegram.send_telegram_message", new_callable=AsyncMock)
_tg_mock.start()

# In-memory SQLite for tests — no external DB needed
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest_asyncio.fixture
async def async_engine():
    """Create a fresh test database for each test."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    """Async DB session with automatic rollback after each test."""
    session_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    """Async HTTP client with test DB injected into FastAPI."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
def make_user(db_session):
    """Factory fixture for creating test users."""
    from app.models.user import User

    async def _make(tier: str = "FREE", email: str | None = None, **kwargs):
        user = User(
            id=str(uuid.uuid4()),
            tier=tier,
            email=email or f"test-{uuid.uuid4().hex[:8]}@test.com",
            **kwargs,
        )
        db_session.add(user)
        await db_session.flush()
        return user

    return _make


def auth_headers(user) -> dict:
    """Generate JWT auth headers for a test user."""
    from datetime import datetime, timedelta

    from app.config import settings
    from jose import jwt

    token = jwt.encode(
        {"sub": user.id, "tier": user.tier, "v": getattr(user, "token_version", 1) or 1, "exp": datetime.utcnow() + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}
