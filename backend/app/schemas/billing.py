from datetime import datetime

from pydantic import BaseModel


# --- Pricing ---

class FeatureItem(BaseModel):
    text: str
    style: str = "normal"  # "normal" | "highlight" | "disabled"


class PricingTier(BaseModel):
    tier: str
    name: str
    price_monthly: int  # rubles
    price_yearly: int   # rubles (total per year)
    limit_monthly: int | None  # None = unlimited display
    features: list[FeatureItem]
    popular: bool = False


class PricingResponse(BaseModel):
    tiers: list[PricingTier]
    free_limit: int | None = None  # FREE tier monthly limit (for teaser/UI)


# --- Checkout ---

class CheckoutRequest(BaseModel):
    tier: str  # START, PRO, UNLIMITED
    interval: str = "monthly"  # monthly | yearly
    promo_code: str | None = None  # optional promo/discount code
    provider: str | None = None  # auto-selected by user language if omitted
    auto_renewal_consent: bool = False  # 376-ФЗ: explicit consent required
    email: str | None = None  # collected at checkout if user has no email


class CheckoutResponse(BaseModel):
    payment_url: str
    payment_id: str
    provider: str | None = None  # "yookassa" | "stripe" | "cloudpayments"


# --- Subscription ---

class SubscriptionResponse(BaseModel):
    id: str
    tier: str
    status: str
    billing_interval: str
    amount_kopecks: int
    currency: str
    payment_provider: str | None = None
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    scheduled_tier: str | None = None
    scheduled_interval: str | None = None

    model_config = {"from_attributes": True}


# --- Proration ---

class ChangeTierRequest(BaseModel):
    new_tier: str  # START, PRO, UNLIMITED
    new_interval: str = "monthly"  # monthly | yearly
    auto_renewal_consent: bool = False  # 376-ФЗ


class ProrationPreview(BaseModel):
    proration_amount: int  # amount to charge now (kopecks/cents)
    credit: int  # credit for unused time on current plan
    charge: int  # cost of remaining time on new plan
    new_price_full: int  # full price of new plan (for next renewal)
    currency: str
    days_remaining: int
    next_billing_date: datetime | None
    is_upgrade: bool


# --- Payments ---

class PaymentItem(BaseModel):
    id: str
    amount_kopecks: int
    currency: str
    status: str
    payment_provider: str | None = None
    payment_method: str | None
    description: str | None
    paid_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Portal ---

class PortalResponse(BaseModel):
    url: str


# --- Referral ---

class ReferralCodeResponse(BaseModel):
    referral_code: str
    referral_url: str


class ReferralStatsResponse(BaseModel):
    referral_code: str
    referral_url: str
    total_referred: int
    bonus_credits_earned: int
    bonus_credits_remaining: int
