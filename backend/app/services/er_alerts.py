"""ER Drop Alerts — detect and notify users when tracked authors lose engagement.

Uses Redis snapshots to compare current profile metrics with previous check cycle.
Sends alerts to users who track the affected author via Telegram.

Thresholds:
  - ER drop >25%  → alert
  - Views drop >40% → alert
  - Dedup: max 1 alert per author per 7 days
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trends import ProfileReel, TrackedProfile, UserTrackedProfile
from app.models.user import User
from app.services.telegram import escape_html, send_telegram_message

logger = logging.getLogger(__name__)

_SNAPSHOT_TTL = 86400 * 14   # 14 days
_ALERT_DEDUP_TTL = 86400 * 7  # 7 days — max 1 alert per author per week

ER_DROP_THRESHOLD = 0.25    # 25% drop
VIEWS_DROP_THRESHOLD = 0.40  # 40% drop
MIN_REELS_FOR_ER = 3        # need at least 3 reels to compute meaningful ER


# ---------------------------------------------------------------------------
# ER calculation from recent reels
# ---------------------------------------------------------------------------

def _compute_er_from_reels(reels: list[ProfileReel]) -> float | None:
    """Compute average engagement rate from a list of reels.

    ER = (likes + comments) / views for each reel, then average.
    Returns None if not enough data.
    """
    rates = []
    for r in reels:
        if r.views and r.views > 100 and r.likes is not None:
            er = (r.likes + (r.comments or 0)) / r.views
            rates.append(er)
    if len(rates) < MIN_REELS_FOR_ER:
        return None
    return sum(rates) / len(rates)


# ---------------------------------------------------------------------------
# Redis snapshot management
# ---------------------------------------------------------------------------

async def save_profile_snapshot(
    redis, profile: TrackedProfile, er: float | None,
) -> None:
    """Save current profile metrics to Redis for comparison on next cycle."""
    if redis is None:
        return

    data = {
        "median_views": profile.median_views,
        "avg_views": profile.avg_views,
        "followers": profile.followers_count,
        "er": er,
        "ts": datetime.utcnow().isoformat(),
    }
    try:
        await redis.set(
            f"profile_snapshot:{profile.id}",
            json.dumps(data),
            ex=_SNAPSHOT_TTL,
        )
    except Exception:
        logger.debug("[er_alerts] Failed to save snapshot for %s", profile.id[:8])


async def _get_previous_snapshot(redis, profile_id: str) -> dict | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(f"profile_snapshot:{profile_id}")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


async def _is_alert_deduped(redis, profile_id: str) -> bool:
    if redis is None:
        return False
    try:
        return bool(await redis.exists(f"er_alert:{profile_id}"))
    except Exception:
        return False


async def _mark_alert_sent(redis, profile_id: str) -> None:
    if redis is None:
        return
    try:
        await redis.set(f"er_alert:{profile_id}", "1", ex=_ALERT_DEDUP_TTL)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Detection + notification
# ---------------------------------------------------------------------------

def _fmt_views(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_pct(drop: float) -> str:
    return f"{abs(drop) * 100:.0f}%"


async def check_and_alert_er_drops(
    db: AsyncSession,
    profile: TrackedProfile,
    recent_reels: list[ProfileReel],
    redis=None,
) -> int:
    """Check for ER/views drops and notify tracking users.

    Called after profile metrics are updated in _process_profile_data.
    Returns number of alerts sent.
    """
    if not settings.telegram_bot_token or redis is None:
        return 0

    # Compute current ER
    current_er = _compute_er_from_reels(recent_reels)

    # Get previous snapshot
    prev = await _get_previous_snapshot(redis, profile.id)

    if prev is None:
        # First check — no comparison possible, just save snapshot
        await save_profile_snapshot(redis, profile, current_er)
        return 0

    # Check dedup
    if await _is_alert_deduped(redis, profile.id):
        return 0

    # Detect drops
    alerts: list[str] = []

    prev_er = prev.get("er")
    if current_er is not None and prev_er is not None and prev_er > 0:
        er_change = (current_er - prev_er) / prev_er
        if er_change < -ER_DROP_THRESHOLD:
            alerts.append(
                f"\U0001f4c9 ER \u0443\u043f\u0430\u043b \u043d\u0430 {_fmt_pct(er_change)}: "
                f"{prev_er * 100:.1f}% \u2192 {current_er * 100:.1f}%"
            )

    prev_views = prev.get("median_views")
    curr_views = profile.median_views
    if curr_views is not None and prev_views is not None and prev_views > 0:
        views_change = (curr_views - prev_views) / prev_views
        if views_change < -VIEWS_DROP_THRESHOLD:
            alerts.append(
                f"\U0001f4c9 \u041c\u0435\u0434\u0438\u0430\u043d\u043d\u044b\u0435 \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u044b \u0443\u043f\u0430\u043b\u0438 \u043d\u0430 {_fmt_pct(views_change)}: "
                f"{_fmt_views(int(prev_views))} \u2192 {_fmt_views(int(curr_views))}"
            )

    # Save current snapshot after comparison (so next cycle sees these values)
    await save_profile_snapshot(redis, profile, current_er)

    if not alerts:
        return 0

    # Build message
    username = escape_html(profile.username or "?")
    text = (
        f"\u26a0\ufe0f <b>\u0410\u043b\u0435\u0440\u0442: @{username}</b>\n\n"
        + "\n".join(alerts)
        + "\n\n\u042d\u0442\u043e \u043c\u043e\u0436\u0435\u0442 \u0432\u043b\u0438\u044f\u0442\u044c \u043d\u0430 \u044d\u0444\u0444\u0435\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c \u0441\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u0447\u0435\u0441\u0442\u0432\u0430."
    )

    if profile.profile_url:
        text += f'\n\n<a href="{profile.profile_url}">\U0001f464 \u041f\u0440\u043e\u0444\u0438\u043b\u044c \u0430\u0432\u0442\u043e\u0440\u0430</a>'

    # Find users tracking this profile
    result = await db.execute(
        select(User)
        .join(UserTrackedProfile, UserTrackedProfile.user_id == User.id)
        .where(
            UserTrackedProfile.profile_id == profile.id,
            User.telegram_user_id.isnot(None),
            User.is_anonymous == False,  # noqa: E712
        )
    )
    users = result.scalars().all()

    if not users:
        return 0

    sent = 0
    for user in users:
        try:
            await send_telegram_message(
                user.telegram_user_id, settings.telegram_bot_token, text,
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            pass

    if sent > 0:
        await _mark_alert_sent(redis, profile.id)
        logger.info(
            "[er_alerts] Alert for @%s sent to %d users: %s",
            profile.username, sent, "; ".join(alerts),
        )

    return sent
