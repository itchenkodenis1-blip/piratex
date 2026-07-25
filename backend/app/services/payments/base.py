"""Base classes for the multi-provider payment system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CheckoutResult:
    """Unified result of creating a payment across any provider."""

    payment_url: str
    provider_payment_id: str
    provider_name: str
    stripe_customer_id: str = ""  # Only set by Stripe provider


@dataclass
class WebhookEvent:
    """Normalised webhook event — same shape regardless of provider."""

    event_type: str  # "payment.succeeded" | "payment.cancelled" | "subscription.updated" | "subscription.deleted"
    provider_payment_id: str
    provider_name: str
    user_id: str
    tier: str
    interval: str
    amount_minor: int  # kopecks for RUB, cents for USD, etc.
    currency: str
    payment_method: str  # "bank_card" | "sbp" | "card" | ...
    promo_code: str  # "" if none
    original_amount_minor: int  # amount before promo discount
    raw_data: dict = field(default_factory=dict)
    # Stripe subscription fields (optional — only set for Stripe events)
    stripe_subscription_id: str = ""
    stripe_customer_id: str = ""
    stripe_price_id: str = ""
    current_period_end: int = 0  # Unix timestamp from Stripe


class PaymentProvider(ABC):
    """Interface every payment provider must implement."""

    name: str  # "stripe", "yookassa"
    display_name: str  # "Stripe", "ЮКасса"
    icon: str  # icon key for the frontend

    @abstractmethod
    async def create_checkout_session(
        self,
        *,
        amount_minor: int,
        currency: str,
        description: str,
        return_url: str,
        cancel_url: str,
        metadata: dict,
        user_email: str | None = None,
        **kwargs,
    ) -> CheckoutResult:
        """Create a hosted checkout page and return its URL + provider ID."""
        ...

    @abstractmethod
    async def parse_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent | None:
        """Verify signature, parse webhook, return normalised event.

        Returns ``None`` for events we don't care about.
        """
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when all required API keys are present."""
        ...
