import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import create_access_token, get_current_user
from app.core.exceptions import InvalidURLError
from app.core.identity import find_or_create_user, link_identity, merge_ghost_into_user
from app.database import async_session, get_db
from app.models.identity import AuthIdentity
from app.models.job import Job, JobStatus
from app.models.message import TelegramMessage
from app.models.user import TelegramAuthCode, User
from app.services.job_creator import create_job_from_url
from app.services.telegram import (
    answer_callback_query,
    check_channel_membership,
    edit_telegram_message,
    escape_html,
    format_result_card,
    format_result_keyboard,
    send_telegram_message,
)
from app.services.usage import check_can_create_analysis

CONNECT_CODE_TTL_MINUTES = 5

logger = logging.getLogger(__name__)

router = APIRouter()

# URL patterns for supported platforms (tolerant: allows query params, trailing slashes)
_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:"
    r"instagram\.com/(?:reel|p)/[\w-]+/?\S*"
    r"|tiktok\.com/\S+"
    r"|vm\.tiktok\.com/\S+"
    r"|youtube\.com/shorts/[\w-]+\S*"
    r"|youtu\.be/[\w-]+\S*"
    r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _log_message(
    *,
    telegram_user_id: str,
    direction: str,
    text: str,
    telegram_username: str | None = None,
    telegram_name: str | None = None,
    user_id: str | None = None,
) -> None:
    """Save a telegram message to DB for admin visibility (best-effort)."""
    try:
        async with async_session() as db:
            db.add(TelegramMessage(
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                telegram_name=telegram_name,
                user_id=user_id,
                direction=direction,
                text=text,
            ))
            await db.commit()
    except Exception:
        logger.warning("Failed to log telegram message", exc_info=True)


async def _resolve_user(db: AsyncSession, telegram_user_id: str) -> User | None:
    """Find full User by telegram_user_id."""
    result = await db.execute(
        select(User).where(User.telegram_user_id == telegram_user_id)
    )
    return result.scalar_one_or_none()


async def _send_and_log(
    chat_id: str, text: str, *,
    tg_username: str | None = None,
    tg_name: str | None = None,
    user_id: str | None = None,
    parse_mode: str | None = None,
    reply_markup: dict | None = None,
) -> dict | None:
    """Send message and log it. Returns Telegram API result."""
    result = await send_telegram_message(
        chat_id, settings.telegram_bot_token, text,
        parse_mode=parse_mode, reply_markup=reply_markup,
    )
    await _log_message(
        telegram_user_id=chat_id,
        direction="out",
        text=text,
        telegram_username=tg_username,
        telegram_name=tg_name,
        user_id=user_id,
    )
    return result


def _result_card_text(job: Job) -> str:
    """Format analysis result as HTML card (delegates to shared helper)."""
    return format_result_card(job)


def _result_keyboard(job: Job) -> dict:
    """Build inline keyboard for result card (delegates to shared helper)."""
    return format_result_keyboard(job, settings.app_url)


