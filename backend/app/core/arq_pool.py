"""Managed arq Redis pool with auto-reconnect.

The web process needs an arq pool to enqueue jobs. If Redis restarts
(e.g. Railway maintenance), the pool becomes stale and all enqueue calls
fail with 503. This wrapper adds health checking and reconnection.
"""

import asyncio
import logging

from arq import ArqRedis
from arq.connections import RedisSettings, create_pool

from app.config import settings

logger = logging.getLogger(__name__)

_RECONNECT_DELAYS = [1, 2, 4, 8, 16]  # exponential backoff


class ManagedArqPool:
    """arq pool wrapper with health check and auto-reconnect."""

    def __init__(self):
        self._pool: ArqRedis | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> ArqRedis | None:
        """Create initial connection."""
        try:
            self._pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            logger.info("[arq-pool] Connected")
            return self._pool
        except Exception as e:
            logger.error("[arq-pool] Initial connection failed: %s", e)
            self._pool = None
            return None

    async def get_pool(self) -> ArqRedis | None:
        """Get a healthy pool, reconnecting if necessary."""
        if self._pool is not None:
            try:
                await self._pool.ping()
                return self._pool
            except Exception:
                logger.warning("[arq-pool] Health check failed, reconnecting...")
                self._pool = None

        async with self._lock:
            # Double-check after acquiring lock
            if self._pool is not None:
                try:
                    await self._pool.ping()
                    return self._pool
                except Exception:
                    self._pool = None

            for delay in _RECONNECT_DELAYS:
                try:
                    self._pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
                    logger.info("[arq-pool] Reconnected successfully")
                    return self._pool
                except Exception as e:
                    logger.warning("[arq-pool] Reconnect attempt failed: %s, retrying in %ds", e, delay)
                    await asyncio.sleep(delay)

            logger.error("[arq-pool] All reconnect attempts failed")
            return None

    async def close(self):
        if self._pool:
            await self._pool.close()
            self._pool = None


managed_arq_pool = ManagedArqPool()
