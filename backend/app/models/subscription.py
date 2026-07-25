import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text

from app.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tier = Column(String(20), nullable=False)  # START, PRO, UNLIMITED
    status = Column(String(20), nullable=False, default="active")
    # status: active | past_due | cancelled | expired

    payment_provider = Column(String(50), nullable=False, default="yookassa")
    provider_subscription_id = Column(String(255), nullable=True)
    payment_method_id = Column(String(255), nullable=True)  # saved card token

    amount_kopecks = Column(BigInteger, nullable=False)  # price in kopecks (full price)
    paid_amount_kopecks = Column(BigInteger, nullable=True)  # actual amount paid (after promo)
    currency = Column(String(3), nullable=False, default="RUB")
    billing_interval = Column(String(20), nullable=False, default="monthly")
    # billing_interval: monthly | yearly

    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    # Scheduled downgrade (applied at renewal)
    scheduled_tier = Column(String(20), nullable=True)
    scheduled_interval = Column(String(10), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_subscriptions_status", "status"),
        Index("ix_subscriptions_period_end", "current_period_end"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(
        String, ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    provider_payment_id = Column(String(255), nullable=True, unique=True)
    payment_provider = Column(String(50), nullable=False, default="yookassa")
    amount_kopecks = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False, default="RUB")
    status = Column(String(20), nullable=False, default="pending")
    # status: pending | succeeded | cancelled | refunded

    payment_method = Column(String(50), nullable=True)  # bank_card, sbp, yoomoney
    description = Column(String(500), nullable=True)
    receipt_url = Column(String(500), nullable=True)
    payment_url = Column(Text, nullable=True)  # checkout URL for dedup

    # Security: server-side checkout intent (protects against client-side amount/tier spoofing)
    checkout_tier = Column(String(20), nullable=True)
    checkout_interval = Column(String(20), nullable=True)
    expected_amount_kopecks = Column(BigInteger, nullable=True)

    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ConsentLog(Base):
    """Audit log for user consents and revocations (376-ФЗ, 69-ФЗ compliance)."""

    __tablename__ = "consent_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    consent_type = Column(String(50), nullable=False)
    # consent_type: auto_renewal_granted | auto_renewal_revoked | card_removed
    action = Column(String(20), nullable=False)  # granted | revoked
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    metadata_json = Column(String(2000), nullable=True)  # tier, amount, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