# ---------------------------------------------------------------------------
# Webhook — main entry point
# ---------------------------------------------------------------------------


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Telegram Bot webhook updates (called by Telegram)."""
    # Verify webhook secret (fail-closed: reject if not configured)
    expected_secret = settings.telegram_webhook_secret
    if not expected_secret:
        logger.warning("Telegram webhook secret not configured, rejecting request")
        return {"ok": True}
    received_secret = request.headers.get(
        "x-telegram-bot-api-secret-token", ""
    )
    if not hmac.compare_digest(received_secret, expected_secret):
        return {"ok": True}

    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    # Handle callback_query (inline button presses) BEFORE message
    callback_query = body.get("callback_query")
    if callback_query:
        await _handle_callback(request, db, callback_query)
        return {"ok": True}

    message = body.get("message")
    if not message:
        return {"ok": True}

    await _handle_message(request, db, message)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------


async def _handle_message(request: Request, db: AsyncSession, message: dict):
    """Route incoming text messages to appropriate handlers."""
    text = message.get("text", "")
    from_user = message.get("from", {})
    telegram_user_id = str(from_user.get("id", ""))
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not telegram_user_id:
        return

    # Check if this is a pending support reply from admin
    if text and await _try_handle_support_reply(db, chat_id, text):
        return

    # Extract user info
    tg_username = from_user.get("username")
    tg_first_name = from_user.get("first_name", "")
    tg_last_name = from_user.get("last_name", "")
    display_name = (
        f"{tg_first_name} {tg_last_name}".strip()
        or tg_username
        or f"User-{telegram_user_id}"
    )

    user = await _resolve_user(db, telegram_user_id)
    user_id = user.id if user else None

    # Log incoming message
    await _log_message(
        telegram_user_id=telegram_user_id,
        direction="in",
        text=text,
        telegram_username=tg_username,
        telegram_name=display_name,
        user_id=user_id,
    )

    stripped = text.strip()

    # Command: /start (no code)
    if stripped == "/start":
        await _cmd_start(chat_id, tg_username, display_name, user_id)
        return

    # Command: /start <code> — auth flow
    if stripped.startswith("/start "):
        code = stripped[7:].strip()
        if code:
            await _cmd_start_code(
                db, chat_id, telegram_user_id, code,
                tg_username, display_name,
            )
        return

    # Command: /help
    if stripped == "/help":
        await _cmd_help(chat_id, tg_username, display_name, user_id)
        return

    # Command: /status
    if stripped == "/status":
        await _cmd_status(db, chat_id, user, tg_username, display_name)
        return

    # Check for URL
    url_match = _URL_RE.search(text)
    if url_match:
        await _handle_url(
            request, db, chat_id, user, url_match.group(0),
            tg_username, display_name,
        )
        return

    # Unknown text
    await _send_and_log(
        chat_id,
        "Скиньте ссылку на рилс для анализа.\n/help — список команд",
        tg_username=tg_username, tg_name=display_name, user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def _cmd_start(chat_id: str, tg_username: str | None, display_name: str, user_id: str | None):
    """Welcome message with instructions."""
    text = (
        "\U0001f44b Привет! Я бот Piratex.ai\n\n"
        "Скиньте мне ссылку на рилс — и я создам для вас:\n"
        "\U0001f4dd Сценарий для съёмки\n"
        "\U0001f4f1 Готовый пост с хештегами\n"
        "\U0001f3af Анализ виральности\n\n"
        "Поддерживаю: Instagram, TikTok, YouTube\n\n"
        "/help — все возможности\n"
        "/status — ваш тариф"
    )
    await _send_and_log(
        chat_id, text,
        tg_username=tg_username, tg_name=display_name, user_id=user_id,
    )


async def _cmd_help(chat_id: str, tg_username: str | None, display_name: str, user_id: str | None):
    """/help command."""
    text = (
        "\U0001f3f4\u200d\u2620\ufe0f Что умеет Piratex Bot:\n\n"
        "\U0001f4ce Отправьте ссылку на рилс — получите сценарий, пост и анализ\n"
        "\U0001f4e1 Радар трендов — уведомления о залетевших рилсах в вашей нише\n"
        "\U0001f50d Кнопка «Разобрать» — запустить анализ прямо из уведомления\n\n"
        "Команды:\n"
        "/status — тариф и остаток анализов\n"
        "/help — эта справка"
    )
    await _send_and_log(
        chat_id, text,
        tg_username=tg_username, tg_name=display_name, user_id=user_id,
    )


async def _cmd_status(
    db: AsyncSession, chat_id: str, user: User | None,
    tg_username: str | None, display_name: str,
):
    """/status — show tier and usage."""
    if not user:
        await _send_and_log(
            chat_id,
            "Вы ещё не привязали аккаунт Piratex.\n\n"
            "Перейдите на piratex.ai, авторизуйтесь и привяжите Telegram в настройках.",
            tg_username=tg_username, tg_name=display_name,
        )
        return

    can, used, limit, detail = await check_can_create_analysis(db, user, enforce=False)
    tier = user.tier or "FREE"

    if limit:
        usage_line = f"Использовано: {used}/{limit} анализов"
    else:
        usage_line = f"Использовано: {used} анализов (без лимита)"

    # End of month
    now = datetime.utcnow()
    import calendar
    last_day = calendar.monthrange(now.year, now.month)[1]
    end_date = f"{last_day:02d}.{now.month:02d}.{now.year}"

    text = (
        f"\U0001f4ca Ваш аккаунт\n\n"
        f"Тариф: {tier}\n"
        f"{usage_line}\n"
        f"Период: до {end_date}"
    )

    reply_markup = None
    if tier in ("FREE", "REGISTERED"):
        reply_markup = {
            "inline_keyboard": [[
                {"text": "\u2b06\ufe0f Улучшить тариф", "url": f"{settings.app_url}/pricing"},
            ]]
        }

    await _send_and_log(
        chat_id, text,
        tg_username=tg_username, tg_name=display_name, user_id=user.id,
        reply_markup=reply_markup,
    )


# ---------------------------------------------------------------------------
# URL handling — launch job
# ---------------------------------------------------------------------------


async def _handle_url(
    request: Request, db: AsyncSession,
    chat_id: str, user: User | None, url: str,
    tg_username: str | None, display_name: str,
):
    """Process a reel URL: create job and send progress message."""
    if not user:
        await _send_and_log(
            chat_id,
            "Чтобы анализировать рилсы, привяжите Telegram к аккаунту Piratex.\n\n"
            "Перейдите на piratex.ai → Настройки → Привязать Telegram.",
            tg_username=tg_username, tg_name=display_name,
            reply_markup={
                "inline_keyboard": [[
                    {"text": "\U0001f310 Открыть Piratex", "url": settings.app_url},
                ]]
            },
        )
        return

    # Send progress message first
    progress_result = await _send_and_log(
        chat_id,
        "\u23f3 Принял ссылку, начинаю анализ...",
        tg_username=tg_username, tg_name=display_name, user_id=user.id,
    )
    progress_message_id = progress_result.get("message_id") if progress_result else None

    # Helper: edit progress message or send new if edit impossible (message_id=None)
    async def _reply(text: str, *, parse_mode: str | None = None, reply_markup: dict | None = None):
        if progress_message_id:
            await edit_telegram_message(
                chat_id, progress_message_id, settings.telegram_bot_token,
                text, parse_mode=parse_mode, reply_markup=reply_markup,
            )
        else:
            await _send_and_log(
                chat_id, text,
                tg_username=tg_username, tg_name=display_name, user_id=user.id,
                parse_mode=parse_mode, reply_markup=reply_markup,
            )

    managed = getattr(request.app.state, "managed_arq_pool", None)
    arq_pool = await managed.get_pool() if managed else getattr(request.app.state, "arq_pool", None)

    try:
        result = await create_job_from_url(
            db, user, url, arq_pool,
            source="telegram",
            telegram_chat_id=chat_id,
            telegram_message_id=progress_message_id,
        )
    except (ValueError, InvalidURLError) as e:
        await _reply(f"\u274c {e}")
        return

    if result.outcome == "created":
        # Progress message already sent, worker will update it
        return

    if result.outcome == "existing_completed":
        job = result.job
        await _reply(
            _result_card_text(job),
            parse_mode="HTML",
            reply_markup=_result_keyboard(job),
        )
        return

    # NOTE: "library_hit" outcome removed — cached replay now goes through "created" path

    if result.outcome == "existing_in_progress":
        await _reply("\u23f3 Этот рилс уже анализируется, результат скоро будет.")
        return

    if result.outcome == "limit_exceeded":
        await _reply(
            f"\u274c Лимит анализов исчерпан ({result.used}/{result.limit}).\n"
            "Улучшите тариф для продолжения.",
            reply_markup={
                "inline_keyboard": [[
                    {"text": "\u2b06\ufe0f Улучшить тариф", "url": f"{settings.app_url}/pricing"},
                ]]
            },
        )
        return

    if result.outcome == "queue_unavailable":
        await _reply("\u26a0\ufe0f Сервис временно недоступен. Попробуйте позже.")
        return

    if result.outcome == "activation_required":
        channel_url = settings.telegram_channel_url
        reply_markup = None
        if channel_url:
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "\U0001f4e2 Подписаться", "url": channel_url},
                ]]
            }
        await _reply(
            "Подпишитесь на наш Telegram-канал, чтобы активировать бесплатные анализы.",
            reply_markup=reply_markup,
        )
        return


# ---------------------------------------------------------------------------
# Callback query handler
# ---------------------------------------------------------------------------


async def _handle_callback(request: Request, db: AsyncSession, callback_query: dict):
    """Handle inline button presses."""
    data = callback_query.get("data", "")
    cb_id = callback_query.get("id", "")
    from_user = callback_query.get("from", {})
    telegram_user_id = str(from_user.get("id", ""))
    chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))

    if not telegram_user_id or not chat_id:
        await answer_callback_query(cb_id, settings.telegram_bot_token)
        return

    user = await _resolve_user(db, telegram_user_id)

    # script:{job_id}
    if data.startswith("script:"):
        job_id = data[7:]
        await _cb_send_content(db, cb_id, chat_id, user, job_id, "script")
        return

    # post:{job_id}
    if data.startswith("post:"):
        job_id = data[5:]
        await _cb_send_content(db, cb_id, chat_id, user, job_id, "post")
        return

    # analyze:{profile_reel_id}
    if data.startswith("analyze:"):
        reel_id = data[8:]
        await _cb_analyze_reel(request, db, cb_id, chat_id, user, reel_id)
        return

    # support_reply:{conversation_id} — admin replies to support from Telegram
    if data.startswith("support_reply:"):
        # Verify the user pressing the button is an admin
        admin_tg_ids = [t.strip() for t in settings.admin_telegram_ids.split(",") if t.strip()]
        if telegram_user_id not in admin_tg_ids:
            await answer_callback_query(cb_id, settings.telegram_bot_token, text="⛔ Нет доступа")
            return
        conv_id = data[len("support_reply:"):]
        await _cb_support_reply_prompt(db, cb_id, chat_id, conv_id)
        return

    await answer_callback_query(cb_id, settings.telegram_bot_token)


async def _cb_send_content(
    db: AsyncSession, cb_id: str, chat_id: str,
    user: User | None, job_id: str, content_type: str,
):
    """Send script or post content as a separate message."""
    if not user:
        await answer_callback_query(
            cb_id, settings.telegram_bot_token,
            text="Аккаунт не привязан",
        )
        return

    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()

    if not job or not job.adaptation_summary:
        await answer_callback_query(
            cb_id, settings.telegram_bot_token,
            text="Анализ не найден",
        )
        return

    summary = job.adaptation_summary
    if content_type == "script":
        title = "\U0001f4dd Сценарий"
        content = summary.get("script", "Сценарий не найден")
    else:
        title = "\U0001f4f1 Пост"
        content = summary.get("description", "")
        # Add hashtags
        hashtags = summary.get("hashtags", {})
        tag_list = hashtags.get("primary", []) + hashtags.get("secondary", [])
        if tag_list:
            content += "\n\n" + " ".join(tag_list)

    full_text = f"{title}\n\n{content}"

    # Telegram message limit is 4096 UTF-16 code units — use safe margin for emoji
    MAX_LEN = 4000
    if len(full_text) <= MAX_LEN:
        await send_telegram_message(
            chat_id, settings.telegram_bot_token, full_text,
        )
    else:
        chunks = [full_text[i:i + MAX_LEN] for i in range(0, len(full_text), MAX_LEN)]
        for chunk in chunks:
            await send_telegram_message(
                chat_id, settings.telegram_bot_token, chunk,
            )

    await answer_callback_query(cb_id, settings.telegram_bot_token)


async def _cb_analyze_reel(
    request: Request, db: AsyncSession,
    cb_id: str, chat_id: str, user: User | None, reel_id: str,
):
    """Launch analysis from radar notification button."""
    from app.models.trends import ProfileReel

    if not user:
        await answer_callback_query(
            cb_id, settings.telegram_bot_token,
            text="Привяжите аккаунт на piratex.ai",
        )
        return

    # Look up reel URL
    result = await db.execute(
        select(ProfileReel.url).where(ProfileReel.id == reel_id)
    )
    row = result.first()
    if not row:
        await answer_callback_query(
            cb_id, settings.telegram_bot_token,
            text="Рилс не найден",
        )
        return

    reel_url = row[0]

    await answer_callback_query(cb_id, settings.telegram_bot_token, text="Запускаю анализ...")

    # Reuse _handle_url logic
    await _handle_url(
        request, db, chat_id, user, reel_url,
        tg_username=None, display_name="",
    )


# ---------------------------------------------------------------------------
# Auth code handling (preserved from original)
# ---------------------------------------------------------------------------


async def _cmd_start_code(
    db: AsyncSession, chat_id: str, telegram_user_id: str, code: str,
    tg_username: str | None, display_name: str,
):
    """Handle /start <code> — Telegram auth flow."""
    logger.info("[tg-auth] /start code=%s… tg_user=%s", code[:6], telegram_user_id)

    resolved_user_id = (await _resolve_user(db, telegram_user_id))
    resolved_id = resolved_user_id.id if resolved_user_id else None

    # Find the auth code (FOR UPDATE prevents concurrent use of same code)
    result = await db.execute(
        select(TelegramAuthCode)
        .where(
            TelegramAuthCode.code == code,
            TelegramAuthCode.confirmed == False,  # noqa: E712
        )
        .with_for_update(skip_locked=True)
    )
    auth_code = result.scalar_one_or_none()

    if not auth_code or datetime.utcnow() > auth_code.expires_at:
        logger.warning("[tg-auth] code expired or not found: %s", code[:6])
        await _send_and_log(
            chat_id,
            "Код авторизации истёк. Попробуйте ещё раз на сайте.",
            tg_username=tg_username, tg_name=display_name, user_id=resolved_id,
        )
        return

    # Load linked user from auth code (may be ghost or authenticated user)
    linked_user = None
    if auth_code.ghost_user_id:
        linked_user_id = auth_code.ghost_user_id
        auth_code.ghost_user_id = None
        await db.flush()

        linked_result = await db.execute(
            select(User).where(User.id == linked_user_id)
        )
        linked_user = linked_result.scalar_one_or_none()

    if linked_user and not linked_user.is_anonymous:
        # Settings flow: link Telegram to an existing authenticated user.
        # If this Telegram ID already belongs to another user (e.g. user
        # previously interacted with the bot before registering via email),
        # merge that old user into the authenticated one first.
        existing_tg_identity = (await db.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == "telegram",
                AuthIdentity.provider_user_id == telegram_user_id,
            )
        )).scalar_one_or_none()

        if existing_tg_identity and existing_tg_identity.user_id != linked_user.id:
            old_owner = (await db.execute(
                select(User).where(User.id == existing_tg_identity.user_id)
            )).scalar_one_or_none()
            if old_owner:
                logger.info(
                    "[tg-auth] merging old tg user %s into %s",
                    old_owner.id, linked_user.id,
                )
                await merge_ghost_into_user(db, ghost=old_owner, target=linked_user)
                await db.flush()

        await link_identity(
            db,
            linked_user,
            provider="telegram",
            provider_user_id=telegram_user_id,
            display_name=display_name,
        )
        user = linked_user
    else:
        # Auth flow: find or create user (ghost merge)
        ghost = linked_user if linked_user and linked_user.is_anonymous else None
        user, identity, is_new = await find_or_create_user(
            db,
            provider="telegram",
            provider_user_id=telegram_user_id,
            display_name=display_name,
            ghost_user=ghost,
        )

    # Sync Telegram-specific fields
    user.telegram_user_id = telegram_user_id
    user.telegram_username = tg_username
    if not user.name:
        user.name = display_name
    if not user.auth_provider:
        user.auth_provider = "telegram"

    await db.flush()

    # Generate JWT and confirm auth code
    token = create_access_token(user.id, user.token_version or 1)
    auth_code.confirmed_user_id = user.id
    auth_code.token = token
    auth_code.confirmed = True

    try:
        await db.commit()
    except Exception:
        logger.exception("[tg-auth] commit failed for code=%s user=%s", code[:6], user.id)
        raise

    logger.info("[tg-auth] confirmed code=%s… user=%s", code[:6], user.id)

    channel_url = settings.telegram_channel_url
    if channel_url:
        auth_success_text = (
            "✅ *Авторизация прошла успешно\\!*\n\n"
            "Остался один шаг — подпишитесь на наш "
            f"[Telegram\\-канал]({channel_url}), "
            "и вы получите *3 бесплатные генерации* в месяц\\.\n\n"
            "Вернитесь на сайт и нажмите «Проверить подписку»\\."
        )
    else:
        auth_success_text = (
            "✅ *Авторизация прошла успешно\\!*\n\n"
            "Вернитесь на сайт, чтобы продолжить\\."
        )
    await _send_and_log(
        chat_id, auth_success_text,
        parse_mode="MarkdownV2",
        tg_username=tg_username, tg_name=display_name, user_id=user.id,
    )


# ---------------------------------------------------------------------------
# Verify subscription + status
# ---------------------------------------------------------------------------


@router.post("/verify")
async def verify_telegram_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check channel subscription and upgrade tier if subscribed."""
    if not user.telegram_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram not linked",
        )

    try:
        subscribed = await check_channel_membership(
            user.telegram_user_id,
            settings.telegram_bot_token,
            settings.telegram_channel_id,
        )
    except Exception:
        logger.warning("Telegram API unreachable during /verify")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Telegram API unavailable, try again later",
        )

    user.telegram_checked_at = datetime.utcnow()

    # Only auto-switch between REGISTERED ↔ FREE; never touch paid tiers
    PAID_TIERS = {"START", "PRO", "UNLIMITED"}

    if subscribed:
        user.telegram_subscribed = True
        if user.tier not in PAID_TIERS and user.tier == "REGISTERED":
            user.tier = "FREE"
        await db.commit()
        await db.refresh(user)
        return {"subscribed": True, "tier": user.tier}

    user.telegram_subscribed = False
    if user.tier not in PAID_TIERS and user.tier == "FREE":
        user.tier = "REGISTERED"
    await db.commit()

    channel_url = settings.telegram_channel_url
    if not channel_url:
        cid = settings.telegram_channel_id
        channel_url = (
            f"https://t.me/{cid.lstrip('@')}" if cid.startswith("@") else ""
        )
    return {"subscribed": False, "channel_url": channel_url}


