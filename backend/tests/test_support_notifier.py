"""Tests for support reply notification orchestrator."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.feedback import SupportConversation, SupportMessage
from app.models.user import User, UserSettings


@pytest_asyncio.fixture
async def user_with_tg(db_session):
    u = User(
        id=str(uuid.uuid4()),
        tier="FREE",
        email=f"tg-{uuid.uuid4().hex[:8]}@test.com",
        telegram_user_id="123456789",
    )
    db_session.add(u)
    us = UserSettings(id=str(uuid.uuid4()), user_id=u.id, language="ru")
    db_session.add(us)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def user_email_only(db_session):
    u = User(
        id=str(uuid.uuid4()),
        tier="FREE",
        email=f"email-{uuid.uuid4().hex[:8]}@test.com",
    )
    db_session.add(u)
    us = UserSettings(id=str(uuid.uuid4()), user_id=u.id, language="en")
    db_session.add(us)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def user_no_contacts(db_session):
    u = User(id=str(uuid.uuid4()), tier="FREE")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def conversation(db_session, user_with_tg):
    conv = SupportConversation(
        id=str(uuid.uuid4()),
        user_id=user_with_tg.id,
        status="open",
    )
    db_session.add(conv)
    await db_session.flush()
    return conv


@pytest_asyncio.fixture
async def admin_message(db_session, conversation, user_with_tg):
    msg = SupportMessage(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        sender_type="admin",
        sender_id=user_with_tg.id,
        text="Мы разобрались с вашей проблемой. Всё починили!",
    )
    db_session.add(msg)
    await db_session.flush()
    return msg


@pytest.mark.asyncio
async def test_sends_telegram_when_user_has_tg(
    db_session, user_with_tg, conversation, admin_message,
):
    """Should send Telegram notification when user has telegram_user_id."""
    from app.services.support_notifier import notify_user_support_reply

    with patch("app.services.support_notifier.send_telegram_message", new_callable=AsyncMock) as mock_tg, \
         patch("app.services.support_notifier.get_redis", new_callable=AsyncMock) as mock_redis, \
         patch("app.services.support_notifier.get_db_session") as mock_db, \
         patch("app.services.support_notifier.settings") as mock_settings:
        mock_settings.telegram_bot_token = "fake-token"
        mock_settings.app_url = "https://piratex.ai"
        mock_redis.return_value = AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock())
        mock_db.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_tg.return_value = {"message_id": 1}

        await notify_user_support_reply(str(admin_message.id), str(user_with_tg.id))

        mock_tg.assert_called_once()
        call_args = mock_tg.call_args
        assert call_args[0][0] == "123456789"  # chat_id
        assert "Мы разобрались" in call_args[0][2]  # text preview


@pytest.mark.asyncio
async def test_sends_email_when_no_telegram(
    db_session, user_email_only,
):
    """Should send email when user has no telegram_user_id."""
    from app.services.support_notifier import notify_user_support_reply

    conv = SupportConversation(
        id=str(uuid.uuid4()), user_id=user_email_only.id, status="open",
    )
    db_session.add(conv)
    msg = SupportMessage(
        id=str(uuid.uuid4()), conversation_id=conv.id,
        sender_type="admin", sender_id=user_email_only.id,
        text="We fixed your issue.",
    )
    db_session.add(msg)
    await db_session.flush()

    with patch("app.services.support_notifier.send_support_reply_email", new_callable=AsyncMock) as mock_email, \
         patch("app.services.support_notifier.send_telegram_message", new_callable=AsyncMock) as mock_tg, \
         patch("app.services.support_notifier.get_redis", new_callable=AsyncMock) as mock_redis, \
         patch("app.services.support_notifier.get_db_session") as mock_db:
        mock_redis.return_value = AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock())
        mock_db.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

        await notify_user_support_reply(str(msg.id), str(user_email_only.id))

        mock_tg.assert_not_called()
        mock_email.assert_called_once()
        call_args = mock_email.call_args
        assert user_email_only.email in call_args[1].get("to_email", call_args[0][0] if call_args[0] else "")
        assert "en" in str(call_args)  # language


@pytest.mark.asyncio
async def test_falls_back_to_email_when_telegram_fails(
    db_session, user_with_tg, conversation, admin_message,
):
    """Should fall back to email when Telegram send returns None (e.g. bot blocked)."""
    from app.services.support_notifier import notify_user_support_reply

    with patch("app.services.support_notifier.send_telegram_message", new_callable=AsyncMock) as mock_tg, \
         patch("app.services.support_notifier.send_support_reply_email", new_callable=AsyncMock) as mock_email, \
         patch("app.services.support_notifier.get_redis", new_callable=AsyncMock) as mock_redis, \
         patch("app.services.support_notifier.get_db_session") as mock_db, \
         patch("app.services.support_notifier.settings") as mock_settings:
        mock_settings.telegram_bot_token = "fake-token"
        mock_settings.app_url = "https://piratex.ai"
        mock_redis.return_value = AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock())
        mock_db.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_tg.return_value = None  # Telegram failed (bot blocked, network error, etc.)
        mock_email.return_value = True

        await notify_user_support_reply(str(admin_message.id), str(user_with_tg.id))

        mock_tg.assert_called_once()
        mock_email.assert_called_once()
        assert user_with_tg.email in str(mock_email.call_args)


@pytest.mark.asyncio
async def test_skips_when_message_already_read(
    db_session, user_with_tg, conversation, admin_message,
):
    """Should skip notification when message is already read."""
    from datetime import datetime

    from app.services.support_notifier import notify_user_support_reply

    admin_message.read_at = datetime.utcnow()
    await db_session.flush()

    with patch("app.services.support_notifier.send_telegram_message", new_callable=AsyncMock) as mock_tg, \
         patch("app.services.support_notifier.get_redis", new_callable=AsyncMock) as mock_redis, \
         patch("app.services.support_notifier.get_db_session") as mock_db:
        mock_redis.return_value = AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock())
        mock_db.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

        await notify_user_support_reply(str(admin_message.id), str(user_with_tg.id))

        mock_tg.assert_not_called()


@pytest.mark.asyncio
async def test_skips_when_cooldown_active(
    db_session, user_with_tg, conversation, admin_message,
):
    """Should skip notification when cooldown is active in Redis."""
    from app.services.support_notifier import notify_user_support_reply

    with patch("app.services.support_notifier.send_telegram_message", new_callable=AsyncMock) as mock_tg, \
         patch("app.services.support_notifier.get_redis", new_callable=AsyncMock) as mock_redis, \
         patch("app.services.support_notifier.get_db_session") as mock_db:
        mock_redis.return_value = AsyncMock(get=AsyncMock(return_value="1"), set=AsyncMock())
        mock_db.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

        await notify_user_support_reply(str(admin_message.id), str(user_with_tg.id))

        mock_tg.assert_not_called()


@pytest.mark.asyncio
async def test_skips_when_no_contacts(
    db_session, user_no_contacts,
):
    """Should silently skip when user has no email or telegram."""
    from app.services.support_notifier import notify_user_support_reply

    conv = SupportConversation(
        id=str(uuid.uuid4()), user_id=user_no_contacts.id, status="open",
    )
    db_session.add(conv)
    msg = SupportMessage(
        id=str(uuid.uuid4()), conversation_id=conv.id,
        sender_type="admin", sender_id=user_no_contacts.id,
        text="Test",
    )
    db_session.add(msg)
    await db_session.flush()

    with patch("app.services.support_notifier.send_support_reply_email", new_callable=AsyncMock) as mock_email, \
         patch("app.services.support_notifier.send_telegram_message", new_callable=AsyncMock) as mock_tg, \
         patch("app.services.support_notifier.get_redis", new_callable=AsyncMock) as mock_redis, \
         patch("app.services.support_notifier.get_db_session") as mock_db:
        mock_redis.return_value = AsyncMock(get=AsyncMock(return_value=None), set=AsyncMock())
        mock_db.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_db.return_value.__aexit__ = AsyncMock(return_value=False)

        await notify_user_support_reply(str(msg.id), str(user_no_contacts.id))

        mock_tg.assert_not_called()
        mock_email.assert_not_called()
