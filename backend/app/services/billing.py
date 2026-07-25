"""Billing service — subscription lifecycle management."""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    PROVIDER_CURRENCY,
    STRIPE_PRICE_IDS,
    STRIPE_PRICE_TO_TIER,
    TIER_PRICING,
    TIER_PRICING_EUR,
    settings,
)
from app.models.subscription import Payment, Subscription
from app.models.user import User, UserSettings
from app.services.payments import WebhookEvent, get_provider
from app.services.telegram import send_telegram_message

logger = logging.getLogger(__name__)

INTERVAL_DAYS = {"monthly": 30, "yearly": 365}

TIER_NAMES = {
    "START": "Start — 50 роликов/мес",
    "PRO": "Pro — 150 роликов/мес",
    "UNLIMITED": "Unlimited — безлимит",
}

TIER_ORDER = {"FREE": 0, "START": 1, "PRO": 2, "UNLIMITED": 3}


def _is_upgrade(current_tier: str, current_interval: str, new_tier: str, new_interval: str) -> bool:
    """Determine if the tier change is an upgrade.

    Upgrade: new_tier > current_tier OR (same tier + monthly → yearly).
    """
    cur_order = TIER_ORDER.get(current_tier, 0)
    new_order = TIER_ORDER.get(new_tier, 0)
    if new_order > cur_order:
        return True
    if new_order < cur_order:
        return False
    # Same tier: monthly → yearly is upgrade
    return current_interval == "monthly" and new_interval == "yearly"


def calculate_proration(
    subscription: Subscription,
    new_tier: str,
    new_interval: str,
    now: datetime | None = None,
) -> dict:
    """Calculate proration for a tier change. Pure function, no DB access.

    Returns dict with: proration_amount, credit, charge, new_price_full,
    currency, days_remaining, next_billing_date, is_upgrade.
    """
    now = now or datetime.utcnow()

    if not subscription.current_period_end or not subscription.current_period_start:
        raise ValueError("Subscription has no billing period — cannot calculate proration")

    currency = subscription.currency
    if currency == "EUR":
        new_price_full = TIER_PRICING_EUR[new_tier][new_interval]
    else:
        new_price_full = TIER_PRICING[new_tier][new_interval]

    is_up = _is_upgrade(
        subscription.tier, subscription.billing_interval,
        new_tier, new_interval,
    )

    period_end = subscription.current_period_end
    period_start = subscription.current_period_start

    days_remaining = max(0, (period_end - now).total_seconds() / 86400)
    days_in_period = max(1, (period_end - period_start).total_seconds() / 86400)
    ratio = days_remaining / days_in_period

    # Credit from actually paid amount (not full price) to avoid revenue leak with promos
    old_amount = subscription.paid_amount_kopecks or subscription.amount_kopecks
    credit = round(ratio * old_amount)

    if is_up:
        # For monthly→yearly upgrade: charge full yearly price (new billing cycle)
        if subscription.billing_interval != new_interval:
            charge = new_price_full
        else:
            charge = round(ratio * new_price_full)
        proration_amount = max(0, charge - credit)
    else:
        # Downgrade: no immediate charge
        charge = 0
        credit = 0
        proration_amount = 0

    return {
        "proration_amount": proration_amount,
        "credit": credit,
        "charge": charge,
        "new_price_full": new_price_full,
        "currency": currency,
        "days_remaining": round(days_remaining),
        "next_billing_date": period_end,
        "is_upgrade": is_up,
    }


def _get_price(tier: str, interval: str, provider_name: str) -> tuple[int, str]:
    """Return (amount_minor, currency) for the given tier/interval/provider."""
    currency = PROVIDER_CURRENCY.get(provider_name, "RUB")
    if currency == "RUB":
        return TIER_PRICING[tier][interval], currency
    return TIER_PRICING_EUR[tier][interval], currency


async def _resolve_provider(db: AsyncSession, user: User, provider_name: str | None) -> str:
    """Determine payment provider from explicit choice or user language."""
    if provider_name:
        return provider_name
    # Auto-select based on user language: ru → cloudpayments (fallback yookassa), else → stripe
    from app.services.payments import get_provider

    result = await db.execute(
        select(UserSettings.language).where(UserSettings.user_id == user.id)
    )
    lang = result.scalar_one_or_none() or "ru"
    if lang == "ru":
        # Prefer CloudPayments, fall back to YooKassa if not configured
        for name in ("cloudpayments", "yookassa"):
            try:
                get_provider(name)
                return name
            except ValueError:
                continue
        return "yookassa"  # will fail with clear error if neither is configured
    return "stripe"


