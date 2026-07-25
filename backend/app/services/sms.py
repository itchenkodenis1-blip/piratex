import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def send_sms_code(phone: str, code: str) -> bool:
    """Send an SMS code via sms.ru. Falls back to logging in dev."""
    if not settings.sms_provider_api_key:
        logger.info("(dev) SMS code for %s: %s", phone, code)
        return True

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://sms.ru/sms/send",
                params={
                    "api_id": settings.sms_provider_api_key,
                    "to": phone,
                    "msg": f"Piratex.ai: ваш код {code}",
                    "json": 1,
                },
            )
            resp.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to send SMS to %s", phone)
        return False
