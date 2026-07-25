"""Provider registry — lazily stores enabled payment providers."""

from __future__ import annotations

import logging

from .base import PaymentProvider

logger = logging.getLogger(__name__)

_providers: dict[str, PaymentProvider] = {}


def register_provider(provider: PaymentProvider) -> None:
    _providers[provider.name] = provider
    if provider.is_configured():
        logger.info("Payment provider registered: %s (enabled)", provider.name)
    else:
        logger.info("Payment provider registered: %s (disabled — missing keys)", provider.name)


def get_provider(name: str) -> PaymentProvider:
    if name not in _providers:
        raise ValueError(f"Unknown payment provider: {name}")
    p = _providers[name]
    if not p.is_configured():
        raise ValueError(f"Payment provider '{name}' is not configured (missing API keys)")
    return p


def get_enabled_providers() -> list[dict]:
    """Return list of configured providers for the frontend."""
    return [
        {"name": p.name, "display_name": p.display_name, "icon": p.icon}
        for p in _providers.values()
        if p.is_configured()
    ]
