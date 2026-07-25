"""Progress tracker with Redis Pub/Sub bridge.

Workers call broadcast() → publishes to Redis channel job:{job_id}:progress.
Web process subscribes to the channel and forwards messages to local WebSocket clients.

Falls back to direct in-memory broadcast when Redis is not available (local dev without Redis).
"""

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ProgressTracker:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._subscriptions: dict[str, asyncio.Task] = {}

    async def _get_redis(self):
        """Get Redis from shared pool. Returns None if unavailable."""
        from app.core.redis_pool import get_redis
        return await get_redis()

    async def connect(self, job_id: str, ws: WebSocket):
        """Accept WebSocket and start subscribing to Redis channel for this job."""
        await ws.accept()
        self._connections[job_id].append(ws)

        # Send current job state from DB so client doesn't miss progress
        await self._send_current_state(job_id, ws)

        # Start Redis subscription for this job_id (if not already running)
        if job_id not in self._subscriptions:
            redis = await self._get_redis()
            if redis:
                task = asyncio.create_task(self._subscribe_and_forward(job_id))
                self._subscriptions[job_id] = task

    async def _send_current_state(self, job_id: str, ws: WebSocket):
        """Fetch current job state from DB and send to newly connected client."""
        try:
            from app.database import get_db_session
            from app.models.job import Job

            async with get_db_session() as db:
                job = await db.get(Job, job_id)
                if not job:
                    return

                # Send progress update
                await ws.send_json({
                    "type": "progress",
                    "status": job.status.value if hasattr(job.status, "value") else job.status,
                    "progress": job.progress or 0,
                    "message": job.progress_message or "",
                })

                # Send metadata if available
                if job.video_title or job.video_duration:
                    await ws.send_json({
                        "type": "metadata",
                        "title": job.video_title,
                        "duration": job.video_duration,
                        "platform": job.video_platform,
                        "author": job.video_author,
                        "views": job.video_views,
                        "likes": job.video_likes,
                        "comments": job.video_comments,
                        "thumbnail": None,
                    })

                # Send transcript if available
                if job.transcript:
                    await ws.send_json({
                        "type": "transcript",
                        "segments": job.transcript,
                    })

                # Send frames if available
                if job.frames:
                    # Send stubs as a batch first (so the grid skeleton renders)
                    stubs = []
                    for frame in job.frames:
                        ts = frame.get("timestamp", 0)
                        minutes, seconds = divmod(int(ts), 60)
                        stubs.append({
                            "frame_index": frame.get("frame_index", 0),
                            "timestamp": ts,
                            "timecode": f"{minutes:02d}:{seconds:02d}",
                        })
                    await ws.send_json({"type": "frames_extracted", "frames": stubs})

                    # Send analyses
                    for frame in job.frames:
                        await ws.send_json({
                            "type": "frame_analyzed",
                            "frame": frame,
                        })

                # Send adaptation summary if available
                if job.adaptation_summary:
                    # Split combined summary into content + strategy parts
                    summary = job.adaptation_summary
                    content_keys = {"script", "description", "editor_instructions", "hooks", "scenes"}
                    strategy_keys = {"language", "content_format", "topics", "keywords", "niche", "cover", "why_it_works", "adaptation_tips"}

                    content_data = {k: v for k, v in summary.items() if k in content_keys}
                    strategy_data = {k: v for k, v in summary.items() if k in strategy_keys}

                    if content_data:
                        await ws.send_json({"type": "content_ready", "summary": summary})
                    if strategy_data:
                        await ws.send_json({"type": "strategy_ready", "strategy": summary})

        except Exception as e:
            logger.warning("Failed to send current state for job %s: %s", job_id, e)

    async def disconnect(self, job_id: str, ws: WebSocket):
        """Remove WebSocket from local connections. Clean up subscription if no clients left."""
        conns = self._connections[job_id]
        if ws in conns:
            conns.remove(ws)
        if not conns:
            del self._connections[job_id]
            sub_task = self._subscriptions.pop(job_id, None)
            if sub_task and not sub_task.done():
                sub_task.cancel()

    async def broadcast(self, job_id: str, data: dict):
        """Publish progress to Redis Pub/Sub (or fallback to local broadcast)."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.publish(f"job:{job_id}:progress", json.dumps(data))
                return
            except Exception as e:
                logger.warning("Redis publish failed, falling back to local: %s", e)

        # Fallback: direct local broadcast (same-process only)
        await self._local_broadcast(job_id, data)

    async def _subscribe_and_forward(self, job_id: str):
        """Subscribe to Redis Pub/Sub channel and forward messages to local WebSockets."""
        redis = await self._get_redis()
        if not redis:
            return

        channel = f"job:{job_id}:progress"
        pubsub = redis.pubsub()
        try:
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self._local_broadcast(job_id, data)
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning("Failed to forward Redis message: %s", e)

                # Stop if no more local clients
                if job_id not in self._connections:
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Redis subscription error for job %s: %s", job_id, e)
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass

    async def _local_broadcast(self, job_id: str, data: dict):
        """Send data to locally connected WebSocket clients only."""
        dead = []
        for ws in self._connections.get(job_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns = self._connections.get(job_id, [])
            if ws in conns:
                conns.remove(ws)
        if job_id in self._connections and not self._connections[job_id]:
            del self._connections[job_id]


progress_tracker = ProgressTracker()
