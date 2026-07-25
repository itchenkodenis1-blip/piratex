"""Tests for billing fixes — /recurrent webhook ignore + pending cleanup."""

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.subscription import Payment, Subscription
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_sub(
    db_session,
    user_id: str,
    tier: str = "START",
    status: str = "active",
    provider: str = "cloudpayments",
    **kwargs,
) -> Subscription:
    now = datetime.utcnow()
    sub = Subscription(
        id=str(uuid.uuid4()),
        user_id=user_id,
        tier=tier,
        status=status,
        payment_provider=provider,
        amount_kopecks=200_000,
        currency="RUB",
        billing_interval="monthly",
        current_period_start=kwargs.get("period_start", now),
        current_period_end=kwargs.get("period_end", now + timedelta(days=30)),
        payment_method_id=kwargs.get("payment_method_id"),
        scheduled_tier=kwargs.get("scheduled_tier"),
        scheduled_interval=kwargs.get("scheduled_interval"),
    )
    db_session.add(sub)
    return sub


def _make_payment(
    db_session,
    user_id: str,
    status: str = "pending",
    amount_kopecks: int = 500_000,
    created_at: datetime | None = None,
    **kwargs,
) -> Payment:
    payment = Payment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        provider_payment_id=kwargs.get("provider_payment_id", str(uuid.uuid4())),
        payment_provider=kwargs.get("payment_provider", "cloudpayments"),
        amount_kopecks=amount_kopecks,
        currency="RUB",
        status=status,
        description=kwargs.get("description", "Test payment"),
    )
    if created_at:
        payment.created_at = created_at
    db_session.add(payment)
    return payment


# ---------------------------------------------------------------------------
# Test: /recurrent webhook ignores Cancelled when pending checkout exists
# ---------------------------------------------------------------------------


class TestRecurrentWebhookIgnorePendingCheckout:
    """When we cancel CP subscription during create_checkout, CP sends a
    /recurrent webhook with Cancelled status. We should NOT mark the
    subscription as past_due if there's a recent pending payment (checkout
    in progress)."""

    @pytest.mark.asyncio
    async def test_recurrent_cancelled_with_pending_payment_ignored(self, db_session, make_user):
        """If user has a pending payment (checkout in progress), /recurrent
        Cancelled should be ignored — subscription stays active."""
        user = await make_user(tier="START")
        sub = _make_sub(db_session, user.id)
        # Pending payment = checkout in progress (user upgrading)
        _make_payment(db_session, user.id, status="pending")
        await db_session.flush()

        from app.workers.billing_tasks import _should_ignore_cp_recurrent_cancelled
        result = await _should_ignore_cp_recurrent_cancelled(db_session, user.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_recurrent_cancelled_without_pending_payment_processed(self, db_session, make_user):
        """If no pending payment, /recurrent Cancelled should proceed normally."""
        user = await make_user(tier="START")
        sub = _make_sub(db_session, user.id)
        # No pending payment — this is a real CP cancellation
        await db_session.flush()

        from app.workers.billing_tasks import _should_ignore_cp_recurrent_cancelled
        result = await _should_ignore_cp_recurrent_cancelled(db_session, user.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_recurrent_cancelled_with_other_provider_pending_not_ignored(self, db_session, make_user):
        """If pending payment is from another provider (e.g. YooKassa),
        /recurrent Cancelled should NOT be ignored — it's a real CP failure."""
        user = await make_user(tier="START")
        sub = _make_sub(db_session, user.id)
        # Recent pending from YooKassa — should NOT suppress CP /recurrent
        _make_payment(
            db_session, user.id, status="pending",
            payment_provider="yookassa",
        )
        await db_session.flush()

        from app.workers.billing_tasks import _should_ignore_cp_recurrent_cancelled
        result = await _should_ignore_cp_recurrent_cancelled(db_session, user.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_recurrent_cancelled_with_old_pending_payment_processed(self, db_session, make_user):
        """If pending payment is old (>30 min), /recurrent Cancelled should
        proceed — this is likely a real failure, not a checkout in progress."""
        user = await make_user(tier="START")
        sub = _make_sub(db_session, user.id)
        # Old pending payment — not a current checkout
        _make_payment(
            db_session, user.id, status="pending",
            created_at=datetime.utcnow() - timedelta(hours=2),
        )
        await db_session.flush()

        from app.workers.billing_tasks import _should_ignore_cp_recurrent_cancelled
        result = await _should_ignore_cp_recurrent_cancelled(db_session, user.id)
        assert result is False


# ---------------------------------------------------------------------------
# Test: Cleanup abandoned pending payments
# ---------------------------------------------------------------------------


class TestCleanupAbandonedPayments:
    """Pending payments from abandoned checkouts should be marked 'abandoned'
    after 24 hours."""

    @pytest.mark.asyncio
    async def test_old_pending_payments_marked_abandoned(self, db_session, make_user):
        """Pending payments older than 24h should become abandoned."""
        user = await make_user(tier="START")
        old_payment = _make_payment(
            db_session, user.id, status="pending",
            created_at=datetime.utcnow() - timedelta(hours=25),
        )
        await db_session.flush()

        from app.workers.billing_tasks import cleanup_abandoned_payments
        count = await cleanup_abandoned_payments(db_session)

        assert count == 1
        await db_session.refresh(old_payment)
        assert old_payment.status == "abandoned"

    @pytest.mark.asyncio
    async def test_recent_pending_payments_not_touched(self, db_session, make_user):
        """Pending payments newer than 24h should stay pending."""
        user = await make_user(tier="START")
        recent_payment = _make_payment(
            db_session, user.id, status="pending",
            created_at=datetime.utcnow() - timedelta(hours=1),
        )
        await db_session.flush()

        from app.workers.billing_tasks import cleanup_abandoned_payments
        count = await cleanup_abandoned_payments(db_session)

        assert count == 0
        await db_session.refresh(recent_payment)
        assert recent_payment.status == "pending"

    @pytest.mark.asyncio
    async def test_succeeded_payments_not_touched(self, db_session, make_user):
        """Succeeded payments should never be touched."""
        user = await make_user(tier="START")
        payment = _make_payment(
            db_session, user.id, status="succeeded",
            created_at=datetime.utcnow() - timedelta(hours=48),
        )
        await db_session.flush()

        from app.workers.billing_tasks import cleanup_abandoned_payments
        count = await cleanup_abandoned_payments(db_session)

        assert count == 0
        await db_session.refresh(payment)
        assert payment.status == "succeeded"

    @pytest.mark.asyncio
    async def test_multiple_old_pending_payments_all_abandoned(self, db_session, make_user):
        """Multiple old pending payments all get abandoned."""
        user = await make_user(tier="START")
        p1 = _make_payment(
            db_session, user.id, status="pending",
            created_at=datetime.utcnow() - timedelta(hours=30),
        )
        p2 = _make_payment(
            db_session, user.id, status="pending",
            created_at=datetime.utcnow() - timedelta(hours=48),
        )
        # Recent pending — should stay
        p3 = _make_payment(
            db_session, user.id, status="pending",
            created_at=datetime.utcnow() - timedelta(hours=5),
        )
        await db_session.flush()

        from app.workers.billing_tasks import cleanup_abandoned_payments
        count = await cleanup_abandoned_payments(db_session)

        assert count == 2
        await db_session.refresh(p1)
        await db_session.refresh(p2)
        await db_session.refresh(p3)
        assert p1.status == "abandoned"
        assert p2.status == "abandoned"
        assert p3.status == "pending"