async def create_checkout(
    db: AsyncSession,
    user: User,
    tier: str,
    interval: str,
    promo_code: str | None = None,
    provider_name: str | None = None,
) -> tuple[str, str, str]:
    """Create a payment session via the selected provider.

    If provider_name is None, auto-selects based on user language.
    Returns (payment_url, provider_payment_id, provider_name).
    """
    if tier not in TIER_PRICING:
        raise ValueError(f"Unknown tier: {tier}")
    if interval not in ("monthly", "yearly"):
        raise ValueError(f"Unknown interval: {interval}")

    # Dedup: return existing pending checkout if created within 30 minutes
    # Match by tier name and interval to avoid returning wrong checkout link
    tier_name = TIER_NAMES.get(tier, tier)
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    existing_result = await db.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.status == "pending",
            Payment.created_at > cutoff,
            Payment.payment_url.isnot(None),
            Payment.description.contains(tier_name),
            Payment.description.contains(f"({interval})"),
        ).order_by(Payment.created_at.desc()).limit(1)
    )
    existing_pending = existing_result.scalar_one_or_none()
    if existing_pending:
        return existing_pending.payment_url, existing_pending.provider_payment_id, existing_pending.payment_provider

    provider_name = await _resolve_provider(db, user, provider_name)
    provider = get_provider(provider_name)
    amount_minor, currency = _get_price(tier, interval, provider_name)

    # Apply promo code discount if provided (usage recorded after payment succeeds)
    promo = None
    if promo_code:
        from app.services.promo import (
            calculate_discounted_amount,
            validate_promo_code,
        )

        promo, error = await validate_promo_code(db, promo_code, user.id, tier, interval)
        if not promo:
            raise ValueError(f"promo:{error}")
        amount_minor = calculate_discounted_amount(amount_minor, promo)

    brand = "Piratex.ai" if provider_name == "yookassa" else "Viralex.ai"
    description = f"{brand} {TIER_NAMES.get(tier, tier)} ({interval})"
    if promo:
        description += f" (promo {promo.code})"

    original_amount, _ = _get_price(tier, interval, provider_name)

    metadata = {
        "user_id": user.id,
        "tier": tier,
        "interval": interval,
        "email": user.email or "",
        "promo_code": promo.code if promo else "",
        "original_amount": str(original_amount),
    }

    # Stripe-specific: pass extra params for subscription mode
    extra_kwargs: dict = {}
    if provider_name == "stripe":
        extra_kwargs["stripe_customer_id"] = user.stripe_customer_id
        extra_kwargs["stripe_price_id"] = STRIPE_PRICE_IDS.get(tier, {}).get(interval)

        # Create Stripe Coupon for promo discount
        if promo and promo.discount_percent:
            from app.services.payments.stripe_provider import StripeProvider
            if isinstance(provider, StripeProvider):
                duration = "once"
                duration_in_months = None
                if promo.duration_months and promo.duration_months > 1:
                    duration = "repeating"
                    duration_in_months = promo.duration_months
                coupon_id = await provider.create_coupon(
                    percent_off=promo.discount_percent,
                    duration=duration,
                    duration_in_months=duration_in_months,
                )
                extra_kwargs["stripe_coupon_id"] = coupon_id

    # For CloudPayments: cancel any existing recurrent subscriptions before
    # creating a new checkout. CP creates a NEW subscription per widget payment,
    # so old ones must be cancelled to prevent double-charging on upgrade.
    if provider_name == "cloudpayments":
        try:
            from app.services.payments.cloudpayments_provider import CloudPaymentsProvider
            if isinstance(provider, CloudPaymentsProvider):
                await provider.cancel_subscription(account_id=user.id)
        except Exception as e:
            logger.warning("CP cancel old subscriptions before checkout: %s", e)

    result = await provider.create_checkout_session(
        amount_minor=amount_minor,
        currency=currency,
        description=description,
        return_url=f"{settings.app_url}/checkout/success",
        cancel_url=f"{settings.app_url}/pricing",
        metadata=metadata,
        user_email=user.email,
        **extra_kwargs,
    )

    # Save stripe_customer_id on user if returned
    if result.stripe_customer_id and provider_name == "stripe":
        user.stripe_customer_id = result.stripe_customer_id
        await db.flush()

    # Create pending payment record
    payment = Payment(
        user_id=user.id,
        provider_payment_id=result.provider_payment_id,
        payment_provider=provider_name,
        amount_kopecks=amount_minor,
        currency=currency,
        status="pending",
        description=description,
        payment_url=result.payment_url,
        checkout_tier=tier,
        checkout_interval=interval,
        expected_amount_kopecks=amount_minor,
    )
    db.add(payment)
    await db.commit()

    return result.payment_url, result.provider_payment_id, provider_name


