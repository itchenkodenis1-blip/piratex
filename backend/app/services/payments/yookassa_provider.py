"""YooKassa payment provider adapter."""

import asyncio
import hashlib
import hmac
import json
import logging
import uuid

from yookassa import Configuration, Payment as YKPayment

from app.config import settings

from .base import CheckoutResult, PaymentProvider, WebhookEvent

logger = logging.getLogger(__name__)


class YooKassaProvider(PaymentProvider):
    name = "yookassa"
    display_name = "ЮКасса"
    icon = "yookassa"

    def _ensure_configured(self) -> None:
        if not Configuration.account_id:
            Configuration.account_id = settings.yookassa_shop_id
            Configuration.secret_key = settings.yookassa_secret_key

    def is_configured(self) -> bool:
        return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)

    # ------------------------------------------------------------------
    # Checkout
    # ------------------------------------------------------------------

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
        self._ensure_configured()

        amount_rub = f"{amount_minor / 100:.2f}"
        idempotence_key = str(uuid.uuid4())

        params: dict = {
            "amount": {"value": amount_rub, "currency": currency},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description,
            "metadata": metadata,
            "save_payment_method": True,
        }

        # Receipt for 54-FZ compliance
        if user_email:
            params["receipt"] = {
                "customer": {"email": user_email},
                "items": [
                    {
                        "description": description[:128],
                        "quantity": "1.00",
                        "amount": {"value": amount_rub, "currency": currency},
                        "vat_code": 1,
                    }
                ],
            }

        def _create():
            return YKPayment.create(params, idempotence_key)

        result = await asyncio.to_thread(_create)
        raw = result.json()
        data = json.loads(raw) if isinstance(raw, str) else raw

        confirmation_url = data.get("confirmation", {}).get("confirmation_url", "")
        return CheckoutResult(
            payment_url=confirmation_url,
            provider_payment_id=data["id"],
            provider_name=self.name,
        )

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    async def parse_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent | None:
        # Verify signature
        secret = settings.yookassa_webhook_secret
        if not secret:
            raise ValueError("YooKassa webhook secret not configured")

        signature = headers.get("x-webhook-signature", "")
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid YooKassa webhook signature")

        payload = json.loads(body)
        event_name = payload.get("event")
        payment_data = payload.get("object", {})

        # Map YooKassa events to our normalised types
        event_type_map = {
            "payment.succeeded": "payment.succeeded",
            "payment.canceled": "payment.cancelled",
        }
        event_type = event_type_map.get(event_name)
        if not event_type:
            return None  # event we don't handle

        metadata = payment_data.get("metadata", {})
        amount = payment_data.get("amount", {})
        amount_minor = round(float(amount.get("value", "0")) * 100)

        return WebhookEvent(
            event_type=event_type,
            provider_payment_id=payment_data["id"],
            provider_name=self.name,
            user_id=metadata.get("user_id", ""),
            tier=metadata.get("tier", ""),
            interval=metadata.get("interval", "monthly"),
            amount_minor=amount_minor,
            currency=amount.get("currency", "RUB"),
            payment_method=payment_data.get("payment_method", {}).get("type", "unknown"),
            promo_code=metadata.get("promo_code", ""),
            original_amount_minor=int(metadata.get("original_amount", "0")),
            raw_data=payload,
        )
