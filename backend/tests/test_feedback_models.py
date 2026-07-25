"""Tests for feedback models: ScriptRating, SupportConversation, SupportMessage."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.feedback import ScriptRating, SupportConversation, SupportMessage
from app.models.job import Job, JobStatus
from app.models.user import User


@pytest_asyncio.fixture
async def user(db_session):
    u = User(
        id=str(uuid.uuid4()),
        tier="FREE",
        email=f"test-{uuid.uuid4().hex[:8]}@test.com",
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def admin_user(db_session):
    u = User(
        id=str(uuid.uuid4()),
        tier="UNLIMITED",
        email="admin@piratex.ai",
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def job(db_session, user):
    j = Job(
        id=str(uuid.uuid4()),
        user_id=user.id,
        url="https://instagram.com/reel/test",
        status=JobStatus.COMPLETED,
    )
    db_session.add(j)
    await db_session.flush()
    return j


# --- ScriptRating tests ---


@pytest.mark.asyncio
async def test_create_script_rating(db_session, user, job):
    rating = ScriptRating(
        user_id=user.id,
        job_id=job.id,
        rating=4,
        comment="Good but could be better",
    )
    db_session.add(rating)
    await db_session.flush()

    result = await db_session.execute(
        select(ScriptRating).where(ScriptRating.job_id == job.id)
    )
    saved = result.scalar_one()
    assert saved.rating == 4
    assert saved.comment == "Good but could be better"
    assert saved.user_id == user.id


@pytest.mark.asyncio
async def test_script_rating_without_comment(db_session, user, job):
    rating = ScriptRating(
        user_id=user.id,
        job_id=job.id,
        rating=5,
    )
    db_session.add(rating)
    await db_session.flush()

    result = await db_session.execute(
        select(ScriptRating).where(ScriptRating.job_id == job.id)
    )
    saved = result.scalar_one()
    assert saved.rating == 5
    assert saved.comment is None


@pytest.mark.asyncio
async def test_script_rating_unique_constraint(db_session, user, job):
    """One rating per user per job — second insert should fail."""
    r1 = ScriptRating(user_id=user.id, job_id=job.id, rating=3)
    db_session.add(r1)
    await db_session.flush()

    r2 = ScriptRating(user_id=user.id, job_id=job.id, rating=5)
    db_session.add(r2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.skip(reason="CASCADE DELETE is DB-level (PostgreSQL); SQLite test DB doesn't enforce FK cascades via ORM delete")
@pytest.mark.asyncio
async def test_script_rating_cascade_delete_user(db_session, user, job):
    """Rating should be deleted when user is deleted."""
    rating = ScriptRating(user_id=user.id, job_id=job.id, rating=4)
    db_session.add(rating)
    await db_session.flush()

    await db_session.delete(user)
    await db_session.flush()

    result = await db_session.execute(select(ScriptRating))
    assert result.scalars().all() == []


@pytest.mark.skip(reason="CASCADE DELETE is DB-level (PostgreSQL); SQLite test DB doesn't enforce FK cascades via ORM delete")
@pytest.mark.asyncio
async def test_script_rating_cascade_delete_job(db_session, user, job):
    """Rating should be deleted when job is deleted."""
    rating = ScriptRating(user_id=user.id, job_id=job.id, rating=4)
    db_session.add(rating)
    await db_session.flush()

    await db_session.delete(job)
    await db_session.flush()

    result = await db_session.execute(select(ScriptRating))
    assert result.scalars().all() == []


# --- SupportConversation tests ---


@pytest.mark.asyncio
async def test_create_support_conversation(db_session, user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    result = await db_session.execute(
        select(SupportConversation).where(SupportConversation.user_id == user.id)
    )
    saved = result.scalar_one()
    assert saved.status == "open"
    assert saved.unread_admin == 0
    assert saved.unread_user == 0


@pytest.mark.asyncio
async def test_support_conversation_unique_per_user(db_session, user):
    """Only one conversation per user."""
    c1 = SupportConversation(user_id=user.id)
    db_session.add(c1)
    await db_session.flush()

    c2 = SupportConversation(user_id=user.id)
    db_session.add(c2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.skip(reason="CASCADE DELETE is DB-level (PostgreSQL); SQLite test DB doesn't enforce FK cascades via ORM delete")
@pytest.mark.asyncio
async def test_support_conversation_cascade_delete(db_session, user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    await db_session.delete(user)
    await db_session.flush()

    result = await db_session.execute(select(SupportConversation))
    assert result.scalars().all() == []


# --- SupportMessage tests ---


@pytest.mark.asyncio
async def test_create_support_message(db_session, user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="user",
        sender_id=user.id,
        text="Hello, I need help!",
    )
    db_session.add(msg)
    await db_session.flush()

    result = await db_session.execute(
        select(SupportMessage).where(SupportMessage.conversation_id == conv.id)
    )
    saved = result.scalar_one()
    assert saved.text == "Hello, I need help!"
    assert saved.sender_type == "user"
    assert saved.image_key is None
    assert saved.read_at is None


@pytest.mark.asyncio
async def test_support_message_with_image(db_session, user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="user",
        sender_id=user.id,
        text=None,
        image_key="support/abc123.png",
    )
    db_session.add(msg)
    await db_session.flush()

    result = await db_session.execute(
        select(SupportMessage).where(SupportMessage.conversation_id == conv.id)
    )
    saved = result.scalar_one()
    assert saved.text is None
    assert saved.image_key == "support/abc123.png"


@pytest.mark.asyncio
async def test_support_message_admin_reply(db_session, user, admin_user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="admin",
        sender_id=admin_user.id,
        text="Hi! How can I help?",
    )
    db_session.add(msg)
    await db_session.flush()

    result = await db_session.execute(
        select(SupportMessage).where(SupportMessage.conversation_id == conv.id)
    )
    saved = result.scalar_one()
    assert saved.sender_type == "admin"
    assert saved.sender_id == admin_user.id


@pytest.mark.skip(reason="CASCADE DELETE is DB-level (PostgreSQL); SQLite test DB doesn't enforce FK cascades via ORM delete")
@pytest.mark.asyncio
async def test_support_messages_cascade_delete_conversation(db_session, user):
    """Messages should be deleted when conversation is deleted."""
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="user",
        sender_id=user.id,
        text="Test message",
    )
    db_session.add(msg)
    await db_session.flush()

    await db_session.delete(conv)
    await db_session.flush()

    result = await db_session.execute(select(SupportMessage))
    assert result.scalars().all() == []
