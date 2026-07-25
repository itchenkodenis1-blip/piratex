"""Morning Brief — personalized daily briefing in Telegram.

Sent at 09:00 UTC to users with tracked authors or configured niches.
Content varies by tier:
  - PRO/UNLIMITED: full briefing (tracked authors updates + top trending in niches)
  - START: short briefing (top-3 trending in niches)
  - FREE: teaser (1 trending reel + CTA)
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis_pool import get_redis
from app.models.trends import ProfileReel, TrackedProfile, UserTrackedProfile
from app.models.user import User, UserSettings
from app.schemas.profile import UserProfile
from app.services.telegram import escape_html, send_telegram_message

logger = logging.getLogger(__name__)

_DEDUP_TTL = 82800  # ~23 hours — prevents double-send within a day


# ---------------------------------------------------------------------------
# Data queries
# ---------------------------------------------------------------------------

async def get_trending_by_niches(
    db: AsyncSession,
    niches: list[str],
    hours: int = 24,
    limit: int = 5,
) -> list[tuple[ProfileReel, TrackedProfile]]:
    """Top trending reels matching given niches from the last N hours."""
    if not niches:
        return []

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(ProfileReel, TrackedProfile)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.is_hidden == False,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            ProfileReel.hot_score.isnot(None),
            ProfileReel.published_at >= cutoff,
            # Match reel niche or profile niche
            (ProfileReel.niche.in_(niches)) | (TrackedProfile.niche.in_(niches)),
        )
        .order_by(ProfileReel.hot_score.desc().nullslast())
        .limit(limit)
    )
    return list(result.all())


async def get_tracked_authors_updates(
    db: AsyncSession,
    user_id: str,
    hours: int = 24,
    limit: int = 5,
) -> list[tuple[ProfileReel, TrackedProfile]]:
    """Recent reels from authors this user tracks (last N hours)."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(ProfileReel, TrackedProfile)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .join(
            UserTrackedProfile,
            (UserTrackedProfile.profile_id == TrackedProfile.id)
            & (UserTrackedProfile.user_id == user_id),
        )
        .where(
            ProfileReel.is_hidden == False,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            ProfileReel.published_at >= cutoff,
        )
        .order_by(ProfileReel.views.desc().nullslast())
        .limit(limit)
    )
    return list(result.all())


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_views(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _format_reel_line(reel: ProfileReel, profile: TrackedProfile) -> str:
    username = escape_html(profile.username or "?")
    views = _fmt_views(reel.views or 0)
    x_str = f"X{reel.x_factor:.1f}" if reel.x_factor else ""
    caption = (reel.caption or "")[:50]
    if len(reel.caption or "") > 50:
        caption += "..."
    caption = escape_html(caption)

    line = f"  @{username}"
    if x_str:
        line += f" \u2022 {x_str}"
    line += f" \u2022 {views}"
    if caption:
        line += f"\n  <i>{caption}</i>"
    if reel.url:
        line += f'\n  <a href="{reel.url}">\u25b6\ufe0f \u0421\u043c\u043e\u0442\u0440\u0435\u0442\u044c</a>'
    return line


def format_morning_brief(
    user_name: str,
    tier: str,
    trending: list[tuple[ProfileReel, TrackedProfile]],
    author_updates: list[tuple[ProfileReel, TrackedProfile]],
) -> str | None:
    """Build morning brief text. Returns None if nothing to show."""
    lines: list[str] = []

    # Header
    name = escape_html(user_name or "")
    if name:
        lines.append(f"\u2600\ufe0f <b>\u0414\u043e\u0431\u0440\u043e\u0435 \u0443\u0442\u0440\u043e, {name}</b>")
    else:
        lines.append("\u2600\ufe0f <b>\u0414\u043e\u0431\u0440\u043e\u0435 \u0443\u0442\u0440\u043e</b>")

    has_content = False

    # --- Tracked authors section (PRO / UNLIMITED only) ---
    if tier in ("PRO", "UNLIMITED") and author_updates:
        lines.append("")
        lines.append("\U0001f464 <b>\u0412\u0430\u0448\u0438 \u0430\u0432\u0442\u043e\u0440\u044b</b>")
        seen_authors: set[str] = set()
        for reel, profile in author_updates[:3]:
            if profile.id in seen_authors:
                continue
            seen_authors.add(profile.id)
            lines.append(_format_reel_line(reel, profile))
        has_content = True

    # --- Trending in niches section ---
    if tier in ("PRO", "UNLIMITED"):
        # Full: top 5
        if trending:
            lines.append("")
            lines.append("\U0001f525 <b>\u0422\u0440\u0435\u043d\u0434\u044b \u0432 \u0432\u0430\u0448\u0438\u0445 \u043d\u0438\u0448\u0430\u0445</b>")
            for reel, profile in trending[:5]:
                lines.append(_format_reel_line(reel, profile))
            has_content = True
    elif tier == "START":
        # Short: top 3
        if trending:
            lines.append("")
            lines.append("\U0001f525 <b>\u0422\u043e\u043f-3 \u0442\u0440\u0435\u043d\u0434\u0430</b>")
            for reel, profile in trending[:3]:
                lines.append(_format_reel_line(reel, profile))
            has_content = True
    else:
        # FREE: teaser — 1 reel + CTA
        if trending:
            reel, profile = trending[0]
            lines.append("")
            lines.append("\U0001f525 <b>\u0422\u0440\u0435\u043d\u0434 \u0432 \u0432\u0430\u0448\u0435\u0439 \u043d\u0438\u0448\u0435</b>")
            lines.append(_format_reel_line(reel, profile))
            lines.append("")
            lines.append(
                f'\U0001f680 <a href="{settings.app_url}/pricing">'
                "\u0420\u0430\u0437\u0431\u043b\u043e\u043a\u0438\u0440\u0443\u0439\u0442\u0435 \u043f\u043e\u043b\u043d\u044b\u0439 \u0431\u0440\u0438\u0444\u0438\u043d\u0433"
                " \u2014 START \u043e\u0442 \u20bd2000/\u043c\u0435\u0441</a>"
            )
            has_content = True

    if not has_content:
        return None

    # Footer
    lines.append("")
    lines.append(
        f'<a href="{settings.app_url}/trends">\U0001f4ca \u0412\u0441\u0435 \u0442\u0440\u0435\u043d\u0434\u044b</a>'
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def send_morning_briefs(db: AsyncSession) -> int:
    """Send personalized morning briefs to all eligible users.

    Returns number of messages sent.
    """
    if not settings.telegram_bot_token:
        return 0

    redis = await get_redis()

    # Load all non-anonymous users with Telegram
    result = await db.execute(
        select(User, UserSettings)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.telegram_user_id.isnot(None),
            User.is_anonymous == False,  # noqa: E712
        )
    )
    rows = result.all()

    # Batch-load tracked author counts (prevents N+1)
    user_ids = [user.id for user, _ in rows]
    tracked_counts: dict[str, int] = {}
    if user_ids:
        tc_result = await db.execute(
            select(UserTrackedProfile.user_id, func.count())
            .where(UserTrackedProfile.user_id.in_(user_ids))
            .group_by(UserTrackedProfile.user_id)
        )
        tracked_counts = dict(tc_result.all())

    sent = 0
    for user, user_settings in rows:
        try:
            # Parse profile
            profile: UserProfile | None = None
            if user_settings and user_settings.profile_json:
                try:
                    profile = UserProfile(**user_settings.profile_json)
                except Exception:
                    pass

            # Check if morning brief is disabled
            if profile and profile.morning_brief_enabled is False:
                continue

            tier = user.tier or "FREE"
            # Skip ANONYMOUS and REGISTERED — they haven't activated yet
            if tier in ("ANONYMOUS", "REGISTERED"):
                continue

            niches = (profile.niches or []) if profile else []
            tracked_count = tracked_counts.get(user.id, 0)

            # Skip if no personalization data
            if not niches and tracked_count == 0:
                continue

            # Dedup: max one brief per user per day
            dedup_key = f"morning_brief:{user.id}"
            if redis:
                already_sent = not await redis.set(dedup_key, "1", nx=True, ex=_DEDUP_TTL)
                if already_sent:
                    continue

            # Gather data
            trending = await get_trending_by_niches(db, niches) if niches else []
            author_updates = (
                await get_tracked_authors_updates(db, user.id)
                if tracked_count > 0 and tier in ("PRO", "UNLIMITED")
                else []
            )

            # Format
            user_name = user.name or (user_settings.profile_json or {}).get("about_me", "")[:20] if user_settings else ""
            text = format_morning_brief(user_name, tier, trending, author_updates)
            if not text:
                # Nothing to show — release dedup key
                if redis:
                    await redis.delete(dedup_key)
                continue

            # Send
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "\U0001f4ca \u0422\u0440\u0435\u043d\u0434\u044b", "url": f"{settings.app_url}/trends"},
                ]]
            }
            await send_telegram_message(
                user.telegram_user_id,
                settings.telegram_bot_token,
                text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            sent += 1

        except Exception:
            logger.debug("[morning_brief] Failed for user %s", user.id[:8], exc_info=True)

    logger.info("[morning_brief] Sent %d briefs", sent)
    return sent
