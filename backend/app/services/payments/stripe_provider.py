"""Stripe payment provider — subscription mode with recurring billing."""

import asyncio
import json
import logging

import stripe

from app.config import STRIPE_PRICE_IDS, STRIPE_PRICE_TO_TIER, settings

from .base import CheckoutResult, PaymentProvider, WebhookEvent

logger = logging.getLogger(__name__)


class StripeProvider(PaymentProvider):
    name = "stripe"
    display_name = "Stripe"
    icon = "stripe"

    def is_configured(self) -> bool:
        return bool(settings.stripe_secret_key and settings.stripe_webhook_secret)

    def _get_client(self) -> stripe.StripeClient:
        return stripe.StripeClient(settings.stripe_secret_key)

    # ------------------------------------------------------------------
    # Customer management
    # ------------------------------------------------------------------

    async def get_or_create_customer(
        self,
        email: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        """Find existing Stripe Customer or create a new one. Returns customer ID."""
        client = self._get_client()

        # If we already have a stored customer ID, verify it exists
        if stripe_customer_id:
            try:
                customer = await asyncio.to_thread(
                    client.customers.retrieve, stripe_customer_id,
                )
                if not customer.get("deleted"):
                    return customer["id"]
                logger.info("Stripe customer %s is deleted, will create new", stripe_customer_id)
            except stripe.InvalidRequestError:
                logger.warning("Stored Stripe customer %s not found, creating new", stripe_customer_id)
            except Exception:
                # Network/rate limit errors — re-raise, don't silently create duplicate
                raise

        # Search by email
        if email:
            result = await asyncio.to_thread(
                client.customers.search,
                params={"query": f'email:"{email}"', "limit": 1},
            )
            for cust in result.get("data", []):
                if not cust.get("deleted"):
                    return cust["id"]

        # Create new customer
        customer = await asyncio.to_thread(
            client.customers.create,
            params={"email": email} if email else {},
        )
        return customer["id"]

    # ------------------------------------------------------------------
    # Checkout (subscription mode)
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
        # Subscription-specific params
        stripe_customer_id: str | None = None,
        stripe_price_id: str | None = None,
        stripe_coupon_id: str | None = None,
    ) -> CheckoutResult:
        client = self._get_client()

        # Resolve price ID from metadata if not passed directly
        if not stripe_price_id:
            tier = metadata.get("tier", "")
            interval = metadata.get("interval", "monthly")
            stripe_price_id = STRIPE_PRICE_IDS.get(tier, {}).get(interval)

        if not stripe_price_id:
            raise ValueError(f"No Stripe Price ID for tier={metadata.get('tier')} interval={metadata.get('interval')}")

        # Get or create Stripe customer
        customer_id = await self.get_or_create_customer(
            email=user_email or metadata.get("email", ""),
            stripe_customer_id=stripe_customer_id,
        )

        params: dict = {
            "mode": "subscription",
            "customer": customer_id,
            "line_items": [
                {
                    "price": stripe_price_id,
                    "quantity": 1,
                },
            ],
            "subscription_data": {
                "metadata": metadata,
            },
            "success_url": return_url + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": cancel_url,
        }

        # Apply coupon discount if provided
        if stripe_coupon_id:
            params["discounts"] = [{"coupon": stripe_coupon_id}]

        session = await asyncio.to_thread(
            client.checkout.sessions.create, params=params,
        )

        return CheckoutResult(
            payment_url=session.url or "",
            provider_payment_id=session.id,
            provider_name=self.name,
            stripe_customer_id=customer_id,
        )

    # ------------------------------------------------------------------
    # Customer Portal
    # ------------------------------------------------------------------

    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> str:
        """Create a Stripe Customer Portal session. Returns the portal URL."""
        client = self._get_client()

        session = await asyncio.to_thread(
            client.billing_portal.sessions.create,
            params={
                "customer": customer_id,
                "return_url": return_url,
            },
        )
        return session.url or ""

    # ------------------------------------------------------------------
    # Subscription cancellation
    # ------------------------------------------------------------------

    async def cancel_subscription(
        self,
        stripe_subscription_id: str,
    ) -> None:
        """Cancel a Stripe subscription at the end of the current billing period."""
        client = self._get_client()

        await asyncio.to_thread(
            client.subscriptions.update,
            stripe_subscription_id,
            params={"cancel_at_period_end": True},
        )

    # ------------------------------------------------------------------
    # Promo / Coupon
    # ------------------------------------------------------------------

    async def create_coupon(
        self,
        *,
        percent_off: int,
        duration: str = "once",
        duration_in_months: int | None = None,
    ) -> str:
        """Create a Stripe Coupon and return its ID.

        duration: "once" | "repeating" | "forever"
        """
        client = self._get_client()

        params: dict = {
            "percent_off": percent_off,
            "duration": duration,
        }
        if duration == "repeating" and duration_in_months:
            params["duration_in_months"] = duration_in_months

        coupon = await asyncio.to_thread(
            client.coupons.create, params=params,
        )
        return coupon["id"]

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------

    async def parse_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
    ) -> WebhookEvent | None:
        sig = headers.get("stripe-signature", "")
        if not sig:
            raise ValueError("Missing Stripe webhook signature")

        try:
            event = stripe.Webhook.construct_event(
                body, sig, settings.stripe_webhook_secret,
            )
        except stripe.SignatureVerificationError:
            raise ValueError("Invalid Stripe webhook signature")

        raw_data = json.loads(body) if isinstance(body, bytes) else body
        event_type = event["type"]
        data = event["data"]["object"]

        # --- checkout.session.completed ---
        # In subscription mode, invoice.paid handles activation.
        # We only log checkout.session.completed for diagnostics.
        if event_type == "checkout.session.completed":
            logger.info(
                "Stripe checkout.session.completed (subscription mode): session=%s subscription=%s",
                data.get("id"), data.get("subscription"),
            )
            return None  # invoice.paid will handle subscription activation

        # --- invoice.paid (recurring payments + first payment) ---
        if event_type == "invoice.paid":
            sub_id = data.get("subscription", "")
            customer_id = data.get("customer", "")
            metadata = data.get("subscription_details", {}).get("metadata", {})

            # Stripe often doesn't include subscription metadata in invoice.paid payload.
            # Fetch directly from the Subscription object if user_id is missing.
            if sub_id and not metadata.get("user_id"):
                try:
                    client = self._get_client()
                    sub_obj = await asyncio.to_thread(
                        client.subscriptions.retrieve, sub_id
                    )
                    sub_metadata = dict(sub_obj.metadata or {})
                    if sub_metadata.get("user_id"):
                        metadata = sub_metadata
                        logger.info(
                            "Fetched metadata from Stripe subscription %s: user_id=%s tier=%s",
                            sub_id, metadata.get("user_id"), metadata.get("tier"),
                        )
                except Exception as e:
                    logger.warning("Failed to fetch Stripe subscription %s metadata: %s", sub_id, e)

            # Extract price_id and resolve tier from it
            lines = data.get("lines", {}).get("data", [])
            price_id = ""
            current_period_end = 0
            if lines:
                price_obj = lines[0].get("price", {})
                price_id = price_obj.get("id", "")
                current_period_end = lines[0].get("period", {}).get("end", 0)

            tier, interval = STRIPE_PRICE_TO_TIER.get(price_id, ("", ""))
            # Fallback to metadata if reverse mapping fails
            if not tier:
                tier = metadata.get("tier", "")
                interval = metadata.get("interval", "monthly")

            return WebhookEvent(
                event_type="payment.succeeded",
                provider_payment_id=data.get("payment_intent", "") or data["id"],
                provider_name=self.name,
                user_id=metadata.get("user_id", ""),
                tier=tier,
                interval=interval,
                amount_minor=data.get("amount_paid", 0),
                currency=(data.get("currency") or "eur").upper(),
                payment_method="card",
                promo_code=metadata.get("promo_code", ""),
                original_amount_minor=int(metadata.get("original_amount", "0")),
                raw_data=raw_data,
                stripe_subscription_id=sub_id,
                stripe_customer_id=customer_id,
                stripe_price_id=price_id,
                current_period_end=current_period_end,
            )

        # --- customer.subscription.updated (plan change, status change) ---
        if event_type == "customer.subscription.updated":
            metadata = data.get("metadata", {})
            customer_id = data.get("customer", "")
            sub_id = data["id"]

            # Extract current price from subscription items
            items = data.get("items", {}).get("data", [])
            price_id = ""
            if items:
                price_id = items[0].get("price", {}).get("id", "")

            tier, interval = STRIPE_PRICE_TO_TIER.get(price_id, ("", ""))
            if not tier:
                tier = metadata.get("tier", "")
                interval = metadata.get("interval", "monthly")

            return WebhookEvent(
                event_type="subscription.updated",
                provider_payment_id=sub_id,
                provider_name=self.name,
                user_id=metadata.get("user_id", ""),
                tier=tier,
                interval=interval,
                amount_minor=0,
                currency=(data.get("currency") or "eur").upper(),
                payment_method="card",
                promo_code="",
                original_amount_minor=0,
                raw_data=raw_data,
                stripe_subscription_id=sub_id,
                stripe_customer_id=customer_id,
                stripe_price_id=price_id,
                current_period_end=data.get("current_period_end", 0),
            )

        # --- customer.subscription.deleted (cancelled + period ended) ---
        if event_type == "customer.subscription.deleted":
            metadata = data.get("metadata", {})
            customer_id = data.get("customer", "")
            sub_id = data["id"]

            return WebhookEvent(
                event_type="subscription.deleted",
                provider_payment_id=sub_id,
                provider_name=self.name,
                user_id=metadata.get("user_id", ""),
                tier=metadata.get("tier", ""),
                interval=metadata.get("interval", "monthly"),
                amount_minor=0,
                currency=(data.get("currency") or "eur").upper(),
                payment_method="card",
                promo_code="",
                original_amount_minor=0,
                raw_data=raw_data,
                stripe_subscription_id=sub_id,
                stripe_customer_id=customer_id,
            )

        # --- checkout.session.expired ---
        if event_type == "checkout.session.expired":
            metadata = data.get("metadata", {})
            return WebhookEvent(
                event_type="payment.cancelled",
                provider_payment_id=data["id"],
                provider_name=self.name,
                user_id=metadata.get("user_id", ""),
                tier=metadata.get("tier", ""),
                interval=metadata.get("interval", "monthly"),
                amount_minor=data.get("amount_total", 0),
                currency=(data.get("currency") or "eur").upper(),
                payment_method="card",
                promo_code=metadata.get("promo_code", ""),
                original_amount_minor=int(metadata.get("original_amount", "0")),
                raw_data=raw_data,
            )

        # Unknown event type — ignore
        return None
