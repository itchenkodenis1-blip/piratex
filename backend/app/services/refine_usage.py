"""Redis-based daily refine usage counter.

Key pattern: refine:{user_id}:{YYYY-MM-DD}
TTL: 90000 seconds (25 hours — covers timezone edge cases)
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_pool import get_redis as _get_redis
from app.services.usage import _get_tier_limits

logger = logging.getLogger(__name__)

_KEY_TTL = 90_000  # 25 hours


def _key(user_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"refine:{user_id}:{today}"


async def get_refine_usage(user_id: str) -> int:
    """Return number of refines used today."""
    r = await _get_redis()
    if r is None:
        return 0
    val = await r.get(_key(user_id))
    return int(val) if val else 0


async def increment_refine_usage(user_id: str) -> int:
    """Increment and return the new count."""
    r = await _get_redis()
    if r is None:
        return 0
    key = _key(user_id)
    new_val = await r.incr(key)
    if new_val == 1:
        await r.expire(key, _KEY_TTL)
    return new_val


async def check_refine_allowed(
    user_id: str, tier: str, db: AsyncSession,
) -> tuple[bool, int, int]:
    """Check if user can make a refine request.

    Returns: (allowed, used_today, daily_limit)
    """
    tier = tier.upper()
    limits = await _get_tier_limits(db, tier)
    daily_limit = limits.get("max_refines_daily", 0)

    if daily_limit == 0:
        return (False, 0, 0)

    try:
        used = await get_refine_usage(user_id)
        return (used < daily_limit, used, daily_limit)
    except Exception:
        logger.warning("Redis unavailable for refine limit check, allowing request")
        return (True, 0, daily_limit)
