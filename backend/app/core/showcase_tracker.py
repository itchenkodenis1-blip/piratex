"""Showcase event tracker — Redis Pub/Sub bridge for live dashboard.

Backend services publish events (registration, analysis, payment) to Redis
channel ``showcase:events``.  This tracker subscribes and forwards them to
connected admin WebSocket clients.

Follows the same shared-subscription pattern as TrendTracker.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_CHANNEL = "showcase:events"


class ShowcaseTracker:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._sub_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """Get Redis from shared pool. Returns None if unavailable."""
        from app.core.redis_pool import get_redis
        return await get_redis()

    # ------------------------------------------------------------------
    # WebSocket lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.append(ws)
        if self._sub_task is None or self._sub_task.done():
            redis = await self._get_redis()
            if redis:
                self._sub_task = asyncio.create_task(self._subscribe_loop())

    async def disconnect(self, ws: WebSocket) -> None:
        if ws in self._clients:
            self._clients.remove(ws)
        if not self._clients and self._sub_task and not self._sub_task.done():
            self._sub_task.cancel()
            self._sub_task = None

    # ------------------------------------------------------------------
    # Redis subscription loop
    # ------------------------------------------------------------------

    async def _subscribe_loop(self) -> None:
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
                backoff = 1
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            await self._broadcast(data)
                        except Exception as e:
                            logger.debug("[showcase-tracker] Forward error: %s", e)
                    if not self._clients:
                        return
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning(
                    "[showcase-tracker] Subscription error: %s (retry in %ds)",
                    e,
                    backoff,
                )
                pass  # shared pool handles reconnection
            finally:
                try:
                    await pubsub.unsubscribe(_CHANNEL)
                    await pubsub.close()
                except Exception:
                    pass
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    # ------------------------------------------------------------------
    # Broadcast to connected clients
    # ------------------------------------------------------------------

    async def _broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._clients:
                self._clients.remove(ws)


# Singleton
showcase_tracker = ShowcaseTracker()


# ------------------------------------------------------------------
# Helper: emit event from anywhere in the backend
# ------------------------------------------------------------------


_TEST_EMAIL_DOMAINS = {"test.com", "example.com", "localhost"}


async def emit_showcase_event(
    event_type: str,
    **extra: str,
) -> None:
    """Publish a showcase event to Redis (best-effort, never raises).

    Events with masked_email from test domains are silently dropped.
    """
    try:
        # Filter out test emails from showcase feed
        masked = extra.get("masked_email", "")
        if masked:
            domain = masked.rpartition("@")[2].lower()
            if domain in _TEST_EMAIL_DOMAINS:
                return

        from app.core.redis_pool import get_redis

        r = await get_redis()
        if not r:
            return
        payload = {
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            **extra,
        }
        await r.publish(_CHANNEL, json.dumps(payload))
    except Exception as e:
        logger.debug("[showcase] Failed to emit %s event: %s", event_type, e)
