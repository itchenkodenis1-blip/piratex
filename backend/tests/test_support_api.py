"""Tests for support chat API endpoints."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.feedback import SupportConversation, SupportMessage
from app.models.subscription import ConsentLog
from app.models.user import User
from tests.conftest import auth_headers


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
async def admin_user(db_session, monkeypatch):
    """Create an admin user and ensure settings.admin_emails includes them."""
    email = "admin@piratex.ai"
    from app.config import settings
    monkeypatch.setattr(settings, "admin_emails", email)
    u = User(
        id=str(uuid.uuid4()),
        tier="UNLIMITED",
        email=email,
    )
    db_session.add(u)
    await db_session.flush()
    return u


# --- GET /api/support/conversation ---


@pytest.mark.asyncio
async def test_get_conversation_empty(client, user):
    resp = await client.get(
        "/api/support/conversation",
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == ""
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_get_conversation_with_messages(client, db_session, user):
    # Create conversation and message
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="user",
        sender_id=user.id,
        text="Help me!",
    )
    db_session.add(msg)
    await db_session.flush()

    resp = await client.get(
        "/api/support/conversation",
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == conv.id
    assert len(data["messages"]) == 1
    assert data["messages"][0]["text"] == "Help me!"


# --- POST /api/support/messages ---


@pytest.mark.asyncio
async def test_send_first_message_creates_conversation(client, db_session, user):
    resp = await client.post(
        "/api/support/messages",
        json={"text": "Hello support!"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Hello support!"
    assert data["sender_type"] == "user"

    # Conversation should exist
    result = await db_session.execute(
        select(SupportConversation).where(SupportConversation.user_id == user.id)
    )
    conv = result.scalar_one()
    assert conv.status == "open"
    assert conv.unread_admin == 1


@pytest.mark.asyncio
async def test_send_message_logs_consent_on_first(client, db_session, user):
    await client.post(
        "/api/support/messages",
        json={"text": "First message"},
        headers=auth_headers(user),
    )

    result = await db_session.execute(
        select(ConsentLog).where(
            ConsentLog.user_id == user.id,
            ConsentLog.consent_type == "support_chat_consent",
        )
    )
    consent = result.scalar_one_or_none()
    assert consent is not None
    assert consent.action == "granted"


@pytest.mark.asyncio
async def test_send_second_message_no_duplicate_consent(client, db_session, user):
    # First message
    await client.post(
        "/api/support/messages",
        json={"text": "First"},
        headers=auth_headers(user),
    )
    # Second message
    await client.post(
        "/api/support/messages",
        json={"text": "Second"},
        headers=auth_headers(user),
    )

    # Only one consent log
    result = await db_session.execute(
        select(ConsentLog).where(
            ConsentLog.user_id == user.id,
            ConsentLog.consent_type == "support_chat_consent",
        )
    )
    consents = result.scalars().all()
    assert len(consents) == 1


@pytest.mark.asyncio
async def test_send_empty_message_fails(client, user):
    resp = await client.post(
        "/api/support/messages",
        json={},
        headers=auth_headers(user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_message_with_image_key(client, user):
    image_key = f"support/{user.id}/screenshot.png"
    resp = await client.post(
        "/api/support/messages",
        json={"text": "See screenshot", "image_key": image_key},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_key"] == image_key


@pytest.mark.asyncio
async def test_send_message_with_foreign_image_key_rejected(client, user):
    """Prevent IDOR: user cannot attach another user's image."""
    resp = await client.post(
        "/api/support/messages",
        json={"text": "Stolen", "image_key": "support/other-user-id/img.png"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_message_reopens_resolved(client, db_session, user):
    # Create resolved conversation
    conv = SupportConversation(user_id=user.id, status="resolved")
    db_session.add(conv)
    await db_session.flush()

    resp = await client.post(
        "/api/support/messages",
        json={"text": "I have a new issue"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200

    await db_session.refresh(conv)
    assert conv.status == "open"


@pytest.mark.asyncio
async def test_send_message_no_auth(client):
    resp = await client.post(
        "/api/support/messages",
        json={"text": "Hello"},
    )
    assert resp.status_code == 401


# --- GET /api/support/unread-count ---


@pytest.mark.asyncio
async def test_unread_count_zero(client, user):
    resp = await client.get(
        "/api/support/unread-count",
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_unread_count_with_messages(client, db_session, user):
    conv = SupportConversation(user_id=user.id, unread_user=3)
    db_session.add(conv)
    await db_session.flush()

    resp = await client.get(
        "/api/support/unread-count",
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 3


# --- Admin endpoints ---


@pytest.mark.asyncio
async def test_admin_list_support_conversations(client, db_session, user, admin_user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="user",
        sender_id=user.id,
        text="Need help",
    )
    db_session.add(msg)
    await db_session.flush()

    resp = await client.get(
        "/api/admin/support/conversations",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["user_id"] == user.id
    assert data["items"][0]["last_message_text"] == "Need help"


@pytest.mark.asyncio
async def test_admin_get_support_messages(client, db_session, user, admin_user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="user",
        sender_id=user.id,
        text="Help please",
    )
    db_session.add(msg)
    conv.unread_admin = 1
    await db_session.flush()

    resp = await client.get(
        f"/api/admin/support/conversations/{conv.id}",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["text"] == "Help please"


@pytest.mark.asyncio
async def test_admin_send_support_reply(client, db_session, user, admin_user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    resp = await client.post(
        f"/api/admin/support/conversations/{conv.id}/messages",
        json={"text": "How can I help?"},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sender_type"] == "admin"
    assert data["text"] == "How can I help?"

    await db_session.refresh(conv)
    assert conv.unread_user == 1


@pytest.mark.asyncio
async def test_admin_resolve_conversation(client, db_session, user, admin_user):
    conv = SupportConversation(user_id=user.id)
    db_session.add(conv)
    await db_session.flush()

    resp = await client.post(
        f"/api/admin/support/conversations/{conv.id}/resolve",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"

    await db_session.refresh(conv)
    assert conv.status == "resolved"


@pytest.mark.asyncio
async def test_admin_unread_count(client, db_session, user, admin_user):
    conv = SupportConversation(user_id=user.id, unread_admin=5)
    db_session.add(conv)
    await db_session.flush()

    resp = await client.get(
        "/api/admin/support/unread-count",
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 5
