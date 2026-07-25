"""Cloudflare Turnstile verification for bot protection."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    """Verify a Turnstile token via Cloudflare API.

    Returns True if the token is valid or if Turnstile is disabled (empty secret key).
    """
    if not settings.turnstile_secret_key:
        return True

    if not token:
        return False

    payload = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(VERIFY_URL, data=payload)
            data = resp.json()
            success = data.get("success", False)
            if not success:
                logger.warning(
                    "TURNSTILE_FAIL ip=%s errors=%s",
                    remote_ip,
                    data.get("error-codes", []),
                )
            return success
    except Exception:
        logger.exception("TURNSTILE_ERROR ip=%s", remote_ip)
        # Fail open: if Cloudflare is unreachable, allow the request
        return True
