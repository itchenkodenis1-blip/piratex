import html
import logging

import httpx

logger = logging.getLogger(__name__)


class TelegramAPIError(Exception):
    """Raised when Telegram API returns a transient error."""


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return html.escape(text, quote=False)


async def check_channel_membership(
    telegram_user_id: str | int, bot_token: str, channel_id: str,
) -> bool:
    """
    Check if user is subscribed to channel via getChatMember API.

    Returns True if member/admin/creator/restricted-with-is_member.
    Returns False on 'left', 'kicked'.
    Raises TelegramAPIError on transient failures (429, 5xx, network).
    """
    url = f"https://api.telegram.org/bot{bot_token}/getChatMember"
    params = {"chat_id": channel_id, "user_id": str(telegram_user_id)}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        if resp.status_code in (429, 500, 502, 503, 504):
            raise TelegramAPIError(f"Telegram API returned {resp.status_code}")
        if resp.status_code != 200:
            return False
        result = resp.json()
        if not result.get("ok"):
            return False
        member = result.get("result", {})
        member_status = member.get("status", "")
        if member_status == "restricted":
            return member.get("is_member", False)
        return member_status in ("member", "administrator", "creator")


async def send_telegram_message(
    chat_id: str | int, bot_token: str, text: str,
    *, parse_mode: str | None = None,
    reply_markup: dict | None = None,
) -> dict | None:
    """Send a message to a Telegram user via Bot API.

    Returns the full API result dict (containing message_id etc.) on success,
    or None on failure.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload: dict = {"chat_id": str(chat_id), "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data.get("result")
        logger.warning("sendMessage failed: status=%s", resp.status_code)
        return None


async def send_telegram_photo(
    chat_id: str | int, bot_token: str, photo_url: str,
    caption: str = "",
    *, parse_mode: str | None = None,
    reply_markup: dict | None = None,
) -> dict | None:
    """Send a photo with caption via Bot API.

    Returns the full API result dict on success, or None on failure.
    Falls back to sendMessage if photo delivery fails.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    payload: dict = {"chat_id": str(chat_id), "photo": photo_url}
    if caption:
        payload["caption"] = caption
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data.get("result")
        logger.warning("sendPhoto failed (status=%s), falling back to sendMessage", resp.status_code)

    # Fallback: send as text message
    return await send_telegram_message(
        chat_id, bot_token, caption,
        parse_mode=parse_mode, reply_markup=reply_markup,
    )


async def edit_telegram_message(
    chat_id: str | int, message_id: int, bot_token: str, text: str,
    *, parse_mode: str | None = None,
    reply_markup: dict | None = None,
) -> bool:
    """Edit an existing message via editMessageText API."""
    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
    payload: dict = {
        "chat_id": str(chat_id),
        "message_id": message_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.warning("editMessageText failed: status=%s", resp.status_code)
        return resp.status_code == 200


async def answer_callback_query(
    callback_query_id: str, bot_token: str,
    *, text: str | None = None,
    show_alert: bool = False,
) -> bool:
    """Answer a callback query (acknowledge button press)."""
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    payload: dict = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    if show_alert:
        payload["show_alert"] = True

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        return resp.status_code == 200


# ---------------------------------------------------------------------------
# Telegram message formatting helpers (shared by webhook + workers)
# ---------------------------------------------------------------------------


def format_result_card(job) -> str:
    """Format analysis result as HTML card text."""
    author = escape_html(job.video_author or "unknown")
    platform = escape_html(job.video_platform or "")

    summary = job.adaptation_summary or {}
    hook_score = summary.get("primary_hook_score", "\u2014")
    niche = summary.get("niche", "")

    lines = [
        "\U0001f3ac <b>Анализ готов!</b>",
        "",
        f"\U0001f464 @{author} \u00b7 {platform}",
        f"\U0001f3af Hook score: {hook_score}/100",
    ]
    if niche:
        lines.append(f"\U0001f4ca Ниша: {escape_html(niche)}")

    return "\n".join(lines)


def format_result_keyboard(job, app_url: str) -> dict:
    """Build inline keyboard for result card."""
    share_url = f"{app_url}/share/{job.share_token}" if job.share_token else app_url
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f4dd Сценарий", "callback_data": f"script:{job.id}"},
                {"text": "\U0001f4f1 Пост", "callback_data": f"post:{job.id}"},
            ],
            [
                {"text": "\U0001f517 На сайте", "url": share_url},
            ],
        ]
    }


async def notify_admin_job_failure(
    job,
    raw_error: str,
    *,
    user_email: str | None = None,
) -> None:
    """Send job failure details to admin Telegram IDs.

    Includes: user email (masked), URL, platform, raw error.
    Best-effort — never raises.
    """
    from app.config import settings

    if not settings.admin_telegram_ids or not settings.telegram_bot_token:
        return

    try:
        platform = job.video_platform or "unknown"
        url = job.url or "—"
        job_id_short = str(job.id)[:8]

        # Mask email for privacy
        masked = "anonymous"
        if user_email:
            local, _, domain = user_email.partition("@")
            if domain:
                masked = f"{local[:3]}***@{domain}" if len(local) > 2 else f"{local[0]}***@{domain}"

        lines = [
            "🔴 Ошибка анализа",
            "",
            f"👤 {masked}",
            f"🔗 {url}",
            f"📱 {platform}",
            f"🆔 {job_id_short}",
            "",
            f"❌ {raw_error[:500]}",
        ]
        text = "\n".join(lines)

        admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
        for tid in admin_ids:
            await send_telegram_message(tid, settings.telegram_bot_token, text)
    except Exception as e:
        logger.warning("Failed to send admin job failure alert: %s", e)


async def set_bot_commands(bot_token: str) -> bool:
    """Register bot commands with BotFather (setMyCommands)."""
    url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
    commands = [
        {"command": "start", "description": "Начать работу"},
        {"command": "help", "description": "Список возможностей"},
        {"command": "status", "description": "Тариф и остаток анализов"},
    ]
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"commands": commands})
        return resp.status_code == 200
