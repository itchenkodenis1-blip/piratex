"""Auto-send a personal welcome message from the founder in support chat."""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.feedback import SupportConversation, SupportMessage
from app.models.user import User, UserSettings

logger = logging.getLogger(__name__)

# Welcome texts per language (detected from user's language setting)
WELCOME_TEXTS = {
    "ru": "Привет! Я лично читаю все сообщения, чтобы сделать проект лучше. Поэтому, если у тебя есть вопрос или нужна помощь, пиши — я тебе помогу.",
    "en": "Hi! I personally read every message to make the project better. So if you have a question or need help, just write — I'll help you out.",
    "pt": "Olá! Eu leio pessoalmente todas as mensagens para melhorar o projeto. Se você tem uma pergunta ou precisa de ajuda, escreva — eu vou te ajudar.",
    "fr": "Salut ! Je lis personnellement chaque message pour améliorer le projet. Si tu as une question ou besoin d'aide, écris-moi — je t'aiderai.",
    "de": "Hallo! Ich lese persönlich jede Nachricht, um das Projekt besser zu machen. Wenn du eine Frage hast oder Hilfe brauchst, schreib einfach — ich helfe dir.",
}


async def _get_founder_user_id(db: AsyncSession) -> str | None:
    """Find founder's user ID from admin_emails config."""
    if not settings.admin_emails:
        return None
    first_admin_email = settings.admin_emails.split(",")[0].strip()
    if not first_admin_email:
        return None
    result = await db.execute(
        select(User.id).where(User.email == first_admin_email).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_user_language(db: AsyncSession, user_id: str) -> str:
    """Get user's preferred language from settings, default to 'ru'."""
    result = await db.execute(
        select(UserSettings.language).where(UserSettings.user_id == user_id).limit(1)
    )
    return result.scalar_one_or_none() or "ru"


async def send_founder_welcome(
    db: AsyncSession,
    user_id: str,
    language: str | None = None,
) -> SupportConversation | None:
    """Create a support conversation with a welcome message from the founder.

    Returns the conversation if created, None if already exists or founder not found.
    Idempotent — safe to call multiple times for the same user.
    """
    # Check if conversation already exists
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.user_id == user_id)
    )
    if result.scalar_one_or_none():
        return None  # Already has a conversation — don't duplicate

    founder_id = await _get_founder_user_id(db)
    if not founder_id:
        logger.warning("Founder user not found — cannot send welcome message")
        return None

    # Don't send welcome to the founder themselves
    if user_id == founder_id:
        return None

    # Auto-detect language if not provided
    if not language:
        language = await _get_user_language(db, user_id)

    # Create conversation + welcome message
    conv = SupportConversation(user_id=user_id, unread_user=1)
    db.add(conv)
    await db.flush()

    text = WELCOME_TEXTS.get(language, WELCOME_TEXTS["en"])
    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="admin",
        sender_id=founder_id,
        text=text,
    )
    db.add(msg)
    conv.updated_at = datetime.utcnow()

    await db.commit()

    logger.info("Sent founder welcome to user %s (lang=%s)", user_id[:8], language)
    return conv
