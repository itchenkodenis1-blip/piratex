import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    referrer_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    referred_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True,  # user can only be referred once
    )
    bonus_applied = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)


class BonusCredit(Base):
    __tablename__ = "bonus_credits"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    amount = Column(Integer, nullable=False)  # bonus reel count
    used = Column(Integer, nullable=False, default=0)
    reason = Column(String(50), nullable=False)  # referral, promo, manual
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Partner(Base):
    """Partner/affiliate — earns commission on referred users' payments."""
    __tablename__ = "partners"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    partner_code = Column(String(30), unique=True, nullable=False, index=True)
    commission_percent = Column(Integer, nullable=False, default=25)  # 25% default
    status = Column(String(20), nullable=False, default="active")  # active | suspended
    total_referred = Column(Integer, nullable=False, default=0)
    total_earned_kopecks = Column(BigInteger, nullable=False, default=0)
    total_paid_out_kopecks = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class PartnerCommission(Base):
    """Individual commission earned on a payment."""
    __tablename__ = "partner_commissions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    partner_id = Column(String, nullable=False, index=True)
    payment_id = Column(String, nullable=False)
    referred_user_id = Column(String, nullable=False)
    payment_amount_kopecks = Column(BigInteger, nullable=False)
    commission_kopecks = Column(BigInteger, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending | paid
    created_at = Column(DateTime, default=datetime.utcnow)