async def change_tier(
    db: AsyncSession,
    user: User,
    new_tier: str,
    new_interval: str,
) -> dict:
    """Change user's subscription tier (upgrade or downgrade).

    Upgrade: dispatches to provider-specific flow (Фаза 2 will implement).
    Downgrade: schedules tier change at period end.

    Returns dict with result info.
    """
    if new_tier not in TIER_PRICING:
        raise ValueError(f"Unknown tier: {new_tier}")
    if new_interval not in ("monthly", "yearly"):
        raise ValueError(f"Unknown interval: {new_interval}")

    # Must have active subscription (not cancelled, not past_due)
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
        ).with_for_update()
    )
    sub = result.scalar_one_or_none()

    if not sub:
        raise ValueError("No active subscription. Use checkout for new subscriptions.")

    if user.tier == "FREE" or sub.tier == "FREE":
        raise ValueError("FREE users should use normal checkout to subscribe.")

    if sub.tier == new_tier and sub.billing_interval == new_interval:
        raise ValueError("Already on this tier and interval.")

    # Prevent cross-currency upgrades
    provider_currency = PROVIDER_CURRENCY.get(sub.payment_provider, "RUB")
    if sub.currency != provider_currency:
        raise ValueError("Cross-currency tier changes are not supported.")

    is_up = _is_upgrade(sub.tier, sub.billing_interval, new_tier, new_interval)

    if is_up:
        # Upgrade: calculate proration and dispatch to provider
        proration = calculate_proration(sub, new_tier, new_interval)

        # Provider-specific upgrade will be implemented in Фаза 2.
        # For now, return the proration info so the frontend can redirect to checkout.
        return {
            "scheduled": False,
            "is_upgrade": True,
            "proration": proration,
            "provider": sub.payment_provider,
            "message": "Upgrade requires payment. Use provider-specific flow.",
        }
    else:
        # Downgrade: schedule for period end
        sub.scheduled_tier = new_tier
        sub.scheduled_interval = new_interval
        sub.updated_at = datetime.utcnow()
        await db.commit()

        # For CloudPayments: update the recurrent subscription amount on CP side
        # so that the next auto-charge uses the new (lower) price.
        if sub.payment_provider == "cloudpayments":
            try:
                from app.services.payments.cloudpayments_provider import CloudPaymentsProvider
                cp_provider = get_provider("cloudpayments")
                if isinstance(cp_provider, CloudPaymentsProvider):
                    new_price = _get_price(new_tier, new_interval, "cloudpayments")
                    new_amount_rubles = new_price[0] / 100  # kopecks → rubles
                    await cp_provider.update_subscription_amount(
                        account_id=user.id, amount_rubles=new_amount_rubles,
                    )
            except Exception as e:
                logger.error(
                    "Failed to update CP subscription amount for downgrade: user=%s err=%s",
                    user.id, e,
                )

        logger.info(
            "Downgrade scheduled: user=%s %s/%s → %s/%s at %s",
            user.id, sub.tier, sub.billing_interval,
            new_tier, new_interval, sub.current_period_end,
        )

        return {
            "scheduled": True,
            "is_upgrade": False,
            "effective_date": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "message": f"Переход на {new_tier} запланирован на конец текущего периода.",
        }


async def cancel_scheduled_downgrade(
    db: AsyncSession,
    user: User,
) -> Subscription | None:
    """Cancel a scheduled downgrade."""
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
        ).with_for_update()
    )
    sub = result.scalar_one_or_none()
    if not sub or not sub.scheduled_tier:
        return None

    # Remember original tier before clearing scheduled fields
    original_tier = sub.tier
    original_interval = sub.billing_interval

    sub.scheduled_tier = None
    sub.scheduled_interval = None
    sub.updated_at = datetime.utcnow()
    await db.commit()

    # For CloudPayments: restore the original subscription amount on CP side.
    # change_tier() updated CP to the downgraded price — now revert it.
    if sub.payment_provider == "cloudpayments":
        try:
            from app.services.payments.cloudpayments_provider import CloudPaymentsProvider
            cp_provider = get_provider("cloudpayments")
            if isinstance(cp_provider, CloudPaymentsProvider):
                original_price = _get_price(original_tier, original_interval, "cloudpayments")
                original_amount_rubles = original_price[0] / 100
                await cp_provider.update_subscription_amount(
                    account_id=user.id, amount_rubles=original_amount_rubles,
                )
        except Exception as e:
            logger.error(
                "Failed to restore CP subscription amount after cancel downgrade: user=%s err=%s",
                user.id, e,
            )

    logger.info("Scheduled downgrade cancelled: user=%s", user.id)
    return sub


async def handle_proration_payment(
    db: AsyncSession,
    event: WebhookEvent,
) -> tuple["User | None", "Subscription | None"]:
    """Handle a proration payment (upgrade mid-cycle).

    Unlike handle_payment_succeeded, does NOT change billing cycle dates.
    Returns (user, sub) for notification by callsite.
    """
    user_id = event.user_id
    new_tier = event.tier
    provider_id = event.provider_payment_id

    if not user_id or not new_tier:
        logger.warning("proration payment without user_id/tier: %s", provider_id)
        return None, None

    # Update payment record
    result = await db.execute(
        select(Payment).where(Payment.provider_payment_id == provider_id)
    )
    payment = result.scalar_one_or_none()
    if payment:
        payment.status = "succeeded"
        payment.paid_at = datetime.utcnow()
        payment.payment_method = event.payment_method

    # Find active subscription (guard against duplicates like handle_payment_succeeded)
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status.in_(["active", "past_due"]),
        ).with_for_update()
    )
    subs = result.scalars().all()
    if not subs:
        logger.error("Proration payment but no subscription: user=%s", user_id)
        return None, None
    if len(subs) > 1:
        logger.warning("Duplicate active subs for proration user=%s, using most recent", user_id)
        subs.sort(key=lambda s: s.updated_at or s.created_at or datetime.min, reverse=True)
    sub = subs[0]

    new_interval = event.interval or sub.billing_interval
    currency = sub.currency
    if currency == "EUR":
        new_full_price = TIER_PRICING_EUR[new_tier][new_interval]
    else:
        new_full_price = TIER_PRICING[new_tier][new_interval]

    # Update tier but DO NOT change period dates (billing anchor preserved)
    sub.tier = new_tier
    sub.billing_interval = new_interval
    sub.amount_kopecks = new_full_price
    sub.paid_amount_kopecks = new_full_price  # next renewal pays full price
    sub.updated_at = datetime.utcnow()
    # Clear any scheduled downgrade
    sub.scheduled_tier = None
    sub.scheduled_interval = None

    if payment:
        payment.subscription_id = sub.id

    # Update user tier
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.tier = new_tier
        from app.services.trend_monitor import enforce_author_limits
        await enforce_author_limits(db, user_id, new_tier)

    await db.commit()
    logger.info(
        "Proration payment applied: user=%s tier→%s, billing anchor preserved",
        user_id, new_tier,
    )

    return user, sub


