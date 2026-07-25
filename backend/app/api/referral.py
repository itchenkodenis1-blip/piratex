"""Referral API — referral codes, stats, applying codes."""

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import REFERRAL_BONUS_AMOUNT, REFERRAL_MAX_PER_REFERRER, settings
from app.core.auth import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.referral import BonusCredit, Referral
from app.models.user import User
from app.core.turnstile import verify_turnstile
from app.schemas.billing import ReferralCodeResponse, ReferralStatsResponse

router = APIRouter()


def _generate_referral_code() -> str:
    """Generate a short URL-safe referral code."""
    return secrets.token_urlsafe(6)[:8].upper()


@router.get("/code", response_model=ReferralCodeResponse)
async def get_referral_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or create the user's referral code."""
    if user.is_anonymous:
        raise HTTPException(status_code=403, detail="Зарегистрируйтесь для участия в реферальной программе")
    logger = logging.getLogger(__name__)
    if not user.referral_code:
        for attempt in range(5):
            user.referral_code = _generate_referral_code()
            try:
                await db.commit()
                break
            except IntegrityError:
                await db.rollback()
                logger.warning("Referral code collision, retrying (attempt %d)", attempt + 1)
        else:
            raise HTTPException(status_code=500, detail="Failed to generate unique referral code")
        await db.refresh(user)

    return ReferralCodeResponse(
        referral_code=user.referral_code,
        referral_url=f"{settings.app_url}?ref={user.referral_code}",
    )


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_referral_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get referral statistics for the current user."""
    if user.is_anonymous:
        raise HTTPException(status_code=403, detail="Зарегистрируйтесь для участия в реферальной программе")
    if not user.referral_code:
        user.referral_code = _generate_referral_code()
        await db.commit()
        await db.refresh(user)

    # Count total referred users
    total_result = await db.execute(
        select(func.count()).where(Referral.referrer_id == user.id)
    )
    total_referred = total_result.scalar() or 0

    # Count bonus credits earned from referrals
    earned_result = await db.execute(
        select(func.coalesce(func.sum(BonusCredit.amount), 0)).where(
            BonusCredit.user_id == user.id,
            BonusCredit.reason == "referral",
        )
    )
    bonus_earned = earned_result.scalar() or 0

    # Count remaining (unused, not expired) bonus credits
    now = datetime.utcnow()
    remaining_result = await db.execute(
        select(
            func.coalesce(func.sum(BonusCredit.amount - BonusCredit.used), 0)
        ).where(
            BonusCredit.user_id == user.id,
            BonusCredit.amount > BonusCredit.used,
            (BonusCredit.expires_at.is_(None)) | (BonusCredit.expires_at > now),
        )
    )
    bonus_remaining = remaining_result.scalar() or 0

    return ReferralStatsResponse(
        referral_code=user.referral_code,
        referral_url=f"{settings.app_url}?ref={user.referral_code}",
        total_referred=total_referred,
        bonus_credits_earned=bonus_earned,
        bonus_credits_remaining=bonus_remaining,
    )


@router.post("/apply")
@limiter.limit("3/minute")
async def apply_referral_code(
    request: Request,
    code: str,
    turnstile_token: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a referral code. Gives bonus credits to both referrer and referred."""
    # --- Guard 1: anonymous users cannot apply referral codes ---
    if user.is_anonymous:
        raise HTTPException(
            status_code=403,
            detail="Зарегистрируйтесь, чтобы использовать реферальный код",
        )

    # --- Guard 2: Turnstile captcha (bot protection) ---
    client_ip = request.client.host if request.client else None
    if not await verify_turnstile(turnstile_token or "", client_ip):
        raise HTTPException(status_code=403, detail="Проверка Turnstile не пройдена")

    # --- Guard 3: can't refer yourself ---
    if user.referral_code == code:
        raise HTTPException(status_code=400, detail="Нельзя использовать свой код")

    # --- Guard 4: user already applied a code ---
    existing = await db.execute(
        select(Referral).where(Referral.referred_id == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Реферальный код уже применён")

    # --- Guard 5: referrer exists ---
    referrer_result = await db.execute(
        select(User).where(User.referral_code == code)
    )
    referrer = referrer_result.scalar_one_or_none()
    if not referrer:
        raise HTTPException(status_code=404, detail="Код не найден")

    # --- Guard 6: referrer hasn't exceeded max referrals ---
    referrer_count_result = await db.execute(
        select(func.count()).where(Referral.referrer_id == referrer.id)
    )
    referrer_count = referrer_count_result.scalar() or 0
    if referrer_count >= REFERRAL_MAX_PER_REFERRER:
        raise HTTPException(
            status_code=400,
            detail="Лимит рефералов для этого кода исчерпан",
        )

    # Create referral record
    referral = Referral(
        referrer_id=referrer.id,
        referred_id=user.id,
        bonus_applied=True,
    )
    db.add(referral)

    # Update referred_by on user
    user.referred_by = referrer.id

    # Grant bonus credits to both sides
    bonus_expiry = datetime.utcnow() + timedelta(days=90)
    for uid in (referrer.id, user.id):
        bonus = BonusCredit(
            user_id=uid,
            amount=REFERRAL_BONUS_AMOUNT,
            reason="referral",
            expires_at=bonus_expiry,
        )
        db.add(bonus)

    await db.commit()

    return {
        "ok": True,
        "message": f"Бонус +{REFERRAL_BONUS_AMOUNT} анализов начислен!",
        "bonus_amount": REFERRAL_BONUS_AMOUNT,
    }


# ---------------------------------------------------------------------------
# Partner program
# ---------------------------------------------------------------------------

@router.get("/partner")
async def get_partner_info(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get partner program info for the current user."""
    from app.services.partner import get_or_create_partner, get_partner_stats

    partner = await get_or_create_partner(db, user.id)
    await db.commit()
    stats = await get_partner_stats(db, partner.id)
    return stats


@router.get("/partner/commissions")
async def get_partner_commissions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get partner commission history."""
    from app.models.referral import Partner, PartnerCommission

    partner_result = await db.execute(
        select(Partner).where(Partner.user_id == user.id)
    )
    partner = partner_result.scalar_one_or_none()
    if not partner:
        return {"commissions": []}

    result = await db.execute(
        select(PartnerCommission)
        .where(PartnerCommission.partner_id == partner.id)
        .order_by(PartnerCommission.created_at.desc())
        .limit(50)
    )
    commissions = result.scalars().all()
    return {
        "commissions": [
            {
                "id": c.id,
                "payment_amount": c.payment_amount_kopecks // 100,
                "commission": c.commission_kopecks // 100,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in commissions
        ]
    }
