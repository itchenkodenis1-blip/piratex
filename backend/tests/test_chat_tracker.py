"""Tests for ChatTracker (in-memory WebSocket connection manager)."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.chat import ChatTracker


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    tracker = ChatTracker()
    ws = AsyncMock()

    await tracker.connect("user1", ws)
    ws.accept.assert_awaited_once()
    assert tracker.is_connected("user1")

    await tracker.disconnect("user1", ws)
    assert not tracker.is_connected("user1")


@pytest.mark.asyncio
async def test_send_to_user():
    tracker = ChatTracker()
    ws = AsyncMock()

    await tracker.connect("user1", ws)
    await tracker.send_to_user("user1", {"type": "new_message", "text": "Hello"})

    ws.send_text.assert_awaited_once()
    payload = json.loads(ws.send_text.call_args[0][0])
    assert payload["type"] == "new_message"
    assert payload["text"] == "Hello"


@pytest.mark.asyncio
async def test_send_to_disconnected_user():
    tracker = ChatTracker()
    # Should not raise
    await tracker.send_to_user("nonexistent", {"type": "test"})


@pytest.mark.asyncio
async def test_multiple_connections():
    tracker = ChatTracker()
    ws1 = AsyncMock()
    ws2 = AsyncMock()

    await tracker.connect("user1", ws1)
    await tracker.connect("user1", ws2)

    await tracker.send_to_user("user1", {"type": "test"})

    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_dead_connection_cleanup():
    tracker = ChatTracker()
    ws_alive = AsyncMock()
    ws_dead = AsyncMock()
    ws_dead.send_text.side_effect = Exception("Connection closed")

    await tracker.connect("user1", ws_alive)
    await tracker.connect("user1", ws_dead)

    await tracker.send_to_user("user1", {"type": "test"})

    # Dead connection should be cleaned up
    ws_alive.send_text.assert_awaited_once()
    assert tracker.is_connected("user1")  # alive connection remains
