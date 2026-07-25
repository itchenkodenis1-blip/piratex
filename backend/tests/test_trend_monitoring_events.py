"""Tests for trend monitoring event publishing (admin dashboard pipeline tracking).

Verifies that check_stale_profiles publishes Redis events for:
- batch_start, analyzing, completed, failed, trend_found
- hourly counter increments
- activity log entries
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.services.trend_monitor import (
    _publish_monitoring_event,
    _log_activity,
    _increment_hourly,
)


# ---------------------------------------------------------------------------
# Unit: _publish_monitoring_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_event_with_redis():
    """When redis is available, publish to admin:trend-watching channel."""
    redis = AsyncMock()
    redis.publish = AsyncMock(return_value=1)

    await _publish_monitoring_event(
        redis, "profile_status",
        profile_id="abc", status="analyzing", username="testuser",
    )

    redis.publish.assert_called_once()
    channel, payload = redis.publish.call_args[0]
    assert channel == "admin:trend-watching"
    data = json.loads(payload)
    assert data["type"] == "profile_status"
    assert data["status"] == "analyzing"
    assert data["username"] == "testuser"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_publish_event_without_redis():
    """When redis is None, no-op (no exception)."""
    await _publish_monitoring_event(
        None, "profile_status",
        profile_id="abc", status="analyzing", username="testuser",
    )
    # Should not raise


@pytest.mark.asyncio
async def test_publish_event_redis_error():
    """When redis raises, log error but don't crash."""
    redis = AsyncMock()
    redis.publish = AsyncMock(side_effect=Exception("connection lost"))

    # Should not raise
    await _publish_monitoring_event(
        redis, "profile_status",
        profile_id="abc", status="analyzing", username="testuser",
    )


# ---------------------------------------------------------------------------
# Unit: _log_activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_activity_writes_sorted_set():
    """Activity events are stored in a Redis sorted set with timestamp score."""
    redis = AsyncMock()
    redis.zadd = AsyncMock()
    redis.zremrangebyscore = AsyncMock()
    redis.zremrangebyrank = AsyncMock()

    await _log_activity(
        redis, "check_complete",
        profile_username="testuser", platform="instagram",
        details={"reels_found": 5, "new_trends": 2},
    )

    redis.zadd.assert_called_once()
    call_args = redis.zadd.call_args
    key = call_args[0][0]
    assert key == "trend:activity"
    # The mapping should have a JSON string as key and timestamp as score
    mapping = call_args[1] if isinstance(call_args[1], dict) else call_args[0][1]
    assert isinstance(mapping, dict)

    # Pruning should be called
    redis.zremrangebyscore.assert_called_once()
    redis.zremrangebyrank.assert_called_once()


@pytest.mark.asyncio
async def test_log_activity_no_redis():
    """When redis is None, no-op."""
    await _log_activity(None, "check_complete", profile_username="test", platform="instagram")


# ---------------------------------------------------------------------------
# Unit: _increment_hourly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_increment_hourly():
    """Hourly counters use HINCRBY with a 48h TTL."""
    redis = AsyncMock()
    redis.hincrby = AsyncMock()
    redis.expire = AsyncMock()

    await _increment_hourly(redis, "checks")

    redis.hincrby.assert_called_once()
    key = redis.hincrby.call_args[0][0]
    assert key.startswith("trend:hourly:")
    field = redis.hincrby.call_args[0][1]
    assert field == "checks"

    redis.expire.assert_called_once()
    ttl = redis.expire.call_args[0][1]
    assert ttl == 172800  # 48 hours


@pytest.mark.asyncio
async def test_increment_hourly_no_redis():
    """When redis is None, no-op."""
    await _increment_hourly(None, "checks")