async def handle_payment_succeeded(
    db: AsyncSession,
    event: WebhookEvent,
) -> tuple["User | None", "Subscription | None"]:
    """Handle normalised payment.succeeded event from any provider.

    Activates or renews subscription, upgrades user tier.
    """
    # Check if this is a proration payment — delegate to specialized handler
    if event.raw_data:
        import json as _json
        metadata = {}
        # YooKassa: metadata in object.metadata or top-level metadata
        for path in ("metadata", "object.metadata", "Data"):
            obj = event.raw_data
            for key in path.split("."):
                obj = obj.get(key, {}) if isinstance(obj, dict) else {}
            if obj:
                if isinstance(obj, str):
                    try:
                        obj = _json.loads(obj)
                    except (ValueError, TypeError):
                        obj = {}
                metadata = obj
                break
        # Stripe: metadata in data.object.metadata
        if not metadata:
            stripe_meta = (event.raw_data.get("data", {}).get("object", {}).get("metadata", {}))
            if stripe_meta:
                metadata = stripe_meta
        if metadata.get("is_proration"):
            return await handle_proration_payment(db, event)
    provider_id = event.provider_payment_id
    user_id = event.user_id
    tier = event.tier
    interval = event.interval

    # Idempotency guard: if this provider_payment_id was already processed
    # successfully, skip to prevent duplicate subscription extensions.
    # Uses FOR UPDATE to serialize concurrent webhook retries.
    if provider_id:
        existing_result = await db.execute(
            select(Payment).where(
                Payment.provider_payment_id == provider_id,
                Payment.status == "succeeded",
            ).with_for_update(skip_locked=True)
        )
        if existing_result.scalar_one_or_none():
            logger.info(
                "Webhook idempotency: payment %s already processed — skipping",
                provider_id,
            )
            return None, None

    # CloudPayments recurrent webhooks may not include tier/interval metadata.
    # Look up from the existing active subscription.
    if user_id and (not tier or not interval) and event.provider_name == "cloudpayments":
        sub_result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.payment_provider == "cloudpayments",
                Subscription.status.in_(["active", "past_due"]),
            ).order_by(Subscription.updated_at.desc().nulls_last()).limit(1)
        )
        existing_sub = sub_result.scalar_one_or_none()
        if existing_sub:
            tier = tier or existing_sub.tier
            interval = interval or existing_sub.billing_interval
            logger.info(
                "CP recurrent webhook: resolved tier=%s interval=%s from existing sub for user=%s",
                tier, interval, user_id,
            )

    # Stripe fallback: if user_id missing but we have stripe_customer_id, look up user
    if not user_id and event.provider_name == "stripe" and event.stripe_customer_id:
        cust_result = await db.execute(
            select(User).where(User.stripe_customer_id == event.stripe_customer_id)
        )
        cust_user = cust_result.scalar_one_or_none()
        if cust_user:
            user_id = cust_user.id
            logger.info(
                "Stripe fallback: resolved user_id=%s from stripe_customer_id=%s",
                user_id, event.stripe_customer_id,
            )

    # Final fallback — interval must have a value
    interval = interval or "monthly"

    if not user_id or not tier:
        logger.warning("payment.succeeded without user_id/tier metadata: %s", provider_id)
        return None, None

    # Update payment record
    result = await db.execute(
        select(Payment).where(Payment.provider_payment_id == provider_id)
    )
    payment = result.scalar_one_or_none()

    # CloudPayments: TransactionId (provider_id) != InvoiceId (our UUID from checkout).
    # Look up the original checkout Payment by InvoiceId from webhook raw_data.
    if not payment and event.provider_name == "cloudpayments" and event.raw_data:
        invoice_id = str(event.raw_data.get("InvoiceId", ""))
        if invoice_id:
            inv_result = await db.execute(
                select(Payment).where(Payment.provider_payment_id == invoice_id)
            )
            payment = inv_result.scalar_one_or_none()
            if payment:
                # Update to TransactionId for future lookups (refunds, etc.)
                payment.provider_payment_id = provider_id

    # Detect recurrent (auto-renewal) payments — used for CP amount enforcement below
    is_recurrent = (
        event.provider_name == "cloudpayments"
        and event.raw_data
        and str(event.raw_data.get("Recurrent", "")).lower() == "true"
    )

    if payment:
        payment.status = "succeeded"
        payment.paid_at = datetime.utcnow()
        payment.payment_method = event.payment_method

        # Security: use server-side checkout intent instead of untrusted webhook data
        if payment.checkout_tier:
            if tier and tier != payment.checkout_tier:
                logger.warning(
                    "CloudPayments tier mismatch: webhook=%s checkout=%s payment=%s — using checkout tier",
                    tier, payment.checkout_tier, provider_id,
                )
            tier = payment.checkout_tier
            interval = payment.checkout_interval or interval

        # Security: reject if actual amount doesn't match expected (spoofed widget amount)
        if payment.expected_amount_kopecks and abs(event.amount_minor - payment.expected_amount_kopecks) > 1:
            logger.error(
                "Payment amount spoofing detected: expected=%d got=%d payment=%s user=%s — rejecting",
                payment.expected_amount_kopecks, event.amount_minor, provider_id, user_id,
            )
            payment.status = "cancelled"
            await db.commit()
            return None, None
    else:
        if event.provider_name == "cloudpayments" and not is_recurrent:
            # First payment without a checkout Payment record — possible spoofing
            logger.error(
                "CloudPayments first payment without checkout record: provider_id=%s user=%s — rejecting",
                provider_id, user_id,
            )
            return None, None

        # Recurrent payment or other provider — create Payment from webhook data
        payment = Payment(
            user_id=user_id,
            provider_payment_id=provider_id,
            payment_provider=event.provider_name,
            amount_kopecks=event.amount_minor,
            currency=event.currency,
            status="succeeded",
            payment_method=event.payment_method,
            description=f"Piratex.ai {tier} ({interval})",
            paid_at=datetime.utcnow(),
        )
        db.add(payment)
        # Flush to trigger unique constraint on provider_payment_id —
        # catches concurrent duplicate webhooks that slipped past the guard above.
        try:
            await db.flush()
        except Exception as flush_exc:
            if "unique" in str(flush_exc).lower() or "duplicate" in str(flush_exc).lower():
                logger.info(
                    "Webhook idempotency (flush): duplicate payment %s — skipping",
                    provider_id,
                )
                await db.rollback()
                return None, None
            raise

    # Get or create subscription (guard against duplicates)
    # Exclude admin-granted subs — they should not be overwritten by payments
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status.in_(["active", "past_due"]),
            Subscription.payment_provider != "admin",
        ).with_for_update()
    )
    subs = result.scalars().all()
    if len(subs) > 1:
        logger.warning(
            "Duplicate active subscriptions for user=%s: %s — using most recent",
            user_id, [s.id for s in subs],
        )
        # Pick most recently updated
        subs.sort(key=lambda s: s.updated_at or s.created_at or datetime.min, reverse=True)
    sub = subs[0] if subs else None

    now = datetime.utcnow()

    # For Stripe: use period_end from Stripe (they manage billing cycle)
    # For others: calculate period_end ourselves
    is_stripe = event.provider_name == "stripe"
    if is_stripe and event.current_period_end:
        period_end = datetime.utcfromtimestamp(event.current_period_end)
    else:
        period_days = INTERVAL_DAYS.get(interval, 30)
        period_end = now + timedelta(days=period_days)

    # For subscription, store full price (before promo) so recurring payments charge full amount
    subscription_amount = event.original_amount_minor if event.original_amount_minor else event.amount_minor

    if sub:
        # Save old values before modification — needed for CP subscription update
        old_amount = sub.amount_kopecks
        old_interval = sub.billing_interval

        # For non-Stripe: upgrade with proration (carry over remaining days)
        # For Stripe: Stripe handles proration itself, so skip manual calculation
        if not is_stripe:
            remaining_days = 0
            if sub.status == "active" and sub.tier != tier and sub.current_period_end:
                remaining_seconds = (sub.current_period_end - now).total_seconds()
                remaining_days = max(0, math.ceil(remaining_seconds / 86400))
                if remaining_days:
                    logger.info(
                        "Proration: user=%s upgrade %s→%s, carrying over %d remaining days",
                        user_id, sub.tier, tier, remaining_days,
                    )
            period_end = now + timedelta(days=INTERVAL_DAYS.get(interval, 30) + remaining_days)

        # Apply scheduled downgrade only on renewal (same tier = recurring charge,
        # not an upgrade via proration). If tier differs, this is an upgrade payment
        # and the scheduled downgrade should be cleared, not applied.
        if sub.scheduled_tier and tier == sub.tier:
            logger.info(
                "Applying scheduled downgrade: user=%s %s/%s → %s/%s",
                user_id, tier, interval, sub.scheduled_tier,
                sub.scheduled_interval or interval,
            )
            tier = sub.scheduled_tier
            interval = sub.scheduled_interval or interval
            # Recalculate amount for the new (downgraded) tier
            new_price = _get_price(tier, interval, event.provider_name)
            subscription_amount = new_price[0]

        # Renew existing subscription
        sub.tier = tier
        sub.status = "active"
        sub.payment_provider = event.provider_name
        sub.current_period_start = now
        sub.current_period_end = period_end
        sub.billing_interval = interval
        sub.amount_kopecks = subscription_amount
        sub.paid_amount_kopecks = event.amount_minor  # actual amount paid (after promo)
        sub.currency = event.currency
        sub.updated_at = now
        # Clear scheduled downgrade (already applied above if it existed)
        sub.scheduled_tier = None
        sub.scheduled_interval = None
        # Store Stripe subscription ID
        if is_stripe and event.stripe_subscription_id:
            sub.provider_subscription_id = event.stripe_subscription_id
        # Note: CP recurrent subscription amount/interval is managed at
        # checkout time — old CP subscriptions are cancelled before creating
        # a new checkout (see create_checkout).
        if payment:
            payment.subscription_id = sub.id
    else:
        # New subscription
        sub = Subscription(
            user_id=user_id,
            tier=tier,
            status="active",
            payment_provider=event.provider_name,
            amount_kopecks=subscription_amount,
            paid_amount_kopecks=event.amount_minor,
            currency=event.currency,
            billing_interval=interval,
            current_period_start=now,
            current_period_end=period_end,
        )
        # Store Stripe subscription ID
        if is_stripe and event.stripe_subscription_id:
            sub.provider_subscription_id = event.stripe_subscription_id
        db.add(sub)
        await db.flush()
        if payment:
            payment.subscription_id = sub.id

    # Save Stripe customer ID on user
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.tier = tier
        if is_stripe and event.stripe_customer_id:
            user.stripe_customer_id = event.stripe_customer_id
        from app.services.trend_monitor import enforce_author_limits
        await enforce_author_limits(db, user_id, tier)
    else:
        logger.error(
            "payment.succeeded but user not found: user_id=%s provider_id=%s tier=%s",
            user_id, provider_id, tier,
        )

    # Save payment method token for recurring charges
    if event.provider_name == "yookassa" and event.raw_data:
        pm_data = event.raw_data.get("payment_method", {})
        if not pm_data:
            pm_data = event.raw_data.get("object", {}).get("payment_method", {})
        pm_id = pm_data.get("id")
        if pm_id and pm_data.get("saved"):
            sub.payment_method_id = pm_id
            logger.info("Saved YooKassa payment_method_id=%s for user=%s", pm_id, user_id)

    if event.provider_name == "cloudpayments" and event.raw_data:
        # CloudPayments returns Token in webhook for recurrent charges.
        # We store it as payment_method_id for reference, though CP manages
        # recurrence automatically via their subscriptions API.
        token = event.raw_data.get("Token", "")
        if token:
            sub.payment_method_id = token
            logger.info("Saved CloudPayments Token for user=%s", user_id)

        # Security: enforce correct recurrent amount via CP Subscriptions API.
        # Even if the client tampered with data.CloudPayments.recurrent.amount
        # in the widget, we overwrite the CP-side subscription amount with the
        # server-authoritative full price.  This is a defense-in-depth measure
        # on top of the /check webhook validation.
        if not is_recurrent:
            # First payment — CP just created the subscription, enforce amount
            expected_rubles = subscription_amount / 100
            account_id = event.raw_data.get("AccountId") or user_id
            try:
                from app.services.payments.cloudpayments_provider import CloudPaymentsProvider
                cp_provider = CloudPaymentsProvider()
                updated = await cp_provider.update_subscription_amount(
                    account_id, expected_rubles,
                )
                if updated:
                    logger.info(
                        "CP recurrent amount enforced to %.2f for user=%s",
                        expected_rubles, user_id,
                    )
                else:
                    logger.warning(
                        "CP recurrent amount enforcement failed for user=%s — "
                        "subscription may charge tampered amount",
                        user_id,
                    )
            except Exception as e:
                logger.error(
                    "CP recurrent amount enforcement error for user=%s: %s",
                    user_id, e,
                )

    # DISABLED: partner commission program temporarily closed (abuse)
    # try:
    #     from app.services.partner import record_commission
    #     if payment:
    #         await record_commission(db, user_id, payment.id, event.amount_minor)
    # except Exception as e:
    #     logger.warning("Partner commission error: %s", e)

    # Record promo usage now that payment actually succeeded
    if event.promo_code:
        try:
            from app.models.promo import PromoCode
            from app.services.promo import record_promo_usage

            promo_result = await db.execute(
                select(PromoCode).where(PromoCode.code == event.promo_code.upper().strip())
            )
            promo_obj = promo_result.scalar_one_or_none()
            if promo_obj:
                await record_promo_usage(db, promo_obj, user_id)
        except Exception as e:
            logger.warning("Promo usage recording error: %s", e)

    await db.commit()
    logger.info("Subscription activated: user=%s tier=%s until=%s provider=%s", user_id, tier, period_end, event.provider_name)

    return user, sub


