"""Billing background tasks — recurring payments, grace period, notifications."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TIER_PRICING, settings
from app.models.subscription import Payment, Subscription
from app.models.user import User
from app.services.billing import INTERVAL_DAYS, TIER_NAMES, generate_cancel_token, handle_payment_succeeded
from app.services.payments.base import WebhookEvent
from app.services.email_sender import send_dunning_email, send_renewal_confirmed_email, send_renewal_reminder_email
from app.services.telegram import send_telegram_message
from app.services.yookassa_client import create_payment

logger = logging.getLogger(__name__)


async def process_recurring_payments(db: AsyncSession) -> int:
    """Find active subscriptions past period_end and charge saved payment method.

    Only processes YooKassa subscriptions — CloudPayments manages its own
    recurrence via their subscriptions API and sends /recurrent webhooks.

    Returns number of payments initiated.
    """
    now = datetime.utcnow()

    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.current_period_end < now,
            Subscription.payment_method_id.isnot(None),
            # CloudPayments manages recurrence on their side — skip
            Subscription.payment_provider != "cloudpayments",
            # Admin-granted subscriptions have no payment method — skip
            Subscription.payment_provider != "admin",
        )
    )
    subs = result.scalars().all()
    if not subs:
        return 0

    charged = 0
    for sub in subs:
        try:
            # If a downgrade is scheduled, use the new tier's price
            charge_tier = sub.scheduled_tier or sub.tier
            charge_interval = sub.scheduled_interval or sub.billing_interval

            # Use stored amount or look up from pricing
            if sub.scheduled_tier:
                # Downgrade: charge at new (lower) price
                pricing = TIER_PRICING.get(charge_tier, {})
                amount = pricing.get(charge_interval, 0)
            else:
                amount = sub.amount_kopecks
                if not amount:
                    pricing = TIER_PRICING.get(sub.tier, {})
                    amount = pricing.get(sub.billing_interval, 0)
            if not amount:
                logger.warning("No amount for subscription %s", sub.id)
                continue

            description = f"ВидеоРентген {TIER_NAMES.get(charge_tier, charge_tier)} ({charge_interval}) — автопродление"

            # Get user email for receipt
            user_result = await db.execute(select(User).where(User.id == sub.user_id))
            user = user_result.scalar_one_or_none()
            if user and user.is_seed:
                continue
            email = user.email if user else ""

            result_json = await create_payment(
                amount_kopecks=amount,
                description=description,
                return_url=f"{settings.app_url}/settings",
                payment_method_id=sub.payment_method_id,
                metadata={
                    "user_id": sub.user_id,
                    "tier": charge_tier,
                    "interval": charge_interval,
                    "email": email or "",
                    "recurring": "true",
                },
            )

            import json
            payment_data = json.loads(result_json) if isinstance(result_json, str) else result_json

            # If auto-payment succeeds immediately (status=succeeded)
            if payment_data.get("status") == "succeeded":
                event = WebhookEvent(
                    event_type="payment.succeeded",
                    provider_payment_id=payment_data.get("id", ""),
                    provider_name="yookassa",
                    user_id=sub.user_id,
                    tier=charge_tier,
                    interval=charge_interval,
                    amount_minor=amount,
                    currency=payment_data.get("amount", {}).get("currency", "RUB"),
                    payment_method=payment_data.get("payment_method", {}).get("type", "bank_card"),
                    promo_code="",
                    original_amount_minor=amount,
                    raw_data=payment_data,
                )
                _, renewed_sub = await handle_payment_succeeded(db, event)
                charged += 1
                await _notify_user_renewed(user, renewed_sub or sub)
                await _notify_admin_payment(user, renewed_sub or sub)
            elif payment_data.get("status") == "pending":
                # Will be handled by webhook
                charged += 1
            else:
                # Payment failed — mark as past_due
                sub.status = "past_due"
                sub.updated_at = now
                await db.commit()
                await _notify_user_payment_failed(user, sub)
                logger.warning(
                    "Recurring payment failed for sub=%s status=%s",
                    sub.id, payment_data.get("status"),
                )

        except Exception as e:
            logger.error("Recurring payment error for sub=%s: %s", sub.id, e)
            sub.status = "past_due"
            sub.updated_at = now
            await db.commit()

    logger.info("Processed %d recurring payments", charged)
    return charged


async def mark_stale_cp_subscriptions(db: AsyncSession) -> int:
    """Mark CloudPayments subscriptions as past_due if period ended 2+ days ago.

    CloudPayments manages recurrence on their side. If CP failed to charge
    and didn't send a webhook, the subscription stays 'active' with an expired
    period_end indefinitely. This catches those cases.

    Uses 2-day cutoff to avoid false alarms — CP may retry failed charges
    within 24-48 hours before sending a /fail webhook.
    """
    cutoff = datetime.utcnow() - timedelta(days=2)
    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.payment_provider == "cloudpayments",
            Subscription.current_period_end < cutoff,
        )
    )
    marked = 0
    for sub in result.scalars():
        sub.status = "past_due"
        sub.updated_at = datetime.utcnow()
        marked += 1

        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user and user.is_seed:
            continue
        await _notify_user_payment_failed(user, sub)

    if marked:
        await db.commit()
        logger.info("Marked %d stale CloudPayments subscriptions as past_due", marked)
    return marked


async def handle_past_due_subscriptions(db: AsyncSession) -> int:
    """Expire subscriptions past_due for more than 3 days.

    Returns number of expired subscriptions.
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

        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user and user.is_seed:
            continue
        if user and user.tier in ("START", "PRO", "UNLIMITED"):
            user.tier = "FREE"
            from app.services.trend_monitor import enforce_author_limits
            await enforce_author_limits(db, user.id, "FREE")
            expired += 1
            await _notify_user_expired(user, sub)

    if expired:
        await db.commit()
        logger.info("Expired %d past-due subscriptions", expired)
    return expired


