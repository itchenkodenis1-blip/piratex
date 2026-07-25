"""Onboarding Drip — behaviour-based notification sequence for new users.

Drip steps:
  1. no_analysis_24h — user registered but no analysis after 24h → nudge with trending URL
  2. first_analysis   — first analysis completed → highlight hook score
  3. free_limit       — FREE 3/3 limit reached → upgrade CTA
  4. no_profile_48h   — no niches configured after 48h → nudge to set up profile

Steps 1 and 4 are checked by a scheduled loop (hourly).
Steps 2 and 3 are triggered by event hooks in tasks.py and job_creator.py.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis_pool import get_redis
from app.models.job import Job, JobStatus
from app.models.user import User, UserSettings
from app.services.telegram import send_telegram_message

logger = logging.getLogger(__name__)

_STEP_TTL = 86400 * 30  # 30 days — don't re-send a step within a month


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

async def _is_step_sent(user_id: str, step: str) -> bool:
    redis = await get_redis()
    if not redis:
        return False
    return bool(await redis.exists(f"onboarding:{user_id}:{step}"))


async def _mark_step_sent(user_id: str, step: str) -> None:
    redis = await get_redis()
    if redis:
        await redis.set(f"onboarding:{user_id}:{step}", "1", ex=_STEP_TTL)


# ---------------------------------------------------------------------------
# Individual drip steps
# ---------------------------------------------------------------------------

async def drip_first_analysis(db: AsyncSession, user: User, job: Job) -> bool:
    """Called from tasks.py after first analysis completes.

    Sends a message highlighting the hook score or key metric.
    Returns True if message sent.
    """
    if not user.telegram_user_id or not settings.telegram_bot_token:
        return False

    if await _is_step_sent(user.id, "first_analysis"):
        return False

    # Check this is actually first completed job
    result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.user_id == user.id,
            Job.status == JobStatus.COMPLETED,
        )
    )
    completed_count = result.scalar() or 0
    if completed_count > 1:
        # Not first — skip
        await _mark_step_sent(user.id, "first_analysis")
        return False

    # Build message from job data
    summary = job.adaptation_summary or {}
    hook_score = summary.get("hook_score") or summary.get("hookScore")
    author = job.video_author or "автор"
    platform = job.video_platform or ""

    lines = [
        "\U0001f389 <b>\u041f\u0435\u0440\u0432\u044b\u0439 \u0430\u043d\u0430\u043b\u0438\u0437 \u0433\u043e\u0442\u043e\u0432!</b>",
        "",
    ]

    if hook_score:
        lines.append(
            f"\U0001f3af \u0425\u0443\u043a-\u0441\u043a\u043e\u0440: <b>{hook_score}/100</b>"
        )
        if isinstance(hook_score, (int, float)) and hook_score >= 70:
            lines.append("\u0421\u0438\u043b\u044c\u043d\u044b\u0439 \u0445\u0443\u043a \u2014 \u0441\u0442\u043e\u0438\u0442 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c \u043a\u0430\u043a \u0440\u0435\u0444\u0435\u0440\u0435\u043d\u0441!")
        elif isinstance(hook_score, (int, float)) and hook_score < 40:
            lines.append("\u0425\u0443\u043a \u0441\u043b\u0430\u0431\u044b\u0439 \u2014 \u043f\u043e\u0441\u043c\u043e\u0442\u0440\u0438\u0442\u0435 \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u0438 \u0432 \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0438")

    lines.append("")
    lines.append(
        "\U0001f4a1 \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0440\u0430\u0437\u043e\u0431\u0440\u0430\u0442\u044c \u0435\u0449\u0451 \u043e\u0434\u0438\u043d \u0440\u0438\u043b\u0441 \u2014"
        " \u0441\u0440\u0430\u0432\u043d\u0438\u0442\u0435 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442\u044b!"
    )
    lines.append(f"\n{settings.app_url}")

    text = "\n".join(lines)

    try:
        await send_telegram_message(
            user.telegram_user_id, settings.telegram_bot_token, text,
            parse_mode="HTML",
        )
        await _mark_step_sent(user.id, "first_analysis")
        logger.info("[onboarding] first_analysis drip sent to %s", user.id[:8])
        return True
    except Exception:
        logger.debug("[onboarding] Failed to send first_analysis drip", exc_info=True)
        return False


async def drip_free_limit_reached(user: User) -> bool:
    """Called from job_creator.py when FREE user hits 3/3 monthly limit.

    Returns True if message sent.
    """
    if not user.telegram_user_id or not settings.telegram_bot_token:
        return False

    if await _is_step_sent(user.id, "free_limit"):
        return False

    text = (
        "\U0001f6a8 <b>\u041b\u0438\u043c\u0438\u0442 \u0430\u043d\u0430\u043b\u0438\u0437\u043e\u0432 \u0438\u0441\u0447\u0435\u0440\u043f\u0430\u043d</b>\n"
        "\n"
        "\u0412\u044b \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043b\u0438 \u0432\u0441\u0435 3 \u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0445 \u0430\u043d\u0430\u043b\u0438\u0437\u0430 \u0432 \u044d\u0442\u043e\u043c \u043c\u0435\u0441\u044f\u0446\u0435.\n"
        "\n"
        "\U0001f680 <b>START</b> \u2014 50 \u0430\u043d\u0430\u043b\u0438\u0437\u043e\u0432/\u043c\u0435\u0441 \u0437\u0430 \u20bd2000\n"
        "\u2022 \u0421\u0446\u0435\u043d\u0430\u0440\u0438\u0438 \u0438 \u043e\u043f\u0438\u0441\u0430\u043d\u0438\u044f \u043f\u043e\u0434 \u0432\u0430\u0441\n"
        "\u2022 \u041e\u0442\u0441\u043b\u0435\u0436\u0438\u0432\u0430\u043d\u0438\u0435 \u0430\u0432\u0442\u043e\u0440\u043e\u0432\n"
        "\u2022 \u0420\u0430\u0434\u0430\u0440 \u0442\u0440\u0435\u043d\u0434\u043e\u0432\n"
        f'\n<a href="{settings.app_url}/pricing">\u0412\u044b\u0431\u0440\u0430\u0442\u044c \u0442\u0430\u0440\u0438\u0444 \u2192</a>'
    )

    try:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "\U0001f680 \u0412\u044b\u0431\u0440\u0430\u0442\u044c \u0442\u0430\u0440\u0438\u0444", "url": f"{settings.app_url}/pricing"},
            ]]
        }
        await send_telegram_message(
            user.telegram_user_id, settings.telegram_bot_token, text,
            parse_mode="HTML", reply_markup=reply_markup,
        )
        await _mark_step_sent(user.id, "free_limit")
        logger.info("[onboarding] free_limit drip sent to %s", user.id[:8])
        return True
    except Exception:
        logger.debug("[onboarding] Failed to send free_limit drip", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Scheduled checks (run hourly from engagement loop)
# ---------------------------------------------------------------------------

async def check_scheduled_drips(db: AsyncSession) -> int:
    """Check and send time-based drip messages.

    - no_analysis_24h: registered 24-48h ago, 0 completed analyses
    - no_profile_48h: registered 48-72h ago, no niches configured

    Returns number of messages sent.
    """
    if not settings.telegram_bot_token:
        return 0

    now = datetime.utcnow()
    sent = 0

    # --- Step: no_analysis_24h ---
    # Users registered 24-48h ago with Telegram but 0 completed jobs
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    # Subquery: users with at least 1 completed job
    has_completed = (
        select(Job.user_id)
        .where(Job.status == JobStatus.COMPLETED)
        .group_by(Job.user_id)
        .subquery()
    )

    result = await db.execute(
        select(User)
        .outerjoin(has_completed, User.id == has_completed.c.user_id)
        .where(
            User.telegram_user_id.isnot(None),
            User.is_anonymous == False,  # noqa: E712
            User.created_at >= cutoff_48h,
            User.created_at < cutoff_24h,
            has_completed.c.user_id.is_(None),  # no completed jobs
        )
    )
    no_analysis_users = result.scalars().all()

    # Pre-fetch one trending reel for the nudge (same for all users)
    from app.services.morning_brief import get_trending_by_niches
    from app.services.telegram import escape_html

    trending = await get_trending_by_niches(db, ["ai", "marketing", "business"], hours=48, limit=1)
    if trending:
        _reel, _profile = trending[0]
        suggest_url = _reel.url or settings.app_url
        suggest_text = f"@{escape_html(_profile.username)}" if _profile.username else "\u043f\u043e\u043f\u0443\u043b\u044f\u0440\u043d\u044b\u0439 \u0440\u0438\u043b\u0441"
    else:
        suggest_url = settings.app_url
        suggest_text = "\u043b\u044e\u0431\u043e\u0439 \u0440\u0438\u043b\u0441"

    for user in no_analysis_users:
        if await _is_step_sent(user.id, "no_analysis_24h"):
            continue

        text = (
            "\U0001f44b <b>\u041d\u0435 \u0443\u0441\u043f\u0435\u043b\u0438 \u043f\u043e\u043f\u0440\u043e\u0431\u043e\u0432\u0430\u0442\u044c?</b>\n"
            "\n"
            f"\u0420\u0430\u0437\u0431\u0435\u0440\u0438\u0442\u0435 {suggest_text} \u2014 \u044d\u0442\u043e \u0437\u0430\u0439\u043c\u0451\u0442 30 \u0441\u0435\u043a\u0443\u043d\u0434.\n"
            "\u041f\u0438\u0440\u0430\u0442\u0435\u043a\u0441 \u043f\u043e\u043a\u0430\u0436\u0435\u0442 \u0445\u0443\u043a, \u043d\u0438\u0448\u0443, \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0443 \u0438 \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0439."
            f"\n\n{suggest_url}"
        )

        try:
            await send_telegram_message(
                user.telegram_user_id, settings.telegram_bot_token, text,
                parse_mode="HTML",
            )
            await _mark_step_sent(user.id, "no_analysis_24h")
            sent += 1
        except Exception:
            pass

    # --- Step: no_profile_48h ---
    # Users registered 48-72h ago with no niches configured
    cutoff_72h = now - timedelta(hours=72)

    result = await db.execute(
        select(User, UserSettings)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.telegram_user_id.isnot(None),
            User.is_anonymous == False,  # noqa: E712
            User.created_at >= cutoff_72h,
            User.created_at < cutoff_48h,
        )
    )

    for user, user_settings in result.all():
        if await _is_step_sent(user.id, "no_profile_48h"):
            continue

        # Check if niches are set
        has_niches = False
        if user_settings and user_settings.profile_json:
            niches = user_settings.profile_json.get("niches")
            if niches and len(niches) > 0:
                has_niches = True

        if has_niches:
            # Already configured — mark as done
            await _mark_step_sent(user.id, "no_profile_48h")
            continue

        text = (
            "\u2699\ufe0f <b>\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u0442\u0435 \u043d\u0438\u0448\u0438 \u0437\u0430 30 \u0441\u0435\u043a\u0443\u043d\u0434</b>\n"
            "\n"
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u0432\u043e\u0438 \u043d\u0438\u0448\u0438 \u2014 \u0438 \u0440\u0430\u0434\u0430\u0440 \u0442\u0440\u0435\u043d\u0434\u043e\u0432 \u043d\u0430\u0447\u043d\u0451\u0442\n"
            "\u043f\u0440\u0438\u0441\u044b\u043b\u0430\u0442\u044c \u0437\u0430\u043b\u0451\u0442\u044b \u0438\u043c\u0435\u043d\u043d\u043e \u0432 \u0432\u0430\u0448\u0435\u0439 \u0442\u0435\u043c\u0430\u0442\u0438\u043a\u0435."
            f'\n\n<a href="{settings.app_url}/settings">\u041d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u043f\u0440\u043e\u0444\u0438\u043b\u044c \u2192</a>'
        )

        try:
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "\u2699\ufe0f \u041d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c", "url": f"{settings.app_url}/settings"},
                ]]
            }
            await send_telegram_message(
                user.telegram_user_id, settings.telegram_bot_token, text,
                parse_mode="HTML", reply_markup=reply_markup,
            )
            await _mark_step_sent(user.id, "no_profile_48h")
            sent += 1
        except Exception:
            pass

    logger.info("[onboarding] Scheduled drips sent: %d", sent)
    return sent