async def handle_subscription_updated(
    db: AsyncSession,
    event: WebhookEvent,
) -> None:
    """Handle Stripe subscription.updated — sync tier, period, status."""
    if not event.stripe_subscription_id:
        logger.warning("subscription.updated without stripe_subscription_id")
        return

    # Find subscription by provider_subscription_id
    result = await db.execute(
        select(Subscription).where(
            Subscription.provider_subscription_id == event.stripe_subscription_id,
        ).with_for_update()
    )
    sub = result.scalar_one_or_none()
    if not sub:
        # Try finding by user_id if subscription ID not stored yet
        if event.user_id:
            result = await db.execute(
                select(Subscription).where(
                    Subscription.user_id == event.user_id,
                    Subscription.payment_provider == "stripe",
                    Subscription.status.in_(["active", "past_due", "cancelled"]),
                ).order_by(Subscription.updated_at.desc().nulls_last())
                .with_for_update()
            )
            subs = result.scalars().all()
            sub = subs[0] if subs else None

    if not sub:
        logger.warning(
            "subscription.updated but no subscription found: stripe_sub=%s user=%s",
            event.stripe_subscription_id, event.user_id,
        )
        return

    # Resolve tier from price_id
    if event.stripe_price_id:
        tier_info = STRIPE_PRICE_TO_TIER.get(event.stripe_price_id)
        if tier_info:
            new_tier, new_interval = tier_info
            sub.tier = new_tier
            sub.billing_interval = new_interval

    # Update period from Stripe
    if event.current_period_end:
        sub.current_period_end = datetime.utcfromtimestamp(event.current_period_end)

    # Check raw_data for status changes
    raw_sub = event.raw_data.get("data", {}).get("object", {})
    stripe_status = raw_sub.get("status", "")
    cancel_at_period_end = raw_sub.get("cancel_at_period_end", False)

    if stripe_status == "past_due":
        sub.status = "past_due"
    elif stripe_status == "active" and cancel_at_period_end:
        sub.status = "cancelled"
        sub.cancelled_at = datetime.utcnow()
    elif stripe_status == "active":
        sub.status = "active"
        sub.cancelled_at = None

    sub.provider_subscription_id = event.stripe_subscription_id
    sub.updated_at = datetime.utcnow()

    # Sync user tier
    user_result = await db.execute(select(User).where(User.id == sub.user_id))
    user = user_result.scalar_one_or_none()
    if user and sub.tier:
        user.tier = sub.tier
        from app.services.trend_monitor import enforce_author_limits
        await enforce_author_limits(db, sub.user_id, sub.tier)

    await db.commit()
    logger.info(
        "Subscription updated: user=%s tier=%s status=%s stripe_sub=%s",
        sub.user_id, sub.tier, sub.status, event.stripe_subscription_id,
    )


