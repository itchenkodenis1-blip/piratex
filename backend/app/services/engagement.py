"""User engagement automation — weekly digest, monthly reports, re-engagement."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_pool import get_redis

from app.config import settings
from app.models.job import Job, JobStatus
from app.models.trends import ProfileReel, TrackedProfile
from app.models.user import User
from app.services.telegram import send_telegram_message

_REENGAGEMENT_TTL = 86400  # 24 hours — prevent duplicate sends within a day

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Weekly digest: "Top trending reels"
# ---------------------------------------------------------------------------

async def get_top_trending_reels(db: AsyncSession, limit: int = 5) -> list[dict]:
    """Get top trending reels from the past 7 days by hot_score."""
    week_ago = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(ProfileReel)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.is_hidden == False,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            ProfileReel.published_at >= week_ago,
            ProfileReel.hot_score.isnot(None),
        ).order_by(ProfileReel.hot_score.desc()).limit(limit)
    )
    reels = result.scalars().all()
    return [
        {
            "url": r.url,
            "caption": (r.caption or "")[:80],
            "views": r.views or 0,
            "hot_score": round(r.hot_score or 0, 1),
            "platform_reel_id": r.platform_reel_id,
        }
        for r in reels
    ]


def _format_views(n: int) -> str:
    """Format view count: 1234567 → 1.2M, 12345 → 12.3K."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def format_weekly_digest(reels: list[dict]) -> str:
    """Format top reels as a Telegram message."""
    if not reels:
        return ""

    lines = ["Топ-5 залетевших рилсов этой недели:\n"]
    for i, r in enumerate(reels, 1):
        caption = r["caption"]
        if len(caption) > 60:
            caption = caption[:57] + "..."
        views = _format_views(r["views"])
        lines.append(f"{i}. {caption}\n   {views} просмотров\n   {r['url']}\n")

    lines.append(
        "\nПроанализируйте любой рилс в один клик:\n"
        f"{settings.app_url}"
    )
    return "\n".join(lines)


async def send_weekly_digest(db: AsyncSession) -> int:
    """Send weekly trending reels digest to all users with Telegram.

    Returns number of messages sent.
    """
    if not settings.telegram_bot_token:
        return 0

    reels = await get_top_trending_reels(db)
    if not reels:
        logger.info("[engagement] No trending reels for weekly digest")
        return 0

    text = format_weekly_digest(reels)

    # Get all users with Telegram (non-anonymous, subscribed)
    result = await db.execute(
        select(User.telegram_user_id).where(
            User.telegram_user_id.isnot(None),
            User.is_anonymous == False,  # noqa: E712
        )
    )
    tg_ids = [row[0] for row in result.all() if row[0]]

    sent = 0
    for tg_id in tg_ids:
        try:
            await send_telegram_message(tg_id, settings.telegram_bot_token, text)
            sent += 1
        except Exception:
            pass  # best-effort, don't block on individual failures

    logger.info("[engagement] Weekly digest sent to %d/%d users", sent, len(tg_ids))
    return sent


# ---------------------------------------------------------------------------
# Monthly personal reports
# ---------------------------------------------------------------------------

async def generate_monthly_report(db: AsyncSession, user: User) -> str | None:
    """Generate a personal monthly usage report for a user."""
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Count jobs this month
    result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.user_id == user.id,
            Job.status == JobStatus.COMPLETED,
            Job.created_at >= month_start,
        )
    )
    jobs_count = result.scalar() or 0

    if jobs_count == 0:
        return None  # No activity, skip report

    # Count total jobs all time
    total_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.user_id == user.id,
            Job.status == JobStatus.COMPLETED,
        )
    )
    total_jobs = total_result.scalar() or 0

    # Top platforms this month
    platform_result = await db.execute(
        select(Job.video_platform, func.count()).where(
            Job.user_id == user.id,
            Job.status == JobStatus.COMPLETED,
            Job.created_at >= month_start,
            Job.video_platform.isnot(None),
        ).group_by(Job.video_platform).order_by(func.count().desc()).limit(3)
    )
    top_platforms = [
        f"{row[0]} ({row[1]})" for row in platform_result.all()
    ]

    # Estimated time saved (~15 min per manual analysis)
    hours_saved = round(jobs_count * 15 / 60, 1)

    month_name = now.strftime("%B %Y")
    tier = user.tier or "FREE"

    text = (
        f"Ваш отчёт за {month_name}\n"
        f"{'=' * 25}\n\n"
        f"Анализов за месяц: {jobs_count}\n"
        f"Всего за всё время: {total_jobs}\n"
        f"Сэкономлено времени: ~{hours_saved} ч\n"
    )

    if top_platforms:
        text += f"Платформы: {', '.join(top_platforms)}\n"

    text += (
        f"\nТариф: {tier}\n\n"
        f"Продолжайте анализировать рилсы:\n"
        f"{settings.app_url}"
    )

    return text


