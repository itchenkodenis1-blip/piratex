"""Multi-provider payment system.

Providers register themselves at import time.
Use ``get_provider(name)`` to obtain a configured provider
and ``get_enabled_providers()`` for the list exposed to the frontend.
"""

import logging

from .base import CheckoutResult, PaymentProvider, WebhookEvent  # noqa: F401
from .registry import get_enabled_providers, get_provider, register_provider  # noqa: F401

logger = logging.getLogger(__name__)

# Auto-register all known providers (gracefully skip if SDK not installed)
try:
    from .yookassa_provider import YooKassaProvider
    register_provider(YooKassaProvider())
except ImportError:
    logger.warning("yookassa package not installed — YooKassa provider disabled")

try:
    from .stripe_provider import StripeProvider
    register_provider(StripeProvider())
except ImportError:
    logger.warning("stripe package not installed — Stripe provider disabled")

try:
    from .cloudpayments_provider import CloudPaymentsProvider
    register_provider(CloudPaymentsProvider())
except Exception:
    logger.warning("CloudPayments provider could not be loaded")