async def handle_subscription_deleted(
    db: AsyncSession,
    event: WebhookEvent,
) -> None:
    """Handle Stripe subscription.deleted — expire and downgrade to FREE."""
    if not event.stripe_subscription_id:
        logger.warning("subscription.deleted without stripe_subscription_id")
        return

    result = await db.execute(
        select(Subscription).where(
            Subscription.provider_subscription_id == event.stripe_subscription_id,
        ).with_for_update()
    )
    sub = result.scalar_one_or_none()

    if not sub:
        # Fallback: find by user_id
        if event.user_id:
            result = await db.execute(
                select(Subscription).where(
                    Subscription.user_id == event.user_id,
                    Subscription.payment_provider == "stripe",
                    Subscription.status.in_(["active", "past_due", "cancelled"]),
                ).order_by(Subscription.updated_at.desc().nulls_last())
                .with_for_update()
            )
            subs = result.scalars().all()
            sub = subs[0] if subs else None

    if not sub:
        logger.warning(
            "subscription.deleted but no subscription found: stripe_sub=%s user=%s",
            event.stripe_subscription_id, event.user_id,
        )
        return

    sub.status = "expired"
    sub.updated_at = datetime.utcnow()

    # Downgrade user to FREE
    user_result = await db.execute(select(User).where(User.id == sub.user_id))
    user = user_result.scalar_one_or_none()
    if user and user.tier in ("START", "PRO", "UNLIMITED"):
        user.tier = "FREE"
        from app.services.trend_monitor import enforce_author_limits
        await enforce_author_limits(db, sub.user_id, "FREE")

    await db.commit()
    logger.info(
        "Subscription deleted (expired): user=%s stripe_sub=%s",
        sub.user_id, event.stripe_subscription_id,
    )

    # Notify user via Telegram
    if user and user.telegram_user_id and settings.telegram_bot_token:
        text = (
            f"Подписка {TIER_NAMES.get(sub.tier, sub.tier)} завершена.\n"
            f"Ваш тариф изменён на Free (3 анализа/мес).\n\n"
            f"Оформить подписку заново: {settings.app_url}/pricing"
        )
        try:
            await send_telegram_message(
                user.telegram_user_id, settings.telegram_bot_token, text,
            )
        except Exception:
            pass


