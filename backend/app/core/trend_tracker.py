"""Trend monitoring tracker — Redis Pub/Sub bridge for admin dashboard.

Scheduler publishes events to Redis channel `admin:trend-watching`.
This tracker subscribes and forwards to connected admin WebSocket clients.
Single shared subscription for all admin clients (unlike ProgressTracker which
uses per-job channels).
"""

import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_CHANNEL = "admin:trend-watching"


class TrendTracker:
    def __init__(self):
        self._clients: list[WebSocket] = []
        self._sub_task: asyncio.Task | None = None

    async def _get_redis(self):
        """Get Redis from shared pool. Returns None if unavailable."""
        from app.core.redis_pool import get_redis
        return await get_redis()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)
        # Start shared subscription on first client
        if self._sub_task is None or self._sub_task.done():
            redis = await self._get_redis()
            if redis:
                self._sub_task = asyncio.create_task(self._subscribe_loop())

    async def disconnect(self, ws: WebSocket):
        if ws in self._clients:
            self._clients.remove(ws)
        if not self._clients and self._sub_task and not self._sub_task.done():
            self._sub_task.cancel()
            self._sub_task = None

    async def _subscribe_loop(self):
        backoff = 1
        while self._clients:
            redis = await self._get_redis()
            if not redis:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe(_CHANNEL)
                backoff = 1  # reset on successful connect
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            await self._broadcast(data)
                        except Exception as e:
                            logger.debug("[trend-tracker] Forward error: %s", e)
                    if not self._clients:
                        return
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("[trend-tracker] Subscription error: %s (retry in %ds)", e, backoff)
                pass  # shared pool handles reconnection
            finally:
                try:
                    await pubsub.unsubscribe(_CHANNEL)
                    await pubsub.close()
                except Exception:
                    pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _broadcast(self, data: dict):
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._clients:
                self._clients.remove(ws)


trend_tracker = TrendTracker()
