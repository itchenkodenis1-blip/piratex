"""Promo code validation and discount application."""

import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.promo import PromoCode, PromoCodeUsage

logger = logging.getLogger(__name__)


async def validate_promo_code(
    db: AsyncSession,
    code: str,
    user_id: str,
    tier: str | None,
    interval: str | None,
) -> tuple[PromoCode | None, str]:
    """Validate a promo code for a given user/tier/interval.

    Returns (promo, error_message). If promo is None, error_message explains why.
    """
    result = await db.execute(
        select(PromoCode).where(
            PromoCode.code == code.upper().strip(),
            PromoCode.is_active == True,  # noqa: E712
        )
    )
    promo = result.scalar_one_or_none()
    if not promo:
        return None, "invalid_code"

    now = datetime.utcnow()

    # Check validity period
    if promo.starts_at and now < promo.starts_at:
        return None, "not_started"
    if promo.expires_at and now > promo.expires_at:
        return None, "expired"

    # Check usage limit
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        return None, "exhausted"

    # Check tier restriction (skip when tier is None — preview mode)
    if tier and promo.valid_tiers:
        valid = [t.strip() for t in promo.valid_tiers.split(",")]
        if tier not in valid:
            return None, "invalid_tier"

    # Check interval restriction (skip when interval is None — preview mode)
    if interval and promo.valid_intervals:
        valid = [i.strip() for i in promo.valid_intervals.split(",")]
        if interval not in valid:
            return None, "invalid_interval"

    # Check if user already used this promo
    usage_result = await db.execute(
        select(func.count()).select_from(PromoCodeUsage).where(
            PromoCodeUsage.promo_code_id == promo.id,
            PromoCodeUsage.user_id == user_id,
        )
    )
    if (usage_result.scalar() or 0) > 0:
        return None, "already_used"

    return promo, ""


def calculate_discounted_amount(
    amount_kopecks: int,
    promo: PromoCode,
) -> int:
    """Apply promo discount to an amount. Returns discounted amount in kopecks."""
    if promo.discount_percent:
        discount = amount_kopecks * promo.discount_percent // 100
        return max(amount_kopecks - discount, 100)  # min 1 ruble
    if promo.discount_kopecks:
        return max(amount_kopecks - promo.discount_kopecks, 100)
    return amount_kopecks


async def record_promo_usage(
    db: AsyncSession,
    promo: PromoCode,
    user_id: str,
) -> None:
    """Record that a user has used a promo code."""
    usage = PromoCodeUsage(
        promo_code_id=promo.id,
        user_id=user_id,
    )
    db.add(usage)
    promo.used_count = (promo.used_count or 0) + 1
    await db.flush()
