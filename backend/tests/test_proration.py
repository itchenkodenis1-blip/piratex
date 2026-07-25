"""Tests for subscription proration — calculate_proration and change-tier endpoints."""

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.config import TIER_PRICING
from app.models.subscription import Subscription
from app.services.billing import calculate_proration

from tests.conftest import auth_headers


# ---------------------------------------------------------------------------
# calculate_proration — pure function tests
# ---------------------------------------------------------------------------


class TestCalculateProration:
    """Test the proration calculation logic."""

    def _make_sub(
        self,
        tier: str = "START",
        interval: str = "monthly",
        amount_kopecks: int = 200_000,
        paid_amount_kopecks: int | None = None,
        currency: str = "RUB",
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> Subscription:
        now = datetime.utcnow()
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id="test-user",
            tier=tier,
            status="active",
            payment_provider="cloudpayments",
            amount_kopecks=amount_kopecks,
            paid_amount_kopecks=paid_amount_kopecks,
            currency=currency,
            billing_interval=interval,
            current_period_start=period_start or now,
            current_period_end=period_end or (now + timedelta(days=30)),
        )
        return sub

    def test_upgrade_start_to_pro_mid_cycle(self):
        """START→PRO on day 15 of 30: should charge (15/30)*(5000-2000) = 1500 RUB."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="START",
            amount_kopecks=200_000,
            period_start=now - timedelta(days=15),
            period_end=now + timedelta(days=15),
        )
        result = calculate_proration(sub, "PRO", "monthly", now=now)

        assert result["is_upgrade"] is True
        # 15 days remaining out of 30
        assert result["days_remaining"] == pytest.approx(15, abs=1)
        # credit = (15/30) * 200_000 = 100_000
        assert result["credit"] == pytest.approx(100_000, abs=1000)
        # charge = (15/30) * 500_000 = 250_000
        assert result["charge"] == pytest.approx(250_000, abs=1000)
        # proration = 250_000 - 100_000 = 150_000 (1500 RUB)
        assert result["proration_amount"] == pytest.approx(150_000, abs=1000)
        assert result["new_price_full"] == 500_000
        assert result["currency"] == "RUB"

    def test_upgrade_start_to_unlimited_first_day(self):
        """Upgrade on first day: should charge almost full difference."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="START",
            amount_kopecks=200_000,
            period_start=now,
            period_end=now + timedelta(days=30),
        )
        result = calculate_proration(sub, "UNLIMITED", "monthly", now=now)

        assert result["is_upgrade"] is True
        # Almost 30 days remaining
        assert result["days_remaining"] == pytest.approx(30, abs=1)
        # proration ≈ 1_000_000 - 200_000 = 800_000
        assert result["proration_amount"] == pytest.approx(800_000, abs=5000)

    def test_upgrade_last_day_nearly_free(self):
        """Upgrade on last day: proration ≈ 0."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="START",
            amount_kopecks=200_000,
            period_start=now - timedelta(days=29),
            period_end=now + timedelta(hours=12),  # half a day left
        )
        result = calculate_proration(sub, "PRO", "monthly", now=now)

        assert result["is_upgrade"] is True
        assert result["proration_amount"] < 20_000  # less than 200 RUB

    def test_downgrade_pro_to_start(self):
        """PRO→START is a downgrade."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="PRO",
            amount_kopecks=500_000,
            period_start=now - timedelta(days=10),
            period_end=now + timedelta(days=20),
        )
        result = calculate_proration(sub, "START", "monthly", now=now)

        assert result["is_upgrade"] is False
        assert result["proration_amount"] == 0  # downgrade = no charge

    def test_promo_discount_uses_paid_amount(self):
        """When user paid with promo, credit should use paid_amount_kopecks, not full price."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="START",
            amount_kopecks=200_000,  # full price
            paid_amount_kopecks=150_000,  # paid with 25% discount
            period_start=now - timedelta(days=15),
            period_end=now + timedelta(days=15),
        )
        result = calculate_proration(sub, "PRO", "monthly", now=now)

        # credit from paid amount: (15/30) * 150_000 = 75_000
        assert result["credit"] == pytest.approx(75_000, abs=1000)
        # charge: (15/30) * 500_000 = 250_000
        # proration = 250_000 - 75_000 = 175_000
        assert result["proration_amount"] == pytest.approx(175_000, abs=1000)

    def test_yearly_subscription(self):
        """Annual subscription proration works correctly."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="START",
            interval="yearly",
            amount_kopecks=1_800_000,
            period_start=now - timedelta(days=100),
            period_end=now + timedelta(days=265),
        )
        result = calculate_proration(sub, "PRO", "yearly", now=now)

        assert result["is_upgrade"] is True
        # 265 days remaining out of 365
        ratio = 265 / 365
        expected_credit = round(ratio * 1_800_000)
        expected_charge = round(ratio * 4_500_000)
        assert result["credit"] == pytest.approx(expected_credit, abs=5000)
        assert result["charge"] == pytest.approx(expected_charge, abs=5000)
        assert result["new_price_full"] == 4_500_000

    def test_monthly_to_yearly_same_tier(self):
        """Monthly→yearly same tier is upgrade."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="PRO",
            interval="monthly",
            amount_kopecks=500_000,
            period_start=now - timedelta(days=10),
            period_end=now + timedelta(days=20),
        )
        result = calculate_proration(sub, "PRO", "yearly", now=now)

        assert result["is_upgrade"] is True
        # credit = (20/30) * 500_000
        # charge = full yearly price = 4_500_000 (full year from now, not prorated)
        assert result["new_price_full"] == 4_500_000

    def test_yearly_to_monthly_same_tier_is_downgrade(self):
        """Yearly→monthly same tier is downgrade."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="PRO",
            interval="yearly",
            amount_kopecks=4_500_000,
            period_start=now - timedelta(days=100),
            period_end=now + timedelta(days=265),
        )
        result = calculate_proration(sub, "PRO", "monthly", now=now)

        assert result["is_upgrade"] is False
        assert result["proration_amount"] == 0

    def test_eur_currency(self):
        """EUR pricing works correctly."""
        now = datetime.utcnow()
        sub = self._make_sub(
            tier="START",
            amount_kopecks=2_000,  # €20 in cents
            currency="EUR",
            period_start=now - timedelta(days=15),
            period_end=now + timedelta(days=15),
        )
        result = calculate_proration(sub, "PRO", "monthly", now=now)

        assert result["currency"] == "EUR"
        assert result["new_price_full"] == 5_000  # €50 in cents

    def test_next_billing_date_preserved(self):
        """Billing anchor (next_billing_date) should be current period_end."""
        now = datetime.utcnow()
        period_end = now + timedelta(days=20)
        sub = self._make_sub(
            tier="START",
            amount_kopecks=200_000,
            period_start=now - timedelta(days=10),
            period_end=period_end,
        )
        result = calculate_proration(sub, "PRO", "monthly", now=now)

        assert result["next_billing_date"] == period_end


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestProrationPreviewEndpoint:
    """Test GET /api/proration-preview."""

    @pytest_asyncio.fixture
    async def user_with_sub(self, db_session, make_user):
        """Create user with active START subscription."""
        user = await make_user(tier="START")
        now = datetime.utcnow()
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id=user.id,
            tier="START",
            status="active",
            payment_provider="cloudpayments",
            amount_kopecks=200_000,
            currency="RUB",
            billing_interval="monthly",
            current_period_start=now - timedelta(days=15),
            current_period_end=now + timedelta(days=15),
        )
        db_session.add(sub)
        await db_session.flush()
        return user, sub

    @pytest.mark.asyncio
    async def test_preview_upgrade(self, client, user_with_sub):
        user, sub = user_with_sub
        resp = await client.get(
            "/api/billing/proration-preview",
            params={"new_tier": "PRO", "new_interval": "monthly"},
            headers=auth_headers(user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_upgrade"] is True
        assert data["proration_amount"] > 0
        assert data["new_price_full"] == 500_000
        assert data["currency"] == "RUB"

    @pytest.mark.asyncio
    async def test_preview_downgrade(self, client, user_with_sub):
        """Downgrade preview should show is_upgrade=False, proration=0."""
        user, sub = user_with_sub
        # Change sub to PRO first
        sub.tier = "PRO"
        sub.amount_kopecks = 500_000

        resp = await client.get(
            "/api/billing/proration-preview",
            params={"new_tier": "START", "new_interval": "monthly"},
            headers=auth_headers(user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_upgrade"] is False
        assert data["proration_amount"] == 0

    @pytest.mark.asyncio
    async def test_preview_no_subscription(self, client, make_user):
        """Free user with no subscription gets full price preview."""
        user = await make_user(tier="FREE")
        resp = await client.get(
            "/api/billing/proration-preview",
            params={"new_tier": "PRO", "new_interval": "monthly"},
            headers=auth_headers(user),
        )
        assert resp.status_code == 200
        data = resp.json()
        # FREE user: no proration, just full price
        assert data["proration_amount"] == 500_000
        assert data["is_upgrade"] is True

    @pytest.mark.asyncio
    async def test_preview_same_tier_rejected(self, client, user_with_sub):
        user, sub = user_with_sub
        resp = await client.get(
            "/api/billing/proration-preview",
            params={"new_tier": "START", "new_interval": "monthly"},
            headers=auth_headers(user),
        )
        assert resp.status_code == 400


class TestChangeTierEndpoint:
    """Test POST /api/change-tier."""

    @pytest_asyncio.fixture
    async def user_with_sub(self, db_session, make_user):
        user = await make_user(tier="START")
        now = datetime.utcnow()
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id=user.id,
            tier="START",
            status="active",
            payment_provider="cloudpayments",
            amount_kopecks=200_000,
            currency="RUB",
            billing_interval="monthly",
            current_period_start=now - timedelta(days=15),
            current_period_end=now + timedelta(days=15),
        )
        db_session.add(sub)
        await db_session.flush()
        return user, sub

    @pytest.mark.asyncio
    async def test_downgrade_schedules(self, client, db_session, user_with_sub):
        """Downgrade should schedule tier change, not apply immediately."""
        user, sub = user_with_sub
        # Set tier to PRO for downgrade test
        sub.tier = "PRO"
        sub.amount_kopecks = 500_000
        user.tier = "PRO"
        await db_session.flush()

        resp = await client.post(
            "/api/billing/change-tier",
            json={"new_tier": "START", "new_interval": "monthly", "auto_renewal_consent": True},
            headers=auth_headers(user),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scheduled"] is True
        assert data["effective_date"] is not None

        # Verify subscription still has PRO tier
        await db_session.refresh(sub)
        assert sub.tier == "PRO"
        assert sub.scheduled_tier == "START"
        assert sub.scheduled_interval == "monthly"

    @pytest.mark.asyncio
    async def test_cancel_scheduled_downgrade(self, client, db_session, user_with_sub):
        """DELETE /api/scheduled-downgrade clears scheduled_tier."""
        user, sub = user_with_sub
        sub.tier = "PRO"
        sub.scheduled_tier = "START"
        sub.scheduled_interval = "monthly"
        user.tier = "PRO"
        await db_session.flush()

        resp = await client.delete(
            "/api/billing/scheduled-downgrade",
            headers=auth_headers(user),
        )
        assert resp.status_code == 200

        await db_session.refresh(sub)
        assert sub.scheduled_tier is None
        assert sub.scheduled_interval is None

    @pytest.mark.asyncio
    async def test_change_tier_requires_consent(self, client, user_with_sub):
        """Change tier without consent should fail (376-ФЗ)."""
        user, sub = user_with_sub
        resp = await client.post(
            "/api/billing/change-tier",
            json={"new_tier": "PRO", "new_interval": "monthly"},
            headers=auth_headers(user),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_change_tier_cancelled_rejected(self, client, db_session, user_with_sub):
        """Cannot change tier on cancelled subscription."""
        user, sub = user_with_sub
        sub.status = "cancelled"
        await db_session.flush()

        resp = await client.post(
            "/api/billing/change-tier",
            json={"new_tier": "PRO", "new_interval": "monthly", "auto_renewal_consent": True},
            headers=auth_headers(user),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_change_tier_same_tier_rejected(self, client, user_with_sub):
        """Cannot change to same tier+interval."""
        user, sub = user_with_sub
        resp = await client.post(
            "/api/billing/change-tier",
            json={"new_tier": "START", "new_interval": "monthly", "auto_renewal_consent": True},
            headers=auth_headers(user),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_free_user_rejected(self, client, make_user):
        """FREE user should use normal checkout, not change-tier."""
        user = await make_user(tier="FREE")
        resp = await client.post(
            "/api/billing/change-tier",
            json={"new_tier": "PRO", "new_interval": "monthly", "auto_renewal_consent": True},
            headers=auth_headers(user),
        )
        assert resp.status_code == 400
        assert "checkout" in resp.json()["detail"].lower()


class TestSubscriptionEndpointWithScheduled:
    """Test that GET /subscription returns scheduled_tier."""

    @pytest.mark.asyncio
    async def test_subscription_shows_scheduled(self, client, db_session, make_user):
        user = await make_user(tier="PRO")
        now = datetime.utcnow()
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id=user.id,
            tier="PRO",
            status="active",
            payment_provider="cloudpayments",
            amount_kopecks=500_000,
            currency="RUB",
            billing_interval="monthly",
            current_period_start=now - timedelta(days=10),
            current_period_end=now + timedelta(days=20),
            scheduled_tier="START",
            scheduled_interval="monthly",
        )
        db_session.add(sub)
        await db_session.flush()

        resp = await client.get(
            "/api/billing/subscription",
            headers=auth_headers(user),
        )
        assert resp.status_code == 200
        data = resp.json()["subscription"]
        assert data["scheduled_tier"] == "START"
        assert data["scheduled_interval"] == "monthly"
