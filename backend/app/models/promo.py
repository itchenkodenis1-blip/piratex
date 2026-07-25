"""Promo code model for early bird discounts and campaigns."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String

from app.database import Base


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(30), unique=True, nullable=False, index=True)

    # Discount: percentage (0-100) or fixed amount in kopecks
    discount_percent = Column(Integer, nullable=True)  # e.g. 30 = 30%
    discount_kopecks = Column(BigInteger, nullable=True)  # fixed amount off

    # Limits
    max_uses = Column(Integer, nullable=True)  # None = unlimited
    used_count = Column(Integer, nullable=False, default=0)

    # Duration: how many months the discount applies (None = first payment only)
    duration_months = Column(Integer, nullable=True)  # e.g. 3 = first 3 months

    # Scope: restrict to specific tiers/intervals
    valid_tiers = Column(String, nullable=True)  # comma-separated: "START,PRO,UNLIMITED"
    valid_intervals = Column(String, nullable=True)  # "monthly,yearly"

    # Validity period
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class PromoCodeUsage(Base):
    __tablename__ = "promo_code_usages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    promo_code_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    applied_at = Column(DateTime, default=datetime.utcnow)
