"""Billing API — checkout, subscription management, webhooks, pricing."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TIER_LIMITS, TIER_PRICING, TIER_PRICING_EUR, settings
from app.core.auth import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.tier_config import TierConfig
from app.models.subscription import ConsentLog, Payment
from app.models.user import User
from app.schemas.billing import (
    ChangeTierRequest,
    CheckoutRequest,
    CheckoutResponse,
    FeatureItem,
    PaymentItem,
    PortalResponse,
    PricingResponse,
    PricingTier,
    ProrationPreview,
    SubscriptionResponse,
)
from app.services.billing import (
    calculate_proration,
    cancel_by_token,
    cancel_scheduled_downgrade,
    cancel_subscription,
    change_tier,
    create_checkout,
    get_active_subscription,
    handle_payment_cancelled,
    handle_payment_succeeded,
    handle_subscription_deleted,
    handle_subscription_updated,
    remove_payment_method,
)
from app.services.payments import get_enabled_providers, get_provider

logger = logging.getLogger(__name__)
router = APIRouter()


async def _log_consent(
    db: AsyncSession,
    user_id: str,
    consent_type: str,
    action: str,
    request: Request | None = None,
    metadata: dict | None = None,
) -> None:
    """Record a consent grant or revocation for audit (376-ФЗ)."""
    db.add(ConsentLog(
        user_id=user_id,
        consent_type=consent_type,
        action=action,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] if request else None,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
    ))
    await db.flush()


# --- Pricing (public) ---

# Feature templates — {limit} is replaced with the actual DB value at runtime
TIER_FEATURES_TEMPLATES: dict[str, dict[str, list[dict[str, str]]]] = {
    "START": {
        "ru": [
            {"text": "{limit} сценариев в месяц", "style": "highlight"},
            {"text": "от 38₽ за сценарий", "style": "highlight"},
            {"text": "Полный разбор: хуки, структура, приёмы", "style": "normal"},
            {"text": "Готовый сценарий — бери и снимай", "style": "normal"},
            {"text": "Раздел «Что снимать» + подборка под ваши темы", "style": "normal"},
            {"text": "Мониторинг 10 блогеров — обновление каждые 12ч", "style": "normal"},
            {"text": "Быстрая обработка — результат за минуты", "style": "disabled"},
        ],
        "en": [
            {"text": "{limit} scripts per month", "style": "highlight"},
            {"text": "from €0.40 per script", "style": "highlight"},
            {"text": "Full breakdown: hooks, structure, techniques", "style": "normal"},
            {"text": "Ready-made script — just film it", "style": "normal"},
            {"text": "\"What to film\" + picks for your topics", "style": "normal"},
            {"text": "Track 10 creators — updates every 12h", "style": "normal"},
            {"text": "Fast processing — results in minutes", "style": "disabled"},
        ],
    },
    "PRO": {
        "ru": [
            {"text": "{limit} сценариев в месяц", "style": "highlight"},
            {"text": "от 33₽ за сценарий", "style": "highlight"},
            {"text": "Полный разбор: хуки, структура, приёмы", "style": "normal"},
            {"text": "Готовый сценарий — бери и снимай", "style": "normal"},
            {"text": "Раздел «Что снимать» + подборка под ваши темы", "style": "normal"},
            {"text": "Мониторинг 50 блогеров — топовые каждые 4ч", "style": "highlight"},
            {"text": "Быстрая обработка — результат за минуты", "style": "disabled"},
        ],
        "en": [
            {"text": "{limit} scripts per month", "style": "highlight"},
            {"text": "from €0.33 per script", "style": "highlight"},
            {"text": "Full breakdown: hooks, structure, techniques", "style": "normal"},
            {"text": "Ready-made script — just film it", "style": "normal"},
            {"text": "\"What to film\" + picks for your topics", "style": "normal"},
            {"text": "Track 50 creators — top ones every 4h", "style": "highlight"},
            {"text": "Fast processing — results in minutes", "style": "disabled"},
        ],
    },
    "UNLIMITED": {
        "ru": [
            {"text": "Безлимитные сценарии*", "style": "highlight"},
            {"text": "Без ограничений", "style": "highlight"},
            {"text": "Полный разбор: хуки, структура, приёмы", "style": "normal"},
            {"text": "Готовый сценарий — бери и снимай", "style": "normal"},
            {"text": "Раздел «Что снимать» + подборка под ваши темы", "style": "normal"},
            {"text": "Мониторинг 100 блогеров", "style": "highlight"},
            {"text": "Быстрая обработка — результат за минуты", "style": "highlight"},
        ],
        "en": [
            {"text": "Unlimited scripts*", "style": "highlight"},
            {"text": "No limits", "style": "highlight"},
            {"text": "Full breakdown: hooks, structure, techniques", "style": "normal"},
            {"text": "Ready-made script — just film it", "style": "normal"},
            {"text": "\"What to film\" + picks for your topics", "style": "normal"},
            {"text": "Track 100 creators", "style": "highlight"},
            {"text": "Fast processing — results in minutes", "style": "highlight"},
        ],
    },
}


@router.get("/pricing", response_model=PricingResponse)
async def get_pricing(
    currency: str = "RUB",
    db: AsyncSession = Depends(get_db),
):
    """Public pricing info. Pass currency=EUR for international pricing."""
    use_eur = currency.upper() == "EUR"
    price_table = TIER_PRICING_EUR if use_eur else TIER_PRICING
    lang_key = "en" if use_eur else "ru"

    # Load all tier configs from DB at once
    rows = (await db.execute(select(TierConfig))).scalars().all()
    db_limits = {r.name: r for r in rows}

    # Get FREE tier limit for teaser/UI
    free_cfg = db_limits.get("FREE")
    free_limit = free_cfg.max_monthly if free_cfg and free_cfg.max_monthly is not None else TIER_LIMITS.get("FREE", {}).get("max_monthly")

    tiers = []
    for tier_key, prices in price_table.items():
        # Read limit from DB, fallback to hardcoded
        cfg = db_limits.get(tier_key)
        if cfg and cfg.max_monthly is not None:
            limit_monthly_val = cfg.max_monthly
        else:
            limit_monthly_val = TIER_LIMITS.get(tier_key, {}).get("max_monthly")

        features_map = TIER_FEATURES_TEMPLATES.get(tier_key, {})
        raw_features = features_map.get(lang_key, features_map.get("en", []))
        features = [
            FeatureItem(
                text=f["text"].format(limit=limit_monthly_val if limit_monthly_val is not None else "∞"),
                style=f.get("style", "normal"),
            )
            for f in raw_features
        ]
        # UNLIMITED displays as unlimited (None), not the number
        limit_monthly = None if tier_key == "UNLIMITED" else limit_monthly_val
        tiers.append(
            PricingTier(
                tier=tier_key,
                name=tier_key.capitalize(),
                price_monthly=prices["monthly"] // 100,
                price_yearly=prices["yearly"] // 100,
                limit_monthly=limit_monthly,
                features=features,
                popular=tier_key == "PRO",
            )
        )
    return PricingResponse(tiers=tiers, free_limit=free_limit)


# --- Payment providers ---


@router.get("/providers")
async def list_providers():
    """Return enabled payment providers for the frontend."""
    return {"providers": get_enabled_providers()}


@router.get("/cloudpayments-config")
async def cloudpayments_config():
    """Return CloudPayments public ID for the frontend widget."""
    from app.config import settings as app_settings

    if not app_settings.cloudpayments_public_id:
        raise HTTPException(status_code=404, detail="CloudPayments not configured")
    return {"public_id": app_settings.cloudpayments_public_id}


# --- Checkout ---


@router.post("/checkout", response_model=CheckoutResponse)
@limiter.limit("5/minute")
async def checkout(
    request: Request,
    payload: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a payment session via the selected provider."""
    if not payload.auto_renewal_consent:
        raise HTTPException(
            status_code=400,
            detail="Необходимо согласие на автоматическое продление подписки",
        )

    # Save email if provided and user doesn't have one
    if payload.email and not user.email:
        user.email = payload.email.strip().lower()
        await db.flush()

    # Log consent (376-ФЗ audit)
    await _log_consent(
        db, user.id, "auto_renewal_granted", "granted", request,
        {"tier": payload.tier, "interval": payload.interval, "provider": payload.provider},
    )

    try:
        payment_url, payment_id, resolved_provider = await create_checkout(
            db=db,
            user=user,
            tier=payload.tier,
            interval=payload.interval,
            promo_code=payload.promo_code,
            provider_name=payload.provider,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not payment_url:
        raise HTTPException(status_code=502, detail="Payment provider error")

    return CheckoutResponse(
        payment_url=payment_url,
        payment_id=payment_id,
        provider=resolved_provider,
    )


@router.post("/validate-promo")
async def validate_promo(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate a promo code without creating a payment."""
    from app.services.promo import calculate_discounted_amount, validate_promo_code

    code = payload.get("code", "")
    tier = payload.get("tier")
    interval = payload.get("interval")
    currency = payload.get("currency", "RUB")

    if not code:
        raise HTTPException(status_code=400, detail="Code is required")

    promo, error = await validate_promo_code(db, code, user.id, tier, interval)
    if not promo:
        return {"valid": False, "error": error}

    price_table = TIER_PRICING_EUR if currency.upper() == "EUR" else TIER_PRICING
    original = price_table.get(tier or "", {}).get(interval or "", 0)
    discounted = calculate_discounted_amount(original, promo) if original else 0

    return {
        "valid": True,
        "discount_percent": promo.discount_percent,
        "original_amount": original // 100,
        "discounted_amount": discounted // 100,
        "remaining_uses": (promo.max_uses - promo.used_count) if promo.max_uses else None,
    }


# --- Subscription ---


@router.get("/subscription")
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's active subscription."""
    sub = await get_active_subscription(db, user.id)
    if not sub:
        return {"subscription": None}
    data = SubscriptionResponse.model_validate(sub).model_dump()
    data["has_payment_method"] = bool(sub.payment_method_id)
    data["auto_renewal_enabled"] = bool(sub.payment_method_id) and sub.status == "active"
    return {"subscription": data}


# --- Proration / Tier Change ---


@router.get("/proration-preview", response_model=ProrationPreview)
async def proration_preview(
    new_tier: str,
    new_interval: str = "monthly",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Preview proration cost for changing tier."""
    from app.config import TIER_PRICING, TIER_PRICING_EUR

    if new_tier not in TIER_PRICING:
        raise HTTPException(status_code=400, detail=f"Unknown tier: {new_tier}")
    if new_interval not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail=f"Unknown interval: {new_interval}")

    sub = await get_active_subscription(db, user.id)

    if not sub:
        # FREE user: return full price (no proration)
        currency = "RUB"  # default
        price_table = TIER_PRICING
        # Try to determine currency from user's Stripe customer
        if user.stripe_customer_id:
            currency = "EUR"
            price_table = TIER_PRICING_EUR
        full_price = price_table[new_tier][new_interval]
        return ProrationPreview(
            proration_amount=full_price,
            credit=0,
            charge=full_price,
            new_price_full=full_price,
            currency=currency,
            days_remaining=0,
            next_billing_date=None,
            is_upgrade=True,
        )

    # Same tier+interval = no-op
    if sub.tier == new_tier and sub.billing_interval == new_interval:
        raise HTTPException(status_code=400, detail="Already on this tier and interval")

    result = calculate_proration(sub, new_tier, new_interval)
    return ProrationPreview(**result)


@router.post("/change-tier")
@limiter.limit("5/minute")
async def change_tier_endpoint(
    request: Request,
    payload: ChangeTierRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change subscription tier (upgrade or downgrade).

    Upgrade: calculates proration, returns payment info.
    Downgrade: schedules tier change at period end.
    """
    if not payload.auto_renewal_consent:
        raise HTTPException(
            status_code=400,
            detail="Необходимо согласие на автоматическое продление подписки",
        )

    # Log consent (376-ФЗ)
    await _log_consent(
        db, user.id, "tier_change", "granted", request,
        {"new_tier": payload.new_tier, "new_interval": payload.new_interval},
    )

    try:
        result = await change_tier(db, user, payload.new_tier, payload.new_interval)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@router.delete("/scheduled-downgrade")
async def cancel_downgrade(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a scheduled downgrade."""
    sub = await cancel_scheduled_downgrade(db, user)
    if not sub:
        raise HTTPException(status_code=404, detail="No scheduled downgrade found")

    data = SubscriptionResponse.model_validate(sub).model_dump()
    return {"ok": True, "subscription": data}


@router.post("/cancel")
async def cancel(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel active subscription. Remains active until period end."""
    sub = await cancel_subscription(db, user)
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription")

    await _log_consent(
        db, user.id, "auto_renewal_revoked", "revoked", request,
        {"tier": sub.tier, "reason": "user_cancelled"},
    )
    await db.commit()

    return {
        "ok": True,
        "message": "Подписка отменена. Доступ сохранится до конца оплаченного периода.",
        "active_until": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


# --- Payment method management (376-ФЗ) ---


@router.delete("/payment-method")
async def delete_payment_method(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove saved payment method. Disables auto-renewal (376-ФЗ)."""
    sub = await remove_payment_method(db, user)
    if not sub:
        raise HTTPException(status_code=404, detail="No saved payment method found")

    await _log_consent(
        db, user.id, "card_removed", "revoked", request,
        {"tier": sub.tier, "reason": "card_removed"},
    )
    await db.commit()

    return {
        "ok": True,
        "message": "Карта удалена. Автопродление отключено.",
    }


# --- Stripe Customer Portal ---


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Customer Portal session for managing subscription."""
    if not user.stripe_customer_id:
        raise HTTPException(status_code=404, detail="No Stripe subscription found")

    try:
        provider = get_provider("stripe")
    except ValueError:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    from app.services.payments.stripe_provider import StripeProvider
    if not isinstance(provider, StripeProvider):
        raise HTTPException(status_code=503, detail="Stripe provider unavailable")

    url = await provider.create_portal_session(
        customer_id=user.stripe_customer_id,
        return_url=f"{settings.app_url}/settings",
    )
    if not url:
        raise HTTPException(status_code=502, detail="Could not create portal session")

    return PortalResponse(url=url)


# --- One-click cancel (376-ФЗ: easy unsubscribe) ---


@router.post("/cancel-by-token")
@limiter.limit("10/minute")
async def cancel_by_token_endpoint(
    request: Request,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Cancel subscription via signed token (no auth required).

    Used for one-click unsubscribe from email/Telegram notifications.
    """
    token = payload.get("token", "")
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    sub = await cancel_by_token(db, token)
    if not sub:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Log consent revocation
    await _log_consent(
        db, sub.user_id, "auto_renewal_revoked", "revoked", request,
        {"tier": sub.tier, "reason": "one_click_cancel"},
    )
    await db.commit()

    return {
        "ok": True,
        "message": "Подписка отменена. Доступ сохранится до конца оплаченного периода.",
        "active_until": sub.current_period_end.isoformat() if sub.current_period_end else None,
    }


# --- Payment history ---


@router.get("/payments")
async def list_payments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's payment history."""
    result = await db.execute(
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(50)
    )
    payments = result.scalars().all()
    return {
        "payments": [
            PaymentItem.model_validate(p).model_dump() for p in payments
        ]
    }


# --- Webhooks (per provider) ---


async def _handle_webhook(request: Request, provider_name: str, db: AsyncSession) -> dict:
    """Generic webhook handler — delegates parsing to the provider."""
    try:
        provider = get_provider(provider_name)
    except ValueError:
        raise HTTPException(status_code=503, detail=f"Provider '{provider_name}' not configured")

    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        event = await provider.parse_webhook(body, headers)
    except ValueError as e:
        logger.warning("Webhook verification failed (%s): %s", provider_name, e)
        raise HTTPException(status_code=403, detail=str(e))

    if event is None:
        return {"ok": True}  # event type we don't handle

    if event.event_type == "payment.succeeded":
        user, sub = await handle_payment_succeeded(db, event)
        if user and sub:
            try:
                from app.core.showcase_tracker import emit_showcase_event

                await emit_showcase_event(
                    "payment",
                    tier=sub.tier or "",
                    amount=str(event.amount_minor),
                    currency=event.currency,
                )
            except Exception:
                pass
            try:
                from app.workers.billing_tasks import _notify_user_renewed
                await _notify_user_renewed(user, sub)
            except Exception:
                pass  # best-effort
            try:
                from app.workers.billing_tasks import _notify_admin_payment
                await _notify_admin_payment(user, sub)
            except Exception:
                pass  # best-effort
    elif event.event_type == "payment.cancelled":
        await handle_payment_cancelled(db, event)
    elif event.event_type == "subscription.updated":
        await handle_subscription_updated(db, event)
    elif event.event_type == "subscription.deleted":
        await handle_subscription_deleted(db, event)
    else:
        logger.debug("Unhandled webhook event: %s (%s)", event.event_type, provider_name)

    return {"ok": True}


@router.post("/webhook/yookassa")
@limiter.limit("60/minute")
async def webhook_yookassa(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle YooKassa webhook notifications."""
    return await _handle_webhook(request, "yookassa", db)


@router.post("/webhook/stripe")
@limiter.limit("60/minute")
async def webhook_stripe(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook notifications."""
    return await _handle_webhook(request, "stripe", db)


# --- CloudPayments webhooks ---
# CloudPayments sends different notification types to separate URLs
# and expects {"code": 0} as success response.


@router.post("/webhook/cloudpayments/check")
@limiter.limit("60/minute")
async def webhook_cloudpayments_check(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """CloudPayments Check notification — validate order before charging.

    For recurrent payments, also checks that the user's subscription
    is still active (not cancelled/expired) — rejects if not.
    """
    from app.models.subscription import Subscription

    # Verify HMAC-SHA256 signature (same as other CP webhooks)
    raw_body = await request.body()
    try:
        provider = get_provider("cloudpayments")
        provider._verify_signature(raw_body, {k.lower(): v for k, v in request.headers.items()})
    except (ValueError, Exception) as e:
        logger.warning("CloudPayments /check signature verification failed: %s", e)
        return {"code": 13}

    # CloudPayments sends form-urlencoded or JSON depending on config
    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            body = json.loads(raw_body)
        else:
            from urllib.parse import parse_qs
            parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
            body = {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    except Exception:
        logger.warning("CloudPayments /check: failed to parse body")
        return {"code": 13}  # technical error — reject unknown requests

    amount = body.get("Amount")
    data_raw = body.get("Data") or ""

    try:
        metadata = json.loads(data_raw) if isinstance(data_raw, str) and data_raw else {}
    except (ValueError, TypeError):
        metadata = {}

    tier = metadata.get("tier", "").upper()
    interval = metadata.get("interval", "monthly")
    user_id = metadata.get("user_id") or body.get("AccountId", "")

    # Reject recurrent charges for cancelled/expired subscriptions
    if user_id:
        sub_result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.payment_provider == "cloudpayments",
            ).order_by(Subscription.updated_at.desc().nulls_last()).limit(1)
        )
        sub = sub_result.scalar_one_or_none()
        if sub and sub.status in ("cancelled", "expired"):
            logger.info(
                "CloudPayments check: rejecting charge for %s subscription user=%s",
                sub.status, user_id,
            )
            return {"code": 10}

    # Security: validate amount against server-side checkout intent.
    # Look up Payment record by InvoiceId — it stores the exact expected amount.
    from app.models.subscription import Payment
    invoice_id = body.get("InvoiceId", "")
    if invoice_id and amount is not None:
        pay_result = await db.execute(
            select(Payment).where(
                Payment.provider_payment_id == str(invoice_id),
            )
        )
        checkout_payment = pay_result.scalar_one_or_none()
        if checkout_payment and checkout_payment.status == "succeeded":
            # Payment already processed (retry /check after /pay) — accept
            return {"code": 0}
        if checkout_payment and checkout_payment.expected_amount_kopecks:
            expected_rubles = checkout_payment.expected_amount_kopecks / 100
            try:
                actual = float(amount)
            except (ValueError, TypeError):
                return {"code": 13}
            if abs(actual - expected_rubles) > 0.01:
                logger.warning(
                    "CloudPayments check: amount mismatch invoiceId=%s expected=%.2f got=%.2f — rejecting",
                    invoice_id, expected_rubles, actual,
                )
                return {"code": 10}  # reject — spoofed amount
        elif not checkout_payment and not str(body.get("Recurrent", "")).lower() == "true":
            # First payment without checkout record — reject
            logger.warning(
                "CloudPayments check: no checkout record for invoiceId=%s — rejecting",
                invoice_id,
            )
            return {"code": 13}  # technical error — CP may retry

    # Fallback: validate amount against tier pricing (for recurrent or missing checkout)
    if tier and interval and amount is not None:
        expected_kopecks = TIER_PRICING.get(tier, {}).get(interval)
        if expected_kopecks is not None:
            expected_rubles = expected_kopecks / 100
            try:
                actual = float(amount)
            except (ValueError, TypeError):
                return {"code": 0}  # can't parse — let pay webhook handle it
            if abs(actual - expected_rubles) > 0.01:
                logger.warning(
                    "CloudPayments check: amount mismatch tier=%s interval=%s "
                    "expected=%.2f got=%.2f", tier, interval, expected_rubles, actual,
                )
                return {"code": 10}  # reject — spoofed amount (over or under)

    # Security: validate recurrent.amount in widget data hasn't been tampered with.
    # The client receives data.CloudPayments.recurrent in widget_params and could
    # modify recurrent.amount before passing it to the CP widget.  We compare
    # against the expected full-price tier amount (before promo).
    cp_nested = metadata.get("CloudPayments", {})
    recurrent_cfg = cp_nested.get("recurrent", {}) if isinstance(cp_nested, dict) else {}
    if recurrent_cfg and isinstance(recurrent_cfg, dict):
        recurrent_amount = recurrent_cfg.get("amount")
        if recurrent_amount is not None and tier and interval:
            expected_recurrent_kopecks = TIER_PRICING.get(tier, {}).get(interval)
            if expected_recurrent_kopecks is not None:
                expected_recurrent_rubles = expected_recurrent_kopecks / 100
                try:
                    actual_recurrent = float(recurrent_amount)
                except (ValueError, TypeError):
                    actual_recurrent = 0
                if abs(actual_recurrent - expected_recurrent_rubles) > 0.01:
                    logger.warning(
                        "CloudPayments check: recurrent amount tampered tier=%s interval=%s "
                        "expected=%.2f got=%.2f user=%s — rejecting",
                        tier, interval, expected_recurrent_rubles, actual_recurrent, user_id,
                    )
                    return {"code": 10}  # reject — recurrent amount spoofed

    return {"code": 0}


@router.post("/webhook/cloudpayments/pay")
@limiter.limit("60/minute")
async def webhook_cloudpayments_pay(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """CloudPayments Pay notification — payment succeeded."""
    try:
        result = await _handle_webhook(request, "cloudpayments", db)
    except HTTPException:
        # CloudPayments expects {"code": 0} even on errors (to stop retries)
        return {"code": 13}
    return {"code": 0}


@router.post("/webhook/cloudpayments/fail")
@limiter.limit("60/minute")
async def webhook_cloudpayments_fail(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """CloudPayments Fail notification — payment declined."""
    try:
        await _handle_webhook(request, "cloudpayments", db)
    except HTTPException:
        pass
    return {"code": 0}


@router.post("/webhook/cloudpayments/refund")
@limiter.limit("60/minute")
async def webhook_cloudpayments_refund(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """CloudPayments Refund notification — payment refunded (chargeback or manual).

    When a user disputes a charge with their bank or we issue a refund
    via CP dashboard, cancel their subscription and downgrade to FREE.
    """
    from app.models.subscription import Subscription
    from app.models.user import User

    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        provider = get_provider("cloudpayments")
        provider._verify_signature(raw_body, headers)
    except (ValueError, Exception) as e:
        logger.warning("CP /refund signature verification failed: %s", e)
        return {"code": 0}

    try:
        body = provider._parse_body(raw_body, headers)
    except Exception:
        return {"code": 0}

    account_id = body.get("AccountId", "")
    transaction_id = body.get("TransactionId", "")
    amount = body.get("Amount", 0)

    logger.warning(
        "CP refund received: account=%s transaction=%s amount=%s",
        account_id, transaction_id, amount,
    )

    if not account_id:
        return {"code": 0}

    # Find and cancel the user's active subscription
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == account_id,
            Subscription.payment_provider == "cloudpayments",
            Subscription.status.in_(["active", "past_due"]),
        ).order_by(Subscription.updated_at.desc().nulls_last()).limit(1)
    )
    sub = result.scalar_one_or_none()
    if sub:
        from datetime import datetime
        sub.status = "cancelled"
        sub.cancelled_at = datetime.utcnow()
        sub.updated_at = datetime.utcnow()
        await db.commit()

        # Cancel CP recurrent subscription (prevent future charges)
        try:
            from app.services.payments.cloudpayments_provider import CloudPaymentsProvider
            if isinstance(provider, CloudPaymentsProvider):
                await provider.cancel_subscription(account_id=account_id)
        except Exception as e:
            logger.error("CP cancel after refund error: %s", e)

        # Notify user
        user_result = await db.execute(select(User).where(User.id == account_id))
        user = user_result.scalar_one_or_none()
        if user and user.telegram_user_id and settings.telegram_bot_token:
            from app.services.telegram import send_telegram_message
            text = (
                "Произведён возврат средств за подписку.\n"
                "Подписка отменена.\n\n"
                f"Оформить заново: {settings.app_url}/pricing"
            )
            try:
                await send_telegram_message(
                    user.telegram_user_id, settings.telegram_bot_token, text,
                )
            except Exception:
                pass

        logger.info("Subscription cancelled due to refund: user=%s sub=%s", account_id, sub.id)

    # Update payment record
    if transaction_id:
        from app.models.subscription import Payment
        pay_result = await db.execute(
            select(Payment).where(Payment.provider_payment_id == str(transaction_id))
        )
        payment = pay_result.scalar_one_or_none()
        if payment:
            payment.status = "refunded"
            await db.commit()

    return {"code": 0}


@router.post("/webhook/cloudpayments/cancel")
@limiter.limit("60/minute")
async def webhook_cloudpayments_cancel(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """CloudPayments Cancel notification — payment voided before completion."""
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        provider = get_provider("cloudpayments")
        provider._verify_signature(raw_body, headers)
    except (ValueError, Exception) as e:
        logger.warning("CP /cancel signature verification failed: %s", e)
        return {"code": 0}

    try:
        body = provider._parse_body(raw_body, headers)
    except Exception:
        return {"code": 0}

    transaction_id = body.get("TransactionId", "")
    logger.info("CP cancel received: transaction=%s", transaction_id)

    # Update payment record to cancelled
    if transaction_id:
        from app.models.subscription import Payment
        pay_result = await db.execute(
            select(Payment).where(Payment.provider_payment_id == str(transaction_id))
        )
        payment = pay_result.scalar_one_or_none()
        if payment:
            payment.status = "cancelled"
            await db.commit()

    return {"code": 0}


@router.post("/webhook/cloudpayments/recurrent")
@limiter.limit("60/minute")
async def webhook_cloudpayments_recurrent(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """CloudPayments Recurrent notification — subscription status change.

    This is NOT a payment webhook. CP sends it when a subscription's status
    changes (e.g. auto-cancelled after 3 failed charge attempts).
    Successful/failed recurring charges go to /pay and /fail endpoints.
    """
    from app.models.subscription import Subscription
    from app.models.user import User
    from app.services.payments.cloudpayments_provider import CloudPaymentsProvider

    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        provider = get_provider("cloudpayments")
        if not isinstance(provider, CloudPaymentsProvider):
            return {"code": 0}

        status_info = provider.parse_recurrent_status(raw_body, headers)
    except ValueError as e:
        logger.warning("CP /recurrent signature verification failed: %s", e)
        return {"code": 0}
    except Exception as e:
        logger.error("CP /recurrent parse error: %s", e)
        return {"code": 0}

    if not status_info:
        return {"code": 0}  # informational status, no action

    # CP auto-cancelled subscription (e.g. after 3 failed retries)
    account_id = status_info["account_id"]
    cp_status = status_info["status"]

    logger.warning(
        "CP subscription %s for account=%s (failed_txns=%d)",
        cp_status, account_id, status_info.get("failed_transactions", 0),
    )

    # Find the user's active CP subscription
    result = await db.execute(
        select(Subscription).where(
            Subscription.user_id == account_id,
            Subscription.payment_provider == "cloudpayments",
            Subscription.status.in_(["active", "past_due"]),
        ).order_by(Subscription.updated_at.desc().nulls_last()).limit(1)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        logger.info("CP /recurrent: no active sub for account=%s, ignoring", account_id)
        return {"code": 0}

    # CP sends Cancelled/Rejected/Expired ONCE after exhausting retries.
    # No second webhook will arrive — transition directly to past_due
    # and let handle_past_due_subscriptions expire after grace period.
    # If already past_due — expire immediately.
    #
    # IMPORTANT: If the Cancelled status is a side-effect of our own
    # cancel_subscription() call in create_checkout() (user upgrading),
    # ignore it — the user has a pending checkout for a new tier.
    from datetime import datetime
    if sub.status == "active":
        from app.workers.billing_tasks import _should_ignore_cp_recurrent_cancelled
        if cp_status == "Cancelled" and await _should_ignore_cp_recurrent_cancelled(db, account_id):
            logger.info(
                "CP /recurrent Cancelled ignored: user=%s has pending checkout, "
                "likely our cancel_subscription() during upgrade",
                account_id,
            )
            return {"code": 0}

        sub.status = "past_due"
        sub.updated_at = datetime.utcnow()
        await db.commit()

        user_result = await db.execute(select(User).where(User.id == account_id))
        user = user_result.scalar_one_or_none()
        if user:
            from app.workers.billing_tasks import _notify_user_payment_failed
            await _notify_user_payment_failed(user, sub)

    elif sub.status == "past_due":
        sub.status = "expired"
        sub.updated_at = datetime.utcnow()

        user_result = await db.execute(select(User).where(User.id == account_id))
        user = user_result.scalar_one_or_none()
        if user and user.tier in ("START", "PRO", "UNLIMITED"):
            user.tier = "FREE"
            from app.services.trend_monitor import enforce_author_limits
            await enforce_author_limits(db, account_id, "FREE")

        await db.commit()

        if user:
            from app.workers.billing_tasks import _notify_user_expired
            await _notify_user_expired(user, sub)

    logger.info(
        "CP /recurrent handled: account=%s sub=%s status=%s→%s",
        account_id, sub.id, cp_status, sub.status,
    )
    return {"code": 0}


# Legacy alias — keep the old /webhook path working for YooKassa
@router.post("/webhook")
@limiter.limit("60/minute")
async def webhook_legacy(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Legacy YooKassa webhook endpoint (backwards compatibility)."""
    return await _handle_webhook(request, "yookassa", db)