@router.get("/status")
async def telegram_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current Telegram link status."""
    return {
        "linked": user.telegram_user_id is not None,
        "telegram_username": user.telegram_username,
        "subscribed": user.telegram_subscribed or False,
        "checked_at": user.telegram_checked_at,
    }


# ---------------------------------------------------------------------------
# Connect code (for linking Telegram from Settings)
# ---------------------------------------------------------------------------


@router.post("/connect-code")
async def create_connect_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a one-time code for linking Telegram to an authenticated user.

    Unlike /auth/telegram-code (used for anonymous login), this stores the
    authenticated user's ID so the webhook uses link_identity instead of
    find_or_create_user.
    """
    # Invalidate old unconfirmed codes for this user
    await db.execute(
        delete(TelegramAuthCode).where(
            TelegramAuthCode.ghost_user_id == user.id,
            TelegramAuthCode.confirmed == False,  # noqa: E712
        )
    )

    code = secrets.token_urlsafe(12)
    expires_at = datetime.utcnow() + timedelta(minutes=CONNECT_CODE_TTL_MINUTES)

    auth_code = TelegramAuthCode(
        code=code,
        ghost_user_id=user.id,
        expires_at=expires_at,
    )
    db.add(auth_code)
    await db.commit()

    bot_name = settings.telegram_bot_name
    deep_link = f"https://t.me/{bot_name}?start={code}"

    return {
        "code": code,
        "deep_link": deep_link,
        "expires_at": expires_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------


@router.post("/disconnect")
async def disconnect_telegram(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink Telegram from the current user account."""
    if not user.telegram_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram not linked",
        )

    # Clear Telegram fields on user
    user.telegram_user_id = None
    user.telegram_username = None
    user.telegram_subscribed = False

    # Remove Telegram auth identity
    await db.execute(
        delete(AuthIdentity).where(
            AuthIdentity.user_id == user.id,
            AuthIdentity.provider == "telegram",
        )
    )

    await db.commit()
    logger.info("[tg-disconnect] user=%s telegram unlinked", user.id)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Support reply from Telegram
# ---------------------------------------------------------------------------

# In-memory state: telegram_chat_id -> conversation_id (waiting for reply text)
_pending_support_replies: dict[str, str] = {}


async def _cb_support_reply_prompt(
    db: AsyncSession, cb_id: str, chat_id: str, conversation_id: str,
):
    """Admin pressed 'Ответить' — ask for reply text via ForceReply."""
    from app.models.feedback import SupportConversation

    # Verify conversation exists
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        await answer_callback_query(cb_id, settings.telegram_bot_token, text="Диалог не найден")
        return

    # Store pending state
    _pending_support_replies[chat_id] = conversation_id

    await answer_callback_query(cb_id, settings.telegram_bot_token, text="Введите ответ")
    await send_telegram_message(
        chat_id=chat_id,
        bot_token=settings.telegram_bot_token,
        text="✍️ Введите ответ клиенту:",
        reply_markup={"force_reply": True, "selective": True},
    )


async def _try_handle_support_reply(db: AsyncSession, chat_id: str, text: str) -> bool:
    """Check if this message is a pending support reply. Returns True if handled."""
    conversation_id = _pending_support_replies.pop(chat_id, None)
    if not conversation_id:
        return False

    from app.models.feedback import SupportConversation, SupportMessage
    from app.core.chat import chat_tracker

    # Find conversation
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        await send_telegram_message(
            chat_id=chat_id,
            bot_token=settings.telegram_bot_token,
            text="❌ Диалог не найден",
        )
        return True

    # Find admin user by telegram ID
    admin = await db.execute(
        select(User).where(User.telegram_user_id == chat_id)
    )
    admin_user = admin.scalar_one_or_none()
    if not admin_user:
        # Try matching by admin_telegram_ids
        admin_tg_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
        if chat_id not in admin_tg_ids:
            return True
        # Use first admin email user as sender
        admin_emails = [e.strip() for e in settings.admin_emails.split(",") if e.strip()]
        if admin_emails:
            r = await db.execute(select(User).where(User.email == admin_emails[0]))
            admin_user = r.scalar_one_or_none()
        if not admin_user:
            await send_telegram_message(
                chat_id=chat_id,
                bot_token=settings.telegram_bot_token,
                text="❌ Не удалось определить админа",
            )
            return True

    # Create message
    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="admin",
        sender_id=admin_user.id,
        text=text,
    )
    db.add(msg)
    conv.unread_user = (conv.unread_user or 0) + 1
    conv.updated_at = datetime.utcnow()
    if conv.status == "resolved":
        conv.status = "open"
    await db.commit()

    # Push via WebSocket
    try:
        await chat_tracker.send_to_user(conv.user_id, {
            "type": "new_message",
            "message": {
                "id": msg.id,
                "sender_type": "admin",
                "sender_id": admin_user.id,
                "text": msg.text,
                "image_key": None,
                "read_at": None,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            },
        })
    except Exception:
        pass

    # Schedule deferred notification (Telegram/Email) if unread after 2 min
    try:
        from app.core.arq_pool import managed_arq_pool
        pool = await managed_arq_pool.get_pool()
        if pool:
            await pool.enqueue_job(
                "task_notify_support_reply",
                str(msg.id), str(conv.user_id),
                _defer_by=timedelta(seconds=120),
            )
    except Exception:
        pass

    await send_telegram_message(
        chat_id=chat_id,
        bot_token=settings.telegram_bot_token,
        text="✅ Ответ отправлен",
    )
    return True
