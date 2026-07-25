"""Shared Redis connection pool for all backend services.

Instead of each module creating its own Redis connection,
all consumers should use get_redis() from this module.
This prevents connection leaks and limits total connections.
"""

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: aioredis.ConnectionPool | None = None


def _ensure_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=50,
            decode_responses=True,
        )
        logger.info("[redis-pool] Created shared pool (max_connections=50)")
    return _pool


async def get_redis() -> aioredis.Redis | None:
    """Get a Redis client from the shared pool. Returns None if unavailable."""
    try:
        pool = _ensure_pool()
        return aioredis.Redis(connection_pool=pool)
    except Exception as e:
        logger.warning("[redis-pool] Redis unavailable: %s", e)
        return None


async def close_pool() -> None:
    """Close the shared pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        logger.info("[redis-pool] Closed shared pool")