async def expire_cancelled_subscriptions(db: AsyncSession) -> int:
    """Expire cancelled subscriptions past their period end.

    When a user cancels, they retain access until current_period_end.
    After that, downgrade tier to FREE.
    """
    now = datetime.utcnow()

    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "cancelled",
            Subscription.current_period_end < now,
        )
    )
    expired = 0
    for sub in result.scalars():
        sub.status = "expired"
        sub.updated_at = now

        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user and user.is_seed:
            continue
        if user and user.tier in ("START", "PRO", "UNLIMITED"):
            user.tier = "FREE"
            from app.services.trend_monitor import enforce_author_limits
            await enforce_author_limits(db, user.id, "FREE")
            expired += 1
            await _notify_user_expired(user, sub)

    if expired:
        await db.commit()
        logger.info("Expired %d cancelled subscriptions", expired)
    return expired


async def send_renewal_reminders(db: AsyncSession) -> int:
    """Send reminders 3 days before subscription period ends.

    Returns number of reminders sent.
    """
    now = datetime.utcnow()
    reminder_window_start = now + timedelta(days=2, hours=12)
    reminder_window_end = now + timedelta(days=3, hours=12)

    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.payment_provider != "admin",
            Subscription.current_period_end >= reminder_window_start,
            Subscription.current_period_end < reminder_window_end,
        )
    )

    sent = 0
    for sub in result.scalars():
        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user and user.is_seed:
            continue
        if not user:
            continue

        amount_rub = sub.amount_kopecks // 100
        token = generate_cancel_token(sub.user_id, sub.id)
        cancel_url = f"{settings.app_url}/cancel-subscription?token={token}"
        tier_name = TIER_NAMES.get(sub.tier, sub.tier)
        charge_date = ""
        if sub.current_period_end:
            charge_date = sub.current_period_end.strftime("%d.%m.%Y")

        # Telegram notification
        tg_ok = False
        if user.telegram_user_id:
            text = (
                f"Напоминание: через 3 дня произойдёт автопродление подписки "
                f"{tier_name} "
                f"на сумму {amount_rub} ₽.\n\n"
                f"Отменить подписку: {cancel_url}\n"
                f"Управление подпиской: {settings.app_url}/settings"
            )
            try:
                await send_telegram_message(
                    user.telegram_user_id, settings.telegram_bot_token, text,
                )
                tg_ok = True
            except Exception as e:
                logger.error("Failed to send renewal reminder TG to user=%s: %s", user.id, e)

        # Email notification (376-ФЗ)
        email_ok = False
        if user.email:
            try:
                await send_renewal_reminder_email(
                    to_email=user.email,
                    tier_name=tier_name,
                    amount=f"{amount_rub} ₽",
                    charge_date=charge_date,
                    cancel_url=cancel_url,
                )
                email_ok = True
            except Exception as e:
                logger.error("Failed to send renewal reminder email to user=%s: %s", user.id, e)

        if tg_ok or email_ok:
            sent += 1

    if sent:
        logger.info("Sent %d renewal reminders", sent)
    return sent