async def send_monthly_reports(db: AsyncSession) -> int:
    """Send monthly reports to all active users.

    Returns number of reports sent.
    """
    if not settings.telegram_bot_token:
        return 0

    result = await db.execute(
        select(User).where(
            User.telegram_user_id.isnot(None),
            User.is_anonymous == False,  # noqa: E712
        )
    )
    users = result.scalars().all()

    sent = 0
    for user in users:
        try:
            report = await generate_monthly_report(db, user)
            if report:
                await send_telegram_message(
                    user.telegram_user_id, settings.telegram_bot_token, report,
                )
                sent += 1
        except Exception:
            pass

    logger.info("[engagement] Monthly reports sent to %d users", sent)
    return sent


# ---------------------------------------------------------------------------
# Re-engagement automation
# ---------------------------------------------------------------------------

async def send_reengagement_messages(db: AsyncSession) -> int:
    """Send re-engagement messages to inactive users.

    Tiers:
    - 5 days inactive: "3 new trends in your niche"
    - 14 days inactive: "We miss you + bonus"
    - 30 days inactive: personal message from team

    Returns number of messages sent.
    """
    if not settings.telegram_bot_token:
        return 0

    now = datetime.utcnow()
    sent = 0
    redis = await get_redis()

    # Get last job date for each user (non-anonymous with Telegram)
    last_activity_q = (
        select(
            Job.user_id,
            func.max(Job.created_at).label("last_job_at"),
        )
        .where(Job.status != JobStatus.FAILED)
        .group_by(Job.user_id)
        .subquery()
    )

    users_q = await db.execute(
        select(User, last_activity_q.c.last_job_at).outerjoin(
            last_activity_q, User.id == last_activity_q.c.user_id,
        ).where(
            User.telegram_user_id.isnot(None),
            User.is_anonymous == False,  # noqa: E712
        )
    )

    for user, last_job_at in users_q.all():
        if not last_job_at:
            continue  # Never had a job — onboarding, not re-engagement

        days_inactive = (now - last_job_at).days

        # Determine tier and message
        tier = None
        text = None
        if 5 <= days_inactive <= 6:
            tier = "d5"
            text = (
                "Привет! За последние дни появилось несколько трендовых рилсов.\n\n"
                "Загляните, чтобы не пропустить интересные форматы:\n"
                f"{settings.app_url}"
            )
        elif 14 <= days_inactive <= 15:
            tier = "d14"
            text = (
                "Давно вас не видели в Piratex.ai!\n\n"
                "Пока вас не было, мы добавили новые возможности. "
                "Зайдите и проанализируйте рилс — это займёт 2 минуты:\n"
                f"{settings.app_url}"
            )
        elif 30 <= days_inactive <= 31:
            tier = "d30"
            text = (
                "Добрый день! Это команда Piratex.ai.\n\n"
                "Заметили, что вы давно не заходили. "
                "Если у вас есть вопросы или пожелания — напишите нам, "
                "мы всегда на связи.\n\n"
                f"Вернуться: {settings.app_url}"
            )

        if text and tier:
            # Deduplicate: max one message per user per tier per 24h
            dedup_key = f"reengage:{user.id}:{tier}"
            if redis and await redis.set(dedup_key, "1", nx=True, ex=_REENGAGEMENT_TTL):
                try:
                    await send_telegram_message(
                        user.telegram_user_id, settings.telegram_bot_token, text,
                    )
                    sent += 1
                except Exception:
                    # Remove dedup key so retry is possible next cycle
                    await redis.delete(dedup_key)
            elif not redis:
                # Fallback without Redis — send anyway (better than silent skip)
                try:
                    await send_telegram_message(
                        user.telegram_user_id, settings.telegram_bot_token, text,
                    )
                    sent += 1
                except Exception:
                    pass

    logger.info("[engagement] Re-engagement messages sent: %d", sent)
    return sent
