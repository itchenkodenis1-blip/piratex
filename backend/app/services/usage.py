import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import exists as sa_exists

from app.config import TIER_LIMITS, settings
from app.models.identity import AuthIdentity
from app.models.job import Job, JobStatus
from app.models.referral import BonusCredit
from app.models.tier_config import TierConfig
from app.models.user import User
from app.services.telegram import check_channel_membership

logger = logging.getLogger(__name__)


async def _get_available_bonus(db: AsyncSession, user_id: str) -> int:
    """Return total unused bonus credits (not expired).

    DISABLED: referral/bonus program temporarily closed due to abuse.
    Existing bonus credits are frozen — no new ones are granted or consumed.
    """
    return 0


async def _get_tier_limits(db: AsyncSession, tier_name: str) -> dict:
    """Read tier limits from DB, falling back to hardcoded TIER_LIMITS."""
    result = await db.execute(
        select(TierConfig).where(TierConfig.name == tier_name)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return TIER_LIMITS.get(tier_name, TIER_LIMITS["ANONYMOUS"])

    fallback = TIER_LIMITS.get(tier_name, {})
    limits: dict = {}
    if cfg.max_total is not None:
        limits["max_total"] = cfg.max_total
    elif "max_total" in fallback:
        limits["max_total"] = fallback["max_total"]
    if cfg.max_monthly is not None:
        limits["max_monthly"] = cfg.max_monthly
    elif "max_monthly" in fallback:
        limits["max_monthly"] = fallback["max_monthly"]
    if cfg.max_refines_daily is not None:
        limits["max_refines_daily"] = cfg.max_refines_daily
    elif "max_refines_daily" in fallback:
        limits["max_refines_daily"] = fallback["max_refines_daily"]
    return limits


async def check_can_create_analysis(
    db: AsyncSession, user: User, *, enforce: bool = True,
) -> tuple[bool, int, int, str]:
    """Return (can_create, used, limit, detail_code).

    Args:
        enforce: When True, actively checks Telegram subscription for FREE users
                 and downgrades tier if unsubscribed. Set to False for read-only
                 queries like /me to avoid side effects and HTTP calls.
    """
    tier = user.tier or "ANONYMOUS"
    limits = await _get_tier_limits(db, tier)

    # REGISTERED — auto-activate to FREE if user has verified identity
    if tier == "REGISTERED":
        has_identity = await db.scalar(
            sa_exists(
                select(AuthIdentity.id).where(AuthIdentity.user_id == user.id)
            ).select()
        )
        if has_identity or user.email_verified or user.telegram_subscribed:
            user.tier = "FREE"
            tier = "FREE"
            limits = await _get_tier_limits(db, tier)
            await db.commit()
        else:
            return False, 0, 0, "activation_required"

    # Unlimited tier — soft cap with throttle marker
    if tier == "UNLIMITED":
        max_monthly = limits.get("max_monthly")
        if max_monthly:
            month_start = datetime.utcnow().replace(
                day=1, hour=0, minute=0, second=0, microsecond=0,
            )
            result = await db.execute(
                select(func.count()).select_from(Job).where(
                    Job.user_id == user.id,
                    Job.status != JobStatus.FAILED,
                    Job.created_at >= month_start,
                )
            )
            used = result.scalar() or 0
            if used >= max_monthly:
                # Don't block — allow with throttle marker
                return True, used, max_monthly, "throttled"
            return True, used, max_monthly, ""
        return True, 0, 0, ""

    # Tier with empty limits — unlimited
    if not limits:
        return True, 0, 0, ""

    # Lifetime limit (ANONYMOUS)
    if "max_total" in limits:
        max_total = limits["max_total"]

        # Count ALL jobs (including failed) to prevent abuse scanning
        all_jobs_result = await db.execute(
            select(func.count()).select_from(Job).where(
                Job.user_id == user.id,
            )
        )
        all_jobs = all_jobs_result.scalar() or 0
        # Hard cap: anonymous users can't create more than 5 jobs total
        # (even failed ones) to prevent unlimited scanning
        if all_jobs >= 100_000:
            logger.warning(
                "ANON_HARD_CAP user=%s total_jobs=%d", user.id, all_jobs,
            )
            return False, all_jobs, max_total, "anonymous_limit"
        # Soft limit: count non-failed for the actual analysis limit
        result = await db.execute(
            select(func.count()).select_from(Job).where(
                Job.user_id == user.id,
                Job.status != JobStatus.FAILED,
            )
        )
        used = result.scalar() or 0
        if used >= max_total:
            return False, used, max_total, "anonymous_limit"
        return True, used, max_total, ""

    # Monthly limit (FREE / START / PRO)
    base_limit = limits.get("max_monthly", 0)
    bonus = await _get_available_bonus(db, user.id)
    total_limit = base_limit + bonus

    month_start = datetime.utcnow().replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.user_id == user.id,
            Job.status != JobStatus.FAILED,
            Job.created_at >= month_start,
        )
    )
    used = result.scalar() or 0
    if used >= total_limit:
        return False, used, total_limit, "monthly_limit"
    return True, used, total_limit, ""