async def handle_payment_cancelled(
    db: AsyncSession,
    event: WebhookEvent,
) -> None:
    """Handle normalised payment.cancelled event from any provider."""
    result = await db.execute(
        select(Payment).where(Payment.provider_payment_id == event.provider_payment_id)
    )
    payment = result.scalar_one_or_none()
    if payment:
        payment.status = "cancelled"
        await db.commit()


async def cancel_subscription(
    db: AsyncSession,
    user: User,
) -> Subscription | None:
    """Cancel active subscription. Remains active until period end.

    For Stripe subscriptions: calls Stripe API to cancel at period end.
    For others: just updates local status.
    """
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status == "active",
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None

    payment_provider = sub.payment_provider
    stripe_sub_id = sub.provider_subscription_id

    sub.status = "cancelled"
    sub.cancelled_at = datetime.utcnow()
    sub.updated_at = datetime.utcnow()
    await db.commit()

    # Cancel provider-side subscriptions AFTER db commit (don't hold locks
    # during HTTP calls). Even if the API call fails, our DB status is
    # "cancelled" and /check will reject future CP charges.

    # For Stripe: cancel via Stripe API (Stripe will send subscription.updated webhook)
    if payment_provider == "stripe" and stripe_sub_id:
        try:
            provider = get_provider("stripe")
            from app.services.payments.stripe_provider import StripeProvider
            if isinstance(provider, StripeProvider):
                await provider.cancel_subscription(stripe_sub_id)
        except Exception as e:
            logger.error("Stripe cancel error for sub=%s: %s", sub.id, e)

    # For CloudPayments: cancel recurrent subscriptions via CP API
    if payment_provider == "cloudpayments":
        try:
            provider = get_provider("cloudpayments")
            from app.services.payments.cloudpayments_provider import CloudPaymentsProvider
            if isinstance(provider, CloudPaymentsProvider):
                await provider.cancel_subscription(account_id=user.id)
        except Exception as e:
            logger.error("CloudPayments cancel error for sub=%s: %s", sub.id, e)

    logger.info("Subscription cancelled: user=%s, active until=%s", user.id, sub.current_period_end)
    return sub


