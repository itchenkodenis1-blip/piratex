"""CloudPayments payment provider.

Uses the CloudPayments JS widget on the frontend (no server-side checkout
redirect). The backend provides widget parameters and handles webhooks.

Recurring payments are managed by CloudPayments: the first payment includes
``CloudPayments.recurrent`` in the ``data`` field so CP creates a subscription
on their side and sends ``/recurrent`` webhooks for subsequent charges.

Docs: https://developers.cloudpayments.ru/
"""

import base64
import hashlib
import hmac
import json
import logging
from urllib.parse import parse_qs

import httpx

from app.config import settings

from .base import CheckoutResult, PaymentProvider, WebhookEvent

logger = logging.getLogger(__name__)

CP_API_BASE = "https://api.cloudpayments.ru"


class CloudPaymentsProvider(PaymentProvider):
    name = "cloudpayments"
    display_name = "CloudPayments"
    icon = "cloudpayments"

    def is_configured(self) -> bool:
        return bool(settings.cloudpayments_public_id and settings.cloudpayments_api_secret)

    # ------------------------------------------------------------------
    # Checkout — CloudPayments uses a client-side widget, so we return
    # widget parameters instead of a redirect URL.  The frontend detects
    # provider == "cloudpayments" and opens cp.CloudPayments().pay()
    # instead of redirecting.
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
        # Generate a unique order ID for idempotency
        import uuid

        order_id = str(uuid.uuid4())

        interval = metadata.get("interval", "monthly")
        tier = metadata.get("tier", "")

        # Full price (before promo) for recurring charges
        original_amount_str = metadata.get("original_amount", "")
        if original_amount_str:
            recurrent_amount = int(original_amount_str) / 100
        else:
            recurrent_amount = amount_minor / 100

        # CloudPayments recurrent config — tells CP to save the card
        # and auto-charge on schedule
        cp_recurrent = {
            "interval": "Month" if interval == "monthly" else "Year",
            "period": 1,
            "amount": recurrent_amount,
            "currency": currency,
        }

        # 54-ФЗ: fiscal receipt for the FIRST payment.
        # Amount must match what CP actually charges (may be discounted).
        # CP will use recurrent.amount for subsequent charges.
        first_payment_amount = amount_minor / 100  # actual charge amount (with promo)
        receipt_label = description[:128] if description else f"ВидеоРентген {tier} ({interval})"
        cp_receipt = {
            "Items": [
                {
                    "label": receipt_label,
                    "price": first_payment_amount,
                    "quantity": 1.0,
                    "amount": first_payment_amount,
                    "vat": 0,       # без НДС (цифровые услуги)
                    "method": 4,    # полная оплата
                    "object": 4,    # услуга
                }
            ],
            "taxationSystem": 1,    # УСН доходы
            "email": user_email or metadata.get("email", ""),
            "amounts": {
                "electronic": first_payment_amount,
            },
        }

        # Build widget params that the frontend will use
        widget_params = {
            "publicId": settings.cloudpayments_public_id,
            "amount": amount_minor / 100,  # widget expects amount in major units
            "currency": currency,
            "description": description,
            "accountId": metadata.get("user_id", ""),
            "email": user_email or metadata.get("email", ""),
            "invoiceId": order_id,
            "data": {
                "user_id": metadata.get("user_id", ""),
                "tier": tier,
                "interval": interval,
                "promo_code": metadata.get("promo_code", ""),
                "original_amount": original_amount_str,
                "CloudPayments": {
                    "recurrent": cp_recurrent,
                    "CustomerReceipt": cp_receipt,
                },
            },
            "skin": "mini",
        }

        # Return special URL scheme so frontend knows to use the widget
        return CheckoutResult(
            payment_url=json.dumps(widget_params),
            provider_payment_id=order_id,
            provider_name=self.name,
        )

    # ------------------------------------------------------------------
    # Webhook — CloudPayments sends POST with form-urlencoded or JSON body.
    # Signature is HMAC-SHA256(body, api_secret) in base64, sent via
    # Content-HMAC header.
    # ------------------------------------------------------------------

    def _verify_signature(self, body: bytes, headers: dict[str, str]) -> None:
        """Verify CloudPayments webhook HMAC-SHA256 signature."""
        # CloudPayments sends signature in Content-HMAC or X-Content-HMAC header
        signature = headers.get("content-hmac") or headers.get("x-content-hmac", "")
        if not signature:
            raise ValueError("Missing CloudPayments webhook signature (Content-HMAC)")

        secret = settings.cloudpayments_api_secret.encode("utf-8")
        computed = base64.b64encode(
            hmac.new(secret, body, hashlib.sha256).digest()
        ).decode("utf-8")

        if not hmac.compare_digest(computed, signature):
            raise ValueError("Invalid CloudPayments webhook signature")

    def _parse_body(self, body: bytes, headers: dict[str, str]) -> dict:
        """Parse webhook body — supports both form-urlencoded and JSON."""
        content_type = headers.get("content-type", "")
        if "application/json" in content_type:
            return json.loads(body)

        # Default: application/x-www-form-urlencoded
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    async def parse_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent | None:
        self._verify_signature(body, headers)

        data = self._parse_body(body, headers)

        # CloudPayments webhook types are determined by the endpoint URL,
        # not by a field in the body.  The billing API routes
        # /webhook/cloudpayments/pay and /webhook/cloudpayments/fail
        # to this provider.  We detect the type from the Status field:
        #   "Completed" = payment succeeded
        #   "Declined"  = payment failed
        #   "Authorized" = two-stage auth (treat as succeeded for single-stage)
        status = data.get("Status", "")
        if status in ("Completed", "Authorized"):
            event_type = "payment.succeeded"
        elif status == "Declined":
            event_type = "payment.cancelled"
        else:
            logger.debug("CloudPayments webhook with unhandled status: %s", status)
            return None

        # Parse metadata from Data field (JSON string)
        meta_raw = data.get("Data", "{}")
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
        except (json.JSONDecodeError, TypeError):
            meta = {}

        amount = float(data.get("Amount", 0))
        amount_minor = round(amount * 100)

        # Strip CloudPayments-specific nested config from metadata before
        # passing it through — our handlers don't need it.
        meta.pop("CloudPayments", None)

        return WebhookEvent(
            event_type=event_type,
            provider_payment_id=str(data.get("TransactionId", data.get("InvoiceId", ""))),
            provider_name=self.name,
            user_id=meta.get("user_id", data.get("AccountId", "")),
            tier=meta.get("tier", ""),
            interval=meta.get("interval", ""),
            amount_minor=amount_minor,
            currency=data.get("Currency", "RUB"),
            payment_method=_detect_payment_method(data),
            promo_code=meta.get("promo_code", ""),
            original_amount_minor=int(meta.get("original_amount", "0")),
            raw_data=data,
        )

    # ------------------------------------------------------------------
    # Recurrent webhook — subscription status changes (not payments).
    # CP sends this when a subscription is created, cancelled (e.g.
    # after 3 failed retries), or status changes.  Different fields
    # from Pay/Fail webhooks: Id, AccountId, Status, Amount, etc.
    # ------------------------------------------------------------------

    def parse_recurrent_status(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> dict | None:
        """Parse CloudPayments Recurrent webhook (subscription status change).

        Returns a dict with subscription status info, or None if not actionable.
        CP subscription statuses: Active, PastDue, Cancelled, Rejected, Expired.
        """
        self._verify_signature(body, headers)
        data = self._parse_body(body, headers)

        status = data.get("Status", "")
        account_id = data.get("AccountId", "")

        if not account_id:
            logger.debug("CP recurrent webhook without AccountId, ignoring")
            return None

        # Only act on terminal/negative statuses
        if status in ("Cancelled", "Rejected", "Expired"):
            return {
                "account_id": account_id,
                "status": status,
                "cp_subscription_id": data.get("Id", ""),
                "amount": float(data.get("Amount", 0)),
                "description": data.get("Description", ""),
                "failed_transactions": int(data.get("FailedTransactionsNumber", 0)),
                "next_transaction_date": data.get("NextTransactionDate"),
            }

        # Active / PastDue — informational, no action needed
        logger.info(
            "CP recurrent status=%s for account=%s (informational)",
            status, account_id,
        )
        return None

    # ------------------------------------------------------------------
    # CloudPayments Subscriptions API — manage recurrent payments
    # ------------------------------------------------------------------

    def _api_auth(self) -> tuple[str, str]:
        """Return (public_id, api_secret) for HTTP Basic Auth."""
        return (settings.cloudpayments_public_id, settings.cloudpayments_api_secret)

    async def cancel_subscription(self, account_id: str) -> bool:
        """Cancel all recurrent subscriptions for the given AccountId.

        CloudPayments ``/subscriptions/find`` returns active subscriptions,
        then we cancel each one via ``/subscriptions/cancel``.
        Returns True if at least one subscription was cancelled.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Find active subscriptions for this account
                resp = await client.post(
                    f"{CP_API_BASE}/subscriptions/find",
                    json={"AccountId": account_id},
                    auth=self._api_auth(),
                )
                resp.raise_for_status()
                body = resp.json()

                if not body.get("Success"):
                    logger.warning("CP subscriptions/find failed: %s", body.get("Message"))
                    return False

                subs = body.get("Model", [])
                if not subs:
                    logger.info("No active CP subscriptions for account=%s", account_id)
                    return True  # nothing to cancel — that's fine

                cancelled = 0
                for cp_sub in subs:
                    sub_id = cp_sub.get("Id")
                    if not sub_id:
                        continue
                    cancel_resp = await client.post(
                        f"{CP_API_BASE}/subscriptions/cancel",
                        json={"Id": sub_id},
                        auth=self._api_auth(),
                    )
                    cancel_resp.raise_for_status()
                    cancel_body = cancel_resp.json()
                    if cancel_body.get("Success"):
                        cancelled += 1
                        logger.info("Cancelled CP subscription Id=%s for account=%s", sub_id, account_id)
                    else:
                        logger.warning("Failed to cancel CP subscription Id=%s: %s", sub_id, cancel_body.get("Message"))

                return cancelled > 0

        except Exception as e:
            logger.error("CloudPayments cancel_subscription error for account=%s: %s", account_id, e)
            return False

    async def update_subscription_amount(self, account_id: str, amount_rubles: float) -> bool:
        """Update the recurrent charge amount for all active CP subscriptions."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{CP_API_BASE}/subscriptions/find",
                    json={"AccountId": account_id},
                    auth=self._api_auth(),
                )
                resp.raise_for_status()
                body = resp.json()

                if not body.get("Success"):
                    return False

                updated = 0
                for cp_sub in body.get("Model", []):
                    sub_id = cp_sub.get("Id")
                    if not sub_id:
                        continue
                    update_resp = await client.post(
                        f"{CP_API_BASE}/subscriptions/update",
                        json={"Id": sub_id, "Amount": amount_rubles},
                        auth=self._api_auth(),
                    )
                    update_resp.raise_for_status()
                    update_body = update_resp.json()
                    if update_body.get("Success"):
                        updated += 1
                        logger.info("Updated CP subscription Id=%s amount=%.2f for account=%s", sub_id, amount_rubles, account_id)
                    else:
                        logger.warning("Failed to update CP subscription Id=%s: %s", sub_id, update_body.get("Message"))

                return updated > 0

        except Exception as e:
            logger.error("CloudPayments update_subscription_amount error: %s", e)
            return False


def _detect_payment_method(data: dict) -> str:
    """Detect payment method from CloudPayments webhook data."""
    card_type = data.get("CardType", "").lower()
    if card_type:
        return card_type  # "visa", "mastercard", "mir", etc.
    if data.get("Token"):
        return "token"
    return "bank_card"
