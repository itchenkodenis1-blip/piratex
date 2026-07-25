"""YooKassa payment provider integration.

Wraps the synchronous yookassa SDK with asyncio.to_thread for FastAPI compatibility.
"""

import asyncio
import logging
import uuid

from yookassa import Configuration, Payment as YKPayment

from app.config import settings

logger = logging.getLogger(__name__)


def _ensure_configured():
    if not Configuration.account_id:
        Configuration.account_id = settings.yookassa_shop_id
        Configuration.secret_key = settings.yookassa_secret_key


async def create_payment(
    *,
    amount_kopecks: int,
    currency: str = "RUB",
    description: str,
    return_url: str,
    save_payment_method: bool = False,
    payment_method_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Create a YooKassa payment and return the full response dict.

    For first payment: save_payment_method=True to enable recurring.
    For recurring: pass payment_method_id from saved card.
    """
    _ensure_configured()

    amount_rub = f"{amount_kopecks / 100:.2f}"
    idempotence_key = str(uuid.uuid4())

    params: dict = {
        "amount": {"value": amount_rub, "currency": currency},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": description,
        "metadata": metadata or {},
    }

    if save_payment_method:
        params["save_payment_method"] = True

    if payment_method_id:
        # Recurring charge — no confirmation needed
        params.pop("confirmation", None)
        params["payment_method_id"] = payment_method_id

    # Receipt for 54-FZ compliance
    params["receipt"] = {
        "customer": {"email": metadata.get("email", "") if metadata else ""},
        "items": [
            {
                "description": description[:128],
                "quantity": "1.00",
                "amount": {"value": amount_rub, "currency": currency},
                "vat_code": 1,  # без НДС
            }
        ],
    }
    # Remove receipt if no email (YooKassa requires email or phone)
    if not params["receipt"]["customer"]["email"]:
        params.pop("receipt", None)

    def _create():
        return YKPayment.create(params, idempotence_key)

    result = await asyncio.to_thread(_create)
    return result.json()


async def get_payment(payment_id: str) -> dict:
    """Fetch payment details from YooKassa."""
    _ensure_configured()

    def _find():
        return YKPayment.find_one(payment_id)

    result = await asyncio.to_thread(_find)
    return result.json()


async def cancel_payment(payment_id: str) -> dict:
    """Cancel a pending payment."""
    _ensure_configured()
    idempotence_key = str(uuid.uuid4())

    def _cancel():
        return YKPayment.cancel(payment_id, idempotence_key)

    result = await asyncio.to_thread(_cancel)
    return result.json()
