import hashlib
import json
import logging

from app.core.redis_pool import get_redis

logger = logging.getLogger(__name__)


def make_cache_key(*parts: str) -> str:
    """Create a cache key from multiple string parts."""
    raw = "\n---\n".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


async def cache_get(prefix: str, key: str) -> dict | None:
    """Get a cached JSON value. Returns None on miss or error."""
    try:
        r = await get_redis()
        if not r:
            return None
        data = await r.get(f"{prefix}:{key}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug("Cache get error: %s", e)
    return None


async def cache_set(prefix: str, key: str, value: dict, ttl: int = 86400) -> None:
    """Set a cached JSON value with TTL (default 24h). Silently ignores errors."""
    try:
        r = await get_redis()
        if not r:
            return
        await r.set(f"{prefix}:{key}", json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception as e:
        logger.debug("Cache set error: %s", e)
