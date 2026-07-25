"""Chat tracker for support WebSocket connections.

Simpler than ProgressTracker — direct in-memory broadcast.
Each user has at most one open connection (multiple tabs = multiple connections).
"""

import json
import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ChatTracker:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, user_id: str, ws: WebSocket):
        """Accept WebSocket and register for chat messages."""
        await ws.accept()
        self._connections[user_id].append(ws)
        logger.debug("Support WS connected: user=%s (total=%d)", user_id, len(self._connections[user_id]))

    async def disconnect(self, user_id: str, ws: WebSocket):
        """Remove WebSocket from the connection pool."""
        if user_id in self._connections:
            self._connections[user_id] = [
                c for c in self._connections[user_id] if c is not ws
            ]
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.debug("Support WS disconnected: user=%s", user_id)

    async def send_to_user(self, user_id: str, message: dict):
        """Send a message to all WebSocket connections for a user."""
        connections = self._connections.get(user_id, [])
        if not connections:
            return

        payload = json.dumps(message, default=str)
        dead = []
        for ws in connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        for ws in dead:
            await self.disconnect(user_id, ws)

    def is_connected(self, user_id: str) -> bool:
        """Check if user has any active WebSocket connections."""
        return bool(self._connections.get(user_id))


# Singleton instance
chat_tracker = ChatTracker()