async def send_dunning_reminders(db: AsyncSession) -> int:
    """Send follow-up dunning notifications for past_due subscriptions.

    Day 0: handled by _notify_user_payment_failed() at the time of failure.
    Day 1: gentle reminder (this function).
    Day 2: final warning — "subscription expires tomorrow" (this function).

    Uses current_period_end as the anchor: days_overdue = (now - period_end).days.
    Runs hourly, but only sends one email per day-bucket by checking
    the time window (e.g. day 1 = 24-48h after period_end).
    """
    now = datetime.utcnow()

    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "past_due",
            Subscription.payment_provider != "admin",
            Subscription.current_period_end.isnot(None),
        )
    )

    sent = 0
    for sub in result.scalars():
        overdue = now - sub.current_period_end
        overdue_hours = overdue.total_seconds() / 3600

        # Determine which dunning day (skip day 0 — already sent at failure time).
        # Wide windows (24h each) so scheduler restarts don't skip a day.
        if 24 <= overdue_hours < 48:
            dunning_day = 1
        elif 48 <= overdue_hours < 72:
            dunning_day = 2
        else:
            continue  # not in a dunning window

        # Dedup: don't re-send if updated_at is recent (within 20h).
        # Each dunning send touches updated_at, preventing hourly repeats.
        if sub.updated_at and (now - sub.updated_at).total_seconds() < 20 * 3600:
            continue

        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user and user.is_seed:
            continue
        if not user:
            continue

        tier_name = TIER_NAMES.get(sub.tier, sub.tier)

        # Telegram
        if user.telegram_user_id and settings.telegram_bot_token:
            if dunning_day == 1:
                text = (
                    f"Напоминание: оплата подписки {tier_name} не прошла.\n\n"
                    f"Обновите способ оплаты: {settings.app_url}/settings"
                )
            else:
                text = (
                    f"Завтра подписка {tier_name} будет отменена.\n\n"
                    f"Обновите способ оплаты прямо сейчас: {settings.app_url}/settings"
                )
            try:
                await send_telegram_message(
                    user.telegram_user_id, settings.telegram_bot_token, text,
                )
            except Exception:
                pass

        # Email
        if user.email:
            try:
                await send_dunning_email(
                    to_email=user.email,
                    tier_name=tier_name,
                    day=dunning_day,
                    settings_url=f"{settings.app_url}/settings",
                )
            except Exception:
                pass

        # Mark as sent to prevent re-sending within the same window
        sub.updated_at = now
        sent += 1

    if sent:
        await db.commit()
        logger.info("Sent %d dunning reminders", sent)
    return sent


# --- Admin payment notification ---