async def remove_payment_method(
    db: AsyncSession,
    user: User,
) -> Subscription | None:
    """Remove saved payment method from active subscription.

    This disables auto-renewal (376-ФЗ compliance: user can remove card).
    Subscription remains active until current_period_end.
    """
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(["active", "cancelled"]),
        ).order_by(Subscription.created_at.desc()).limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub or not sub.payment_method_id:
        return None

    # For CloudPayments: cancel recurrent subscription on their side
    # so CP stops charging even though we removed the token locally.
    if sub.payment_provider == "cloudpayments":
        try:
            provider = get_provider("cloudpayments")
            from app.services.payments.cloudpayments_provider import CloudPaymentsProvider
            if isinstance(provider, CloudPaymentsProvider):
                await provider.cancel_subscription(account_id=user.id)
        except Exception as e:
            logger.error("CloudPayments cancel error on card removal for user=%s: %s", user.id, e)

    sub.payment_method_id = None
    sub.updated_at = datetime.utcnow()
    await db.commit()

    logger.info("Payment method removed: user=%s, sub=%s", user.id, sub.id)
    return sub


async def get_active_subscription(
    db: AsyncSession,
    user_id: str,
) -> Subscription | None:
    """Get user's active or cancelled-but-not-expired subscription."""
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status.in_(["active", "cancelled"]),
            Subscription.current_period_end > datetime.utcnow(),
        )
    )
    return result.scalar_one_or_none()


def generate_cancel_token(user_id: str, subscription_id: str) -> str:
    """Generate a signed cancel token (valid 7 days, HMAC-SHA256).

    Format: {user_id}:{subscription_id}:{expires_ts}:{signature}
    """
    expires = int((datetime.utcnow() + timedelta(days=7)).timestamp())
    payload = f"{user_id}:{subscription_id}:{expires}"
    sig = hmac.new(
        settings.jwt_secret.encode(), payload.encode(), hashlib.sha256,
    ).hexdigest()[:32]
    return f"{payload}:{sig}"


def _verify_cancel_token(token: str) -> tuple[str, str] | None:
    """Verify cancel token signature and expiry. Returns (user_id, sub_id) or None."""
    parts = token.split(":")
    if len(parts) != 4:
        return None
    user_id, sub_id, expires_str, sig = parts
    try:
        expires = int(expires_str)
    except ValueError:
        return None
    if datetime.utcnow().timestamp() > expires:
        return None
    payload = f"{user_id}:{sub_id}:{expires_str}"
    expected = hmac.new(
        settings.jwt_secret.encode(), payload.encode(), hashlib.sha256,
    ).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    return user_id, sub_id


async def cancel_by_token(db: AsyncSession, token: str) -> Subscription | None:
    """Cancel subscription using a signed token (no auth required).

    Used for one-click unsubscribe from email/Telegram notifications.
    """
    verified = _verify_cancel_token(token)
    if not verified:
        return None
    user_id, sub_id = verified

    result = await db.execute(
        select(Subscription).where(
            Subscription.id == sub_id,
            Subscription.user_id == user_id,
            Subscription.status == "active",
        ).with_for_update()
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return None

    is_cp = sub.payment_provider == "cloudpayments"

    sub.status = "cancelled"
    sub.cancelled_at = datetime.utcnow()
    sub.updated_at = datetime.utcnow()
    await db.commit()

    # Cancel CP recurrent subscription AFTER releasing the row lock
    # (HTTP call to CP API can take up to 15s, don't hold the lock)
    if is_cp:
        try:
            provider = get_provider("cloudpayments")
            from app.services.payments.cloudpayments_provider import CloudPaymentsProvider
            if isinstance(provider, CloudPaymentsProvider):
                await provider.cancel_subscription(account_id=user_id)
        except Exception as e:
            logger.error("CloudPayments cancel error via token for user=%s: %s", user_id, e)

    logger.info("Subscription cancelled via token: user=%s sub=%s", user_id, sub_id)
    return sub


async def expire_past_due_subscriptions(db: AsyncSession) -> int:
    """Expire subscriptions that are past due for more than 3 days.

    Called by cron task.
    """
    cutoff = datetime.utcnow() - timedelta(days=3)
    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "past_due",
            Subscription.current_period_end < cutoff,
        )
    )
    expired = 0
    for sub in result.scalars():
        sub.status = "expired"
        sub.updated_at = datetime.utcnow()

        # Downgrade user to FREE + freeze authors
        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user and user.tier in ("START", "PRO", "UNLIMITED"):
            user.tier = "FREE"
            from app.services.trend_monitor import enforce_author_limits
            await enforce_author_limits(db, user.id, "FREE")
            expired += 1

    if expired:
        await db.commit()
        logger.info("Expired %d past-due subscriptions", expired)
    return expired
