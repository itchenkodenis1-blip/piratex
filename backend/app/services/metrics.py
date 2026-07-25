"""Business metrics calculation and daily digest for admin alerts."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.job import Job, JobStatus
from app.models.subscription import Payment, Subscription
from app.models.user import User
from app.services.telegram import send_telegram_message

logger = logging.getLogger(__name__)


async def calculate_daily_metrics(db: AsyncSession) -> dict:
    """Calculate key business metrics for the last 24 hours."""
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # --- New registrations (24h) ---
    reg_result = await db.execute(
        select(func.count()).select_from(User).where(
            User.created_at >= yesterday,
            User.is_anonymous == False,  # noqa: E712
        )
    )
    new_registrations = reg_result.scalar() or 0

    # --- Total users ---
    total_users_result = await db.execute(
        select(func.count()).select_from(User).where(
            User.is_anonymous == False,  # noqa: E712
        )
    )
    total_users = total_users_result.scalar() or 0

    # --- Paid users (active subscriptions) ---
    paid_result = await db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.status.in_(["active", "cancelled"]),
            Subscription.current_period_end > now,
        )
    )
    paid_users = paid_result.scalar() or 0

    # --- Jobs completed (24h) ---
    jobs_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status == JobStatus.COMPLETED,
            Job.created_at >= yesterday,
        )
    )
    jobs_24h = jobs_result.scalar() or 0

    # --- Jobs failed (24h) ---
    failed_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status == JobStatus.FAILED,
            Job.created_at >= yesterday,
        )
    )
    jobs_failed_24h = failed_result.scalar() or 0

    # --- Monthly jobs ---
    monthly_jobs_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status == JobStatus.COMPLETED,
            Job.created_at >= month_start,
        )
    )
    monthly_jobs = monthly_jobs_result.scalar() or 0

    # --- MRR (Monthly Recurring Revenue) ---
    mrr_result = await db.execute(
        select(func.coalesce(func.sum(Subscription.amount_kopecks), 0)).where(
            Subscription.status == "active",
            Subscription.billing_interval == "monthly",
        )
    )
    mrr_monthly = mrr_result.scalar() or 0

    # Add yearly subscribers prorated to monthly
    mrr_yearly_result = await db.execute(
        select(func.coalesce(func.sum(Subscription.amount_kopecks / 12), 0)).where(
            Subscription.status == "active",
            Subscription.billing_interval == "yearly",
        )
    )
    mrr_yearly = int(mrr_yearly_result.scalar() or 0)
    mrr_total = mrr_monthly + mrr_yearly

    # --- Revenue (24h) ---
    revenue_result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount_kopecks), 0)).where(
            Payment.status == "succeeded",
            Payment.paid_at >= yesterday,
        )
    )
    revenue_24h = revenue_result.scalar() or 0

    # --- Revenue (month) ---
    revenue_month_result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount_kopecks), 0)).where(
            Payment.status == "succeeded",
            Payment.paid_at >= month_start,
        )
    )
    revenue_month = revenue_month_result.scalar() or 0

    # --- New subscriptions (24h) ---
    new_subs_result = await db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.created_at >= yesterday,
        )
    )
    new_subscriptions = new_subs_result.scalar() or 0

    # --- Churned subscriptions (24h) ---
    churned_result = await db.execute(
        select(func.count()).select_from(Subscription).where(
            Subscription.status.in_(["cancelled", "expired"]),
            Subscription.updated_at >= yesterday,
        )
    )
    churned = churned_result.scalar() or 0

    # --- Tier breakdown ---
    tier_result = await db.execute(
        select(User.tier, func.count()).where(
            User.is_anonymous == False,  # noqa: E712
        ).group_by(User.tier)
    )
    tier_breakdown = {row[0]: row[1] for row in tier_result.all()}

    return {
        "new_registrations": new_registrations,
        "total_users": total_users,
        "paid_users": paid_users,
        "jobs_24h": jobs_24h,
        "jobs_failed_24h": jobs_failed_24h,
        "monthly_jobs": monthly_jobs,
        "mrr_total_kopecks": mrr_total,
        "revenue_24h_kopecks": revenue_24h,
        "revenue_month_kopecks": revenue_month,
        "new_subscriptions": new_subscriptions,
        "churned": churned,
        "tier_breakdown": tier_breakdown,
    }


def format_metrics_digest(metrics: dict) -> str:
    """Format metrics as a Telegram-friendly text message."""
    now = datetime.utcnow()
    date_str = now.strftime("%d.%m.%Y")

    mrr_rub = metrics["mrr_total_kopecks"] // 100
    rev_24h = metrics["revenue_24h_kopecks"] // 100
    rev_month = metrics["revenue_month_kopecks"] // 100

    tier = metrics.get("tier_breakdown", {})
    tier_lines = []
    for t in ["FREE", "START", "PRO", "UNLIMITED"]:
        count = tier.get(t, 0)
        if count:
            tier_lines.append(f"  {t}: {count}")

    fail_rate = ""
    total = metrics["jobs_24h"] + metrics["jobs_failed_24h"]
    if total > 0:
        pct = round(metrics["jobs_failed_24h"] / total * 100, 1)
        fail_rate = f" ({pct}% ошибок)"

    text = (
        f"Piratex.ai — Дайджест {date_str}\n"
        f"{'=' * 30}\n\n"
        f"Пользователи:\n"
        f"  Новые (24ч): {metrics['new_registrations']}\n"
        f"  Всего: {metrics['total_users']}\n"
        f"  Платные: {metrics['paid_users']}\n\n"
        f"Тарифы:\n"
        + ("\n".join(tier_lines) + "\n\n" if tier_lines else "  —\n\n")
        + f"Анализы (24ч): {metrics['jobs_24h']}{fail_rate}\n"
        f"  За месяц: {metrics['monthly_jobs']}\n\n"
        f"Финансы:\n"
        f"  MRR: {mrr_rub:,} ₽\n"
        f"  Выручка (24ч): {rev_24h:,} ₽\n"
        f"  Выручка (мес): {rev_month:,} ₽\n"
        f"  Новые подписки (24ч): {metrics['new_subscriptions']}\n"
        f"  Отток (24ч): {metrics['churned']}\n"
    )
    return text


async def send_daily_digest(db: AsyncSession) -> bool:
    """Calculate metrics and send daily digest to admin Telegram IDs."""
    if not settings.admin_telegram_ids or not settings.telegram_bot_token:
        logger.debug("Daily digest skipped: no admin_telegram_ids or bot token configured")
        return False

    metrics = await calculate_daily_metrics(db)
    text = format_metrics_digest(metrics)

    admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
    sent = False
    for admin_id in admin_ids:
        try:
            await send_telegram_message(admin_id, settings.telegram_bot_token, text)
            sent = True
        except Exception as e:
            logger.error("Failed to send digest to admin %s: %s", admin_id, e)

    return sent


async def calculate_period_metrics(db: AsyncSession, since: datetime) -> dict:
    """Calculate metrics for a given period (since → now)."""
    now = datetime.utcnow()

    # Registrations
    reg_result = await db.execute(
        select(func.count()).select_from(User).where(
            User.created_at >= since,
            User.is_anonymous == False,  # noqa: E712
        )
    )
    registrations = reg_result.scalar() or 0

    # Registration breakdown by auth provider
    auth_result = await db.execute(
        select(User.auth_provider, func.count()).where(
            User.created_at >= since,
            User.is_anonymous == False,  # noqa: E712
        ).group_by(User.auth_provider)
    )
    auth_breakdown = {row[0] or "unknown": row[1] for row in auth_result.all()}

    # Jobs completed
    jobs_completed_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status == JobStatus.COMPLETED,
            Job.created_at >= since,
        )
    )
    jobs_completed = jobs_completed_result.scalar() or 0

    # Jobs failed
    jobs_failed_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status == JobStatus.FAILED,
            Job.created_at >= since,
        )
    )
    jobs_failed = jobs_failed_result.scalar() or 0

    # Jobs in progress (pending/processing right now)
    jobs_in_progress_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]),
            Job.created_at >= since,
        )
    )
    jobs_in_progress = jobs_in_progress_result.scalar() or 0

    # Platform breakdown (completed + failed jobs)
    platform_result = await db.execute(
        select(Job.video_platform, func.count()).where(
            Job.created_at >= since,
            Job.video_platform.isnot(None),
        ).group_by(Job.video_platform)
    )
    platform_breakdown = {row[0]: row[1] for row in platform_result.all()}

    # Source breakdown (web, telegram, radar)
    source_result = await db.execute(
        select(Job.source, func.count()).where(
            Job.created_at >= since,
        ).group_by(Job.source)
    )
    source_breakdown = {row[0] or "web": row[1] for row in source_result.all()}

    # Average processing time (completed jobs only)
    avg_time_result = await db.execute(
        select(
            func.avg(func.extract("epoch", Job.completed_at) - func.extract("epoch", Job.created_at))
        ).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at.isnot(None),
            Job.created_at >= since,
        )
    )
    avg_processing_seconds = avg_time_result.scalar()

    # AI costs (from cost_breakdown JSON)
    cost_result = await db.execute(
        select(Job.cost_breakdown).where(
            Job.created_at >= since,
            Job.cost_breakdown.isnot(None),
        )
    )
    total_cost_usd = 0.0
    for (breakdown,) in cost_result.all():
        if isinstance(breakdown, dict):
            total_cost_usd += breakdown.get("total_usd", 0.0)

    # Payments succeeded
    payments_result = await db.execute(
        select(func.count()).select_from(Payment).where(
            Payment.status == "succeeded",
            Payment.paid_at >= since,
        )
    )
    payments = payments_result.scalar() or 0

    # Abandoned checkouts (pending payments)
    abandoned_result = await db.execute(
        select(func.count()).select_from(Payment).where(
            Payment.status == "pending",
            Payment.created_at >= since,
        )
    )
    abandoned_checkouts = abandoned_result.scalar() or 0

    # Revenue
    revenue_result = await db.execute(
        select(func.coalesce(func.sum(Payment.amount_kopecks), 0)).where(
            Payment.status == "succeeded",
            Payment.paid_at >= since,
        )
    )
    revenue_kopecks = revenue_result.scalar() or 0

    return {
        "registrations": registrations,
        "auth_breakdown": auth_breakdown,
        "jobs_completed": jobs_completed,
        "jobs_failed": jobs_failed,
        "jobs_in_progress": jobs_in_progress,
        "platform_breakdown": platform_breakdown,
        "source_breakdown": source_breakdown,
        "avg_processing_seconds": avg_processing_seconds,
        "total_cost_usd": total_cost_usd,
        "payments": payments,
        "abandoned_checkouts": abandoned_checkouts,
        "revenue_kopecks": revenue_kopecks,
    }


def _format_auth_breakdown(auth: dict) -> str:
    """Format auth provider breakdown as compact string."""
    abbrev = {"telegram": "TG", "email": "Email", "yandex": "Ya", "vk": "VK", "google": "G", "phone": "Tel"}
    parts = []
    for provider, count in sorted(auth.items(), key=lambda x: -x[1]):
        label = abbrev.get(provider, provider)
        parts.append(f"{label}: {count}")
    return ", ".join(parts)


def _format_platform_breakdown(platforms: dict) -> str:
    """Format platform breakdown as compact string."""
    abbrev = {"instagram": "IG", "tiktok": "TT", "youtube": "YT"}
    parts = []
    for platform, count in sorted(platforms.items(), key=lambda x: -x[1]):
        label = abbrev.get(platform, platform)
        parts.append(f"{label}: {count}")
    return " | ".join(parts)


def _format_source_breakdown(sources: dict) -> str:
    """Format source breakdown as compact string."""
    parts = []
    for source, count in sorted(sources.items(), key=lambda x: -x[1]):
        parts.append(f"{source} {count}")
    return ", ".join(parts)


def _format_duration(seconds: float | None) -> str:
    """Format seconds as 'Xm Ys'."""
    if not seconds:
        return "—"
    m, s = divmod(int(seconds), 60)
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _format_period_report(m: dict) -> str:
    """Format period metrics into a report body (shared by hourly and daily)."""
    lines = []

    # Registrations
    reg_line = f"👤 Регистрации: {m['registrations']}"
    if m["auth_breakdown"]:
        reg_line += f" ({_format_auth_breakdown(m['auth_breakdown'])})"
    lines.append(reg_line)

    # Analyses
    total_jobs = m["jobs_completed"] + m["jobs_failed"] + m["jobs_in_progress"]
    analysis_line = f"🔬 Анализов: {total_jobs} → ✅ {m['jobs_completed']}"
    if m["jobs_failed"]:
        analysis_line += f"  ❌ {m['jobs_failed']}"
    if m["jobs_in_progress"]:
        analysis_line += f"  ⏳ {m['jobs_in_progress']}"
    lines.append(analysis_line)

    # Platform breakdown
    if m["platform_breakdown"]:
        lines.append(f"   {_format_platform_breakdown(m['platform_breakdown'])}")

    # Average processing time
    if m["avg_processing_seconds"]:
        lines.append(f"   ⏱ Среднее: {_format_duration(m['avg_processing_seconds'])}")

    # Source breakdown
    if m["source_breakdown"]:
        lines.append(f"📡 Источник: {_format_source_breakdown(m['source_breakdown'])}")

    # Payments
    pay_line = f"💳 Оплаты: {m['payments']}"
    if m["abandoned_checkouts"]:
        pay_line += f" | Брошено: {m['abandoned_checkouts']}"
    lines.append(pay_line)

    # AI costs
    if m["total_cost_usd"] > 0:
        lines.append(f"🤖 Расход AI: ${m['total_cost_usd']:.2f}")

    return "\n".join(lines)


async def send_hourly_stats(db: AsyncSession) -> bool:
    """Send hourly mini-summary to admin Telegram IDs."""
    if not settings.admin_telegram_ids or not settings.telegram_bot_token:
        return False

    since = datetime.utcnow() - timedelta(hours=1)
    m = await calculate_period_metrics(db, since)

    # Skip if nothing happened
    total_jobs = m["jobs_completed"] + m["jobs_failed"] + m["jobs_in_progress"]
    if all(v == 0 for v in (m["registrations"], total_jobs, m["payments"])):
        return False

    text = f"📊 <b>За последний час</b>\n\n{_format_period_report(m)}"

    admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
    sent = False
    for admin_id in admin_ids:
        try:
            await send_telegram_message(admin_id, settings.telegram_bot_token, text, parse_mode="HTML")
            sent = True
        except Exception as e:
            logger.error("Failed to send hourly stats to admin %s: %s", admin_id, e)
    return sent


async def send_daily_summary(db: AsyncSession) -> bool:
    """Send end-of-day summary (midnight MSK) to admin Telegram IDs."""
    if not settings.admin_telegram_ids or not settings.telegram_bot_token:
        return False

    # "Today" in MSK: 00:00 MSK → 21:00 UTC previous day
    now_utc = datetime.utcnow()
    msk_offset = timedelta(hours=3)
    now_msk = now_utc + msk_offset
    day_start_msk = now_msk.replace(hour=0, minute=0, second=0, microsecond=0)
    since_utc = day_start_msk - msk_offset  # start of MSK day in UTC

    m = await calculate_period_metrics(db, since_utc)
    date_str = now_msk.strftime("%d.%m.%Y")
    revenue_rub = m["revenue_kopecks"] // 100

    text = f"📈 <b>Итоги дня {date_str}</b>\n\n{_format_period_report(m)}"
    if revenue_rub:
        text += f"\n💰 Выручка: {revenue_rub:,} ₽"

    admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
    sent = False
    for admin_id in admin_ids:
        try:
            await send_telegram_message(admin_id, settings.telegram_bot_token, text, parse_mode="HTML")
            sent = True
        except Exception as e:
            logger.error("Failed to send daily summary to admin %s: %s", admin_id, e)
    return sent


async def send_alert(message: str) -> None:
    """Send an alert message to all admin Telegram IDs."""
    if not settings.admin_telegram_ids or not settings.telegram_bot_token:
        return

    admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
    for admin_id in admin_ids:
        try:
            await send_telegram_message(admin_id, settings.telegram_bot_token, message)
        except Exception:
            pass