async def _notify_admin_payment(user: User | None, sub: Subscription) -> None:
    """Send Telegram notification to admin about incoming payment."""
    if not settings.telegram_bot_token or not settings.admin_telegram_ids:
        return
    if not sub:
        return

    from app.services.telegram import send_telegram_message, escape_html

    amount_minor = (sub.paid_amount_kopecks or sub.amount_kopecks or 0) // 100
    currency_symbol = "€" if getattr(sub, "currency", "RUB") == "EUR" else "₽"
    amount_str = f"{currency_symbol}{amount_minor}" if currency_symbol == "€" else f"{amount_minor} ₽"
    tier_name = TIER_NAMES.get(sub.tier, sub.tier)
    interval_label = "год" if sub.billing_interval == "yearly" else "мес"
    provider = sub.payment_provider or "unknown"

    user_name = "?"
    if user:
        user_name = user.name or user.email or f"User {str(user.id)[:8]}"

    message = (
        f"💰 <b>Оплата получена</b>\n\n"
        f"👤 {escape_html(user_name)}\n"
        f"📦 {escape_html(tier_name)} ({interval_label})\n"
        f"💵 {escape_html(amount_str)}\n"
        f"🏦 {escape_html(provider)}"
    )

    admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
    for admin_tg_id in admin_ids:
        try:
            await send_telegram_message(
                chat_id=admin_tg_id,
                bot_token=settings.telegram_bot_token,
                text=message,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Failed to send payment notification to admin %s: %s", admin_tg_id, e)


# --- Telegram notification helpers ---

async def _notify_user_renewed(user: User | None, sub: Subscription) -> None:
    """Notify user that subscription was auto-renewed."""
    if not user:
        return
    amount_minor = (sub.amount_kopecks or 0) // 100
    currency_symbol = "€" if getattr(sub, "currency", "RUB") == "EUR" else "₽"
    amount_str = f"{currency_symbol}{amount_minor}" if currency_symbol == "€" else f"{amount_minor} ₽"
    tier_name = TIER_NAMES.get(sub.tier, sub.tier)
    end_date = ""
    if sub.current_period_end:
        end_date = sub.current_period_end.strftime("%d.%m.%Y")

    # Telegram
    if user.telegram_user_id and settings.telegram_bot_token:
        text = (
            f"Подписка {tier_name} продлена.\n"
            f"Списано: {amount_str}\n"
            f"Активна до: {end_date}\n\n"
            f"Управление подпиской: {settings.app_url}/settings"
        )
        try:
            await send_telegram_message(
                user.telegram_user_id, settings.telegram_bot_token, text,
            )
        except Exception:
            pass

    # Email
    if user.email:
        try:
            await send_renewal_confirmed_email(
                to_email=user.email,
                tier_name=tier_name,
                amount=amount_str,
                active_until=end_date,
                settings_url=f"{settings.app_url}/settings",
            )
        except Exception:
            pass


async def _notify_user_payment_failed(user: User | None, sub: Subscription) -> None:
    """Notify user that recurring payment failed."""
    if not user:
        return
    token = generate_cancel_token(sub.user_id, sub.id)
    cancel_url = f"{settings.app_url}/cancel-subscription?token={token}"

    # Telegram
    if user.telegram_user_id and settings.telegram_bot_token:
        text = (
            f"Не удалось списать оплату за подписку {TIER_NAMES.get(sub.tier, sub.tier)}.\n\n"
            f"У вас есть 3 дня чтобы обновить способ оплаты, "
            f"после чего подписка будет отменена.\n\n"
            f"Обновить: {settings.app_url}/settings\n"
            f"Отменить подписку: {cancel_url}"
        )
        try:
            await send_telegram_message(
                user.telegram_user_id, settings.telegram_bot_token, text,
            )
        except Exception:
            pass

    # Email
    if user.email:
        try:
            from app.services.email_sender import _send_email, _billing_email_html
            email_html = _billing_email_html(
                "Ошибка оплаты подписки",
                [
                    f"Не удалось списать оплату за подписку <b>{TIER_NAMES.get(sub.tier, sub.tier)}</b>.",
                    "У вас есть 3 дня чтобы обновить способ оплаты, после чего подписка будет отменена.",
                ],
                "Управление подпиской",
                f"{settings.app_url}/settings",
            )
            await _send_email(user.email, "ВидеоРентген — ошибка оплаты подписки", email_html)
        except Exception:
            pass


async def _notify_user_expired(user: User | None, sub: Subscription) -> None:
    """Notify user that subscription expired."""
    if not user or not user.telegram_user_id or not settings.telegram_bot_token:
        return
    text = (
        f"Подписка {TIER_NAMES.get(sub.tier, sub.tier)} истекла.\n"
        f"Ваш тариф изменён на Free (3 анализа/мес).\n\n"
        f"Оформить подписку заново: {settings.app_url}/pricing"
    )
    try:
        await send_telegram_message(
            user.telegram_user_id, settings.telegram_bot_token, text,
        )
    except Exception:
        pass


async def _should_ignore_cp_recurrent_cancelled(
    db: AsyncSession, user_id: str,
) -> bool:
    """Check if a CP /recurrent Cancelled webhook should be ignored.

    Returns True if the user has a recent pending payment (< 30 min old),
    indicating an active checkout in progress. The Cancelled status is a
    side-effect of our cancel_subscription() call in create_checkout(), not
    a real payment failure from CP.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    result = await db.execute(
        select(Payment).where(
            Payment.user_id == user_id,
            Payment.status == "pending",
            Payment.payment_provider == "cloudpayments",
            Payment.created_at > cutoff,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def expire_admin_subscriptions(db: AsyncSession) -> int:
    """Expire admin-granted subscriptions past their period end.

    Admin subscriptions (payment_provider='admin') don't have recurring payments,
    so they must be explicitly expired when current_period_end passes.
    """
    now = datetime.utcnow()

    result = await db.execute(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.payment_provider == "admin",
            Subscription.current_period_end.isnot(None),
            Subscription.current_period_end < now,
        )
    )
    expired = 0
    for sub in result.scalars():
        sub.status = "expired"
        sub.updated_at = now
        expired += 1

        user_result = await db.execute(select(User).where(User.id == sub.user_id))
        user = user_result.scalar_one_or_none()
        if user and user.is_seed:
            continue
        if user and user.tier in ("START", "PRO", "UNLIMITED"):
            user.tier = "FREE"
            from app.services.trend_monitor import enforce_author_limits
            await enforce_author_limits(db, user.id, "FREE")
            await _notify_user_expired(user, sub)

    if expired:
        await db.commit()
        logger.info("Expired %d admin-granted subscriptions", expired)
    return expired


async def cleanup_abandoned_payments(db: AsyncSession) -> int:
    """Mark pending payments older than 24h as abandoned.

    Abandoned payments are checkout sessions that the user never completed.
    If a webhook later arrives for an abandoned payment, handle_payment_succeeded
    will override the status to 'succeeded' — so this cleanup is safe.
    """
    from sqlalchemy import update

    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        update(Payment)
        .where(Payment.status == "pending", Payment.created_at < cutoff)
        .values(status="abandoned")
    )
    count = result.rowcount
    if count:
        await db.commit()
        logger.info("Marked %d abandoned pending payments", count)
    return count
