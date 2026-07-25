"""Partner/affiliate program — commission tracking and payouts."""

import logging
import secrets
import string

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.referral import Partner, PartnerCommission
from app.models.user import User
from app.services.telegram import send_telegram_message

logger = logging.getLogger(__name__)


def _generate_partner_code() -> str:
    """Generate a short alphanumeric partner code."""
    chars = string.ascii_uppercase + string.digits
    return "P-" + "".join(secrets.choice(chars) for _ in range(6))


async def get_or_create_partner(db: AsyncSession, user_id: str) -> Partner:
    """Get existing partner record or create a new one."""
    result = await db.execute(
        select(Partner).where(Partner.user_id == user_id)
    )
    partner = result.scalar_one_or_none()
    if partner:
        return partner

    partner = Partner(
        user_id=user_id,
        partner_code=_generate_partner_code(),
    )
    db.add(partner)
    await db.flush()
    return partner


async def get_partner_by_code(db: AsyncSession, code: str) -> Partner | None:
    """Look up a partner by their code."""
    result = await db.execute(
        select(Partner).where(
            Partner.partner_code == code.upper().strip(),
            Partner.status == "active",
        )
    )
    return result.scalar_one_or_none()


async def record_commission(
    db: AsyncSession,
    referred_user_id: str,
    payment_id: str,
    payment_amount_kopecks: int,
) -> PartnerCommission | None:
    """Record a commission for a partner when a referred user pays.

    Looks up the referral chain: referred_user → referred_by → partner.
    Returns the commission record if applicable.
    """
    # Find who referred this user
    user_result = await db.execute(
        select(User.referred_by).where(User.id == referred_user_id)
    )
    referrer_id = user_result.scalar()
    if not referrer_id:
        return None

    # Check if referrer is a partner
    partner_result = await db.execute(
        select(Partner).where(
            Partner.user_id == referrer_id,
            Partner.status == "active",
        )
    )
    partner = partner_result.scalar_one_or_none()
    if not partner:
        return None

    commission_kopecks = payment_amount_kopecks * partner.commission_percent // 100

    commission = PartnerCommission(
        partner_id=partner.id,
        payment_id=payment_id,
        referred_user_id=referred_user_id,
        payment_amount_kopecks=payment_amount_kopecks,
        commission_kopecks=commission_kopecks,
    )
    db.add(commission)

    # Update partner totals
    partner.total_earned_kopecks = (partner.total_earned_kopecks or 0) + commission_kopecks
    await db.flush()

    logger.info(
        "Commission recorded: partner=%s amount=%d commission=%d",
        partner.id, payment_amount_kopecks, commission_kopecks,
    )

    # Notify partner via Telegram
    partner_user_result = await db.execute(
        select(User).where(User.id == partner.user_id)
    )
    partner_user = partner_user_result.scalar_one_or_none()
    if partner_user and partner_user.telegram_user_id and settings.telegram_bot_token:
        commission_rub = commission_kopecks // 100
        total_rub = partner.total_earned_kopecks // 100
        try:
            await send_telegram_message(
                partner_user.telegram_user_id,
                settings.telegram_bot_token,
                f"Партнёрская комиссия: +{commission_rub} ₽\n"
                f"Всего заработано: {total_rub} ₽",
            )
        except Exception:
            pass

    return commission


async def get_partner_stats(db: AsyncSession, partner_id: str) -> dict:
    """Get partner statistics."""
    partner_result = await db.execute(
        select(Partner).where(Partner.id == partner_id)
    )
    partner = partner_result.scalar_one_or_none()
    if not partner:
        return {}

    # Count referred users with active subscriptions
    # (partner's referral code users — via referred_by)
    active_result = await db.execute(
        select(func.count()).select_from(User).where(
            User.referred_by == partner.user_id,
            User.tier.in_(["START", "PRO", "UNLIMITED"]),
        )
    )
    active_paying = active_result.scalar() or 0

    # Pending commissions
    pending_result = await db.execute(
        select(func.coalesce(func.sum(PartnerCommission.commission_kopecks), 0)).where(
            PartnerCommission.partner_id == partner.id,
            PartnerCommission.status == "pending",
        )
    )
    pending_kopecks = pending_result.scalar() or 0

    return {
        "partner_code": partner.partner_code,
        "partner_url": f"{settings.app_url}?ref={partner.partner_code}",
        "commission_percent": partner.commission_percent,
        "total_referred": partner.total_referred,
        "active_paying": active_paying,
        "total_earned": partner.total_earned_kopecks // 100,
        "total_paid_out": partner.total_paid_out_kopecks // 100,
        "pending": pending_kopecks // 100,
    }
