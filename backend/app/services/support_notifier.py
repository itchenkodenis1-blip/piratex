"""Notify users about support replies via Telegram or Email.

Called as a deferred arq task ~2 minutes after admin sends a reply.
Checks whether the message has been read; if not, sends a notification
via the best available channel (Telegram > Email).
"""

import logging

from sqlalchemy import select

from app.config import settings
from app.core.redis_pool import get_redis
from app.database import get_db_session
from app.models.feedback import SupportMessage
from app.models.user import User, UserSettings
from app.services.email_sender import send_support_reply_email
from app.services.telegram import escape_html, send_telegram_message

logger = logging.getLogger(__name__)

_COOLDOWN_TTL = 300  # 5 minutes
_PREVIEW_LEN = 200
_COOLDOWN_PREFIX = "support_notif"


async def notify_user_support_reply(message_id: str, user_id: str) -> None:
    """Check if the support message is still unread and notify the user."""
    async with get_db_session() as db:
        # 1. Load message — check if still unread
        msg = await db.get(SupportMessage, message_id)
        if not msg or msg.read_at is not None:
            return

        # 2. Check Redis cooldown
        cooldown_key = f"{_COOLDOWN_PREFIX}:{user_id}"
        redis = await get_redis()
        if redis and await redis.get(cooldown_key):
            return

        # 3. Load user + settings
        user = await db.get(User, user_id)
        if not user:
            return

        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        user_settings = result.scalar_one_or_none()
        lang = (user_settings.language if user_settings and user_settings.language else "ru")

        # 4. Build preview
        preview = (msg.text or "")[:_PREVIEW_LEN]
        if not preview:
            return  # Nothing to show (image-only message)

        # 5. Send via best channel
        sent = False
        chat_url = f"{settings.app_url}/settings?support=open"

        if user.telegram_user_id and settings.telegram_bot_token:
            sent = await _send_telegram(user.telegram_user_id, preview, chat_url, lang)

        if not sent and user.email:
            sent = await _send_email(user.email, preview, chat_url, lang)

        # 6. Set cooldown
        if sent and redis:
            await redis.set(cooldown_key, "1", ex=_COOLDOWN_TTL)

        if sent:
            logger.info("[support-notify] Notified user %s (message %s)", user_id[:8], message_id[:8])


async def _send_telegram(chat_id: str, preview: str, chat_url: str, lang: str) -> bool:
    """Send Telegram notification to user."""
    TITLES = {
        "ru": "💬 Вам ответили из поддержки ВидеоРентген",
        "en": "💬 You have a reply from VideoRentgen support",
        "fr": "💬 Réponse du support VideoRentgen",
        "pt": "💬 Resposta do suporte VideoRentgen",
        "de": "💬 Antwort vom VideoRentgen Support",
    }
    BUTTONS = {
        "ru": "Открыть чат",
        "en": "Open chat",
        "fr": "Ouvrir le chat",
        "pt": "Abrir chat",
        "de": "Chat öffnen",
    }
    title = TITLES.get(lang, TITLES["en"])
    button_text = BUTTONS.get(lang, BUTTONS["en"])
    text = f"{title}\n\n<i>{escape_html(preview)}</i>"
    reply_markup = {
        "inline_keyboard": [[
            {"text": button_text, "url": chat_url},
        ]],
    }
    try:
        result = await send_telegram_message(
            chat_id, settings.telegram_bot_token, text,
            parse_mode="HTML", reply_markup=reply_markup,
        )
        return result is not None
    except Exception:
        logger.exception("[support-notify] Telegram send failed for %s", chat_id)
        return False


async def _send_email(to_email: str, preview: str, chat_url: str, lang: str) -> bool:
    """Send email notification to user."""
    try:
        return await send_support_reply_email(
            to_email=to_email,
            message_preview=preview,
            chat_url=chat_url,
            lang=lang,
        )
    except Exception:
        logger.exception("[support-notify] Email send failed for %s", to_email)
        return False
