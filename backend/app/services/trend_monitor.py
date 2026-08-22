"""Trend monitoring service.

Tracks Instagram/YouTube profiles and detects trending reels based on X-factor
(views relative to the author's median performance).
"""

import asyncio
import json as _json
import logging
import math
import re
import statistics
import time as _time
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.niches import VALID_NICHES, niche_prompt_compact, niche_prompt_detailed, DISAMBIGUATION_RULES
from app.models.library import LibraryReel
from app.models.trends import ProfileReel, TrackedProfile, UserTrackedProfile
from app.models.user import User
from app.services.scraper._apify_client import run_actor
from app.services.scraper._instagram import _parse_metric
from app.storage import storage

logger = logging.getLogger(__name__)

# X-factor threshold: reels above this are marked as trending
X_FACTOR_THRESHOLD = 2.0
# Only calculate X-factor for profiles with at least this many reels
MIN_REELS_FOR_XFACTOR = 3
# Only mark reels as trending if published within this many days
TRENDING_MAX_AGE_DAYS = 7
# How long between profile checks (hours)
CHECK_INTERVAL_HOURS = 12

# Minimum absolute views to be considered trending
MIN_VIEWS_THRESHOLD = 1000
# After this many consecutive checks with no trending reels → cold priority
COLD_CHECK_LIMIT = 8

# Author tracking limits per tier
AUTHOR_LIMITS = {"ANONYMOUS": 100, "REGISTERED": 100, "FREE": 100, "START": 10, "PRO": 50, "UNLIMITED": 100}

# Pub/Sub channel for admin trend-watching dashboard
_MONITORING_CHANNEL = "admin:trend-watching"
_ACTIVITY_KEY = "trend:activity"
_ACTIVITY_MAX_AGE = 86400  # 24 hours
_ACTIVITY_MAX_SIZE = 1000
_HOURLY_TTL = 172800  # 48 hours


# ── Admin monitoring helpers ─────────────────────────────────────

async def _publish_monitoring_event(redis, event_type: str, **data) -> None:
    """Publish a monitoring event to Redis Pub/Sub. No-op if redis is None."""
    if redis is None:
        return
    try:
        payload = _json.dumps({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **data,
        })
        await redis.publish(_MONITORING_CHANNEL, payload)
    except Exception:
        logger.debug("[monitoring] Failed to publish event %s", event_type, exc_info=True)


async def _log_activity(redis, event_type: str, **data) -> None:
    """Append an event to the trend:activity sorted set. No-op if redis is None."""
    if redis is None:
        return
    try:
        now_ts = _time.time()
        entry = _json.dumps({
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **data,
        })
        await redis.zadd(_ACTIVITY_KEY, {entry: now_ts})
        # Prune: remove entries older than 24h
        await redis.zremrangebyscore(_ACTIVITY_KEY, "-inf", now_ts - _ACTIVITY_MAX_AGE)
        # Safety cap: keep only last 1000 entries
        await redis.zremrangebyrank(_ACTIVITY_KEY, 0, -(_ACTIVITY_MAX_SIZE + 1))
    except Exception:
        logger.debug("[monitoring] Failed to log activity %s", event_type, exc_info=True)


async def _increment_hourly(redis, field: str) -> None:
    """Increment an hourly counter for sparkline data. No-op if redis is None."""
    if redis is None:
        return
    try:
        now = datetime.utcnow()
        key = f"trend:hourly:{now.strftime('%Y-%m-%d')}:{now.hour}"
        await redis.hincrby(key, field, 1)
        await redis.expire(key, _HOURLY_TTL)
    except Exception:
        logger.debug("[monitoring] Failed to increment hourly %s", field, exc_info=True)


async def _track_ai_usage(tokens: int) -> None:
    """Increment daily AI token + call counters in Redis for cost tracking."""
    try:
        from app.core.redis_pool import get_redis
        r = await get_redis()
        if r is None:
            return
        today = date.today().isoformat()
        tok_key = f"trend:ai:tokens:{today}"
        call_key = f"trend:ai:calls:{today}"
        await r.incrby(tok_key, tokens)
        await r.incr(call_key)
        await r.expire(tok_key, 172800)
        await r.expire(call_key, 172800)
    except Exception:
        logger.debug("[monitoring] Failed to track AI usage", exc_info=True)


# ── Input parsing ────────────────────────────────────────────────

_PLATFORM_HOSTS = {
    "instagram": {"instagram.com", "www.instagram.com", "m.instagram.com"},
    "tiktok": {"tiktok.com", "www.tiktok.com", "m.tiktok.com"},
    "youtube": {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"},
}
_HOST_TO_PLATFORM = {h: p for p, hosts in _PLATFORM_HOSTS.items() for h in hosts}

# URL path prefixes that are NOT usernames
_IG_NON_PROFILE = {"reel", "reels", "p", "stories", "explore", "accounts", "direct", "tv"}
_YT_NON_PROFILE = {"watch", "shorts", "playlist", "feed", "results", "live", "embed"}


def parse_author_input(raw: str) -> tuple[str, str]:
    """Parse a profile URL or username into (platform, username).

    Supports:
      - https://instagram.com/username
      - https://www.tiktok.com/@username
      - https://youtube.com/@handle, /c/name, /channel/UCxxx
      - @username  (defaults to instagram)
      - username   (defaults to instagram)
    """
    raw = raw.strip()
    if not raw:
        raise HTTPException(400, "Input is required")

    # Try parsing as URL
    if "/" in raw and ("." in raw.split("/")[0] or raw.startswith("http")):
        url = raw if raw.startswith("http") else f"https://{raw}"
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        platform = _HOST_TO_PLATFORM.get(host)
        if not platform:
            raise HTTPException(400, f"Unsupported platform: {host}")

        # Extract username from path
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if not parts:
            raise HTTPException(400, "Could not extract username from URL")

        if platform == "youtube":
            # Reject non-profile URLs (watch, shorts, etc.)
            if parts[0].lower() in _YT_NON_PROFILE:
                raise HTTPException(400, "Please paste a profile link, not a video link")
            # /c/name, /channel/UCxxx, /@handle
            if parts[0] in ("c", "channel") and len(parts) > 1:
                username = parts[1]
            else:
                username = parts[0]
        elif platform == "instagram":
            # Reject non-profile URLs (reel, p, stories, etc.)
            if parts[0].lower() in _IG_NON_PROFILE:
                raise HTTPException(400, "Please paste a profile link, not a post link")
            username = parts[0]
        else:
            # tiktok: first path segment is the username
            username = parts[0]

        username = username.lstrip("@").lower()
        if not username:
            raise HTTPException(400, "Could not extract username from URL")
        return platform, username

    # Plain username (with or without @) → default to instagram
    username = raw.lstrip("@").strip().lower()
    if not username or not re.match(r"^[\w.]+$", username):
        raise HTTPException(400, "Invalid username")
    return "instagram", username


# ── User author management ───────────────────────────────────────

async def add_user_author(db: AsyncSession, user: User, platform: str, username: str) -> TrackedProfile:
    """Add an author to user's tracked list. Validates via Apify if new."""
    if platform not in ("instagram",):
        raise HTTPException(400, f"{platform.title()} tracking not yet supported")

    # Quick pre-check (without lock — optimistic, to fail fast)
    tier = user.tier or "ANONYMOUS"
    limit = AUTHOR_LIMITS.get(tier, 0)
    count_result = await db.execute(
        select(func.count()).select_from(UserTrackedProfile)
        .where(UserTrackedProfile.user_id == user.id, UserTrackedProfile.frozen == False)  # noqa: E712
    )
    if (count_result.scalar() or 0) >= limit:
        raise HTTPException(400, "Author tracking limit reached")

    # Check if profile already exists globally
    result = await db.execute(
        select(TrackedProfile).where(
            TrackedProfile.platform == platform,
            TrackedProfile.username == username,
        )
    )
    profile = result.scalar_one_or_none()

    if profile and profile.is_blocked:
        raise HTTPException(403, "This author has been blocked by moderation")

    if not profile:
        # Validate via Apify (slow — 10-30s, NO lock held here)
        profile_data = await _scrape_instagram_profile(username)
        if not profile_data:
            raise HTTPException(404, "Profile not found or private")

        profile_url = f"https://www.instagram.com/{username}/"
        display_name = profile_data.get("fullName") or username
        followers = _parse_metric(
            profile_data.get("followersCount") or profile_data.get("followers")
        )

        profile = TrackedProfile(
            platform=platform,
            username=username,
            display_name=display_name,
            profile_url=profile_url,
            followers_count=followers,
        )
        db.add(profile)
        await db.flush()
        logger.info(f"[trends] Created tracked profile via user add: {platform}/{username}")

    # Lock user row AFTER Apify to prevent race condition without long lock hold
    await db.execute(select(User).where(User.id == user.id).with_for_update())

    # Re-check limit under lock (authoritative check)
    count_result = await db.execute(
        select(func.count()).select_from(UserTrackedProfile)
        .where(UserTrackedProfile.user_id == user.id, UserTrackedProfile.frozen == False)  # noqa: E712
    )
    if (count_result.scalar() or 0) >= limit:
        raise HTTPException(400, "Author tracking limit reached")

    # Create junction if not exists, or unfreeze if frozen
    existing_result = await db.execute(
        select(UserTrackedProfile).where(
            UserTrackedProfile.user_id == user.id,
            UserTrackedProfile.profile_id == profile.id,
        )
    )
    existing_utp = existing_result.scalar_one_or_none()
    if existing_utp:
        if existing_utp.frozen:
            existing_utp.frozen = False
    else:
        db.add(UserTrackedProfile(user_id=user.id, profile_id=profile.id))

        # Record interest signals from followed author
        from app.services.interest_signals import record_signals
        topics = list(set(
            (profile.topics or []) + ([profile.niche] if profile.niche else [])
        ))
        if topics:
            await record_signals(
                db, user_id=user.id, topics=topics,
                source="follow", weight=0.7, source_id=str(profile.id),
            )

    await db.commit()
    return profile


async def remove_user_author(db: AsyncSession, user_id: str, profile_id: str) -> bool:
    """Remove an author from user's tracked list. Does NOT delete global profile."""
    result = await db.execute(
        select(UserTrackedProfile).where(
            UserTrackedProfile.user_id == user_id,
            UserTrackedProfile.profile_id == profile_id,
        )
    )
    junction = result.scalar_one_or_none()
    if not junction:
        return False
    await db.delete(junction)
    await db.commit()
    return True


async def get_user_authors(db: AsyncSession, user_id: str, include_frozen: bool = False) -> list[TrackedProfile]:
    """Get all profiles tracked by a specific user.

    By default returns only non-frozen (active) authors.
    Set include_frozen=True to return all.
    """
    query = (
        select(TrackedProfile)
        .join(UserTrackedProfile, UserTrackedProfile.profile_id == TrackedProfile.id)
        .where(UserTrackedProfile.user_id == user_id)
    )
    if not include_frozen:
        query = query.where(UserTrackedProfile.frozen == False)  # noqa: E712
    query = query.order_by(UserTrackedProfile.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_frozen_count(db: AsyncSession, user_id: str) -> int:
    """Return count of frozen authors for a user."""
    result = await db.execute(
        select(func.count()).select_from(UserTrackedProfile)
        .where(UserTrackedProfile.user_id == user_id, UserTrackedProfile.frozen == True)  # noqa: E712
    )
    return result.scalar() or 0


async def enforce_author_limits(db: AsyncSession, user_id: str, new_tier: str) -> None:
    """Freeze/unfreeze authors based on tier limits.

    On downgrade: freeze excess authors (keep top by trending_count).
    On upgrade: unfreeze authors up to the new limit.
    For profiles with no active (non-frozen) users: set check_priority='cold'.
    """
    limit = AUTHOR_LIMITS.get(new_tier, 0)

    # Get all user's tracked profiles with trending counts, ordered by trending_count DESC
    trending_sub = (
        select(func.count(ProfileReel.id))
        .where(
            ProfileReel.profile_id == UserTrackedProfile.profile_id,
            ProfileReel.is_trending == True,  # noqa: E712
        )
        .correlate(UserTrackedProfile)
        .scalar_subquery()
    )
    trending_count_col = func.coalesce(trending_sub, 0).label("trending_count")
    result = await db.execute(
        select(UserTrackedProfile, trending_count_col)
        .where(UserTrackedProfile.user_id == user_id)
        .order_by(trending_count_col.desc(), UserTrackedProfile.created_at.asc())
    )
    rows = result.all()

    affected_profile_ids: list[str] = []
    for idx, (utp, _trending_count) in enumerate(rows):
        should_freeze = idx >= limit
        if utp.frozen != should_freeze:
            utp.frozen = should_freeze
            affected_profile_ids.append(utp.profile_id)

    # Flush so subsequent queries see the updated frozen values
    if affected_profile_ids:
        await db.flush()

    # For profiles that were frozen/unfrozen: check if they still have active users
    if affected_profile_ids:
        for profile_id in affected_profile_ids:
            active_count_result = await db.execute(
                select(func.count()).select_from(UserTrackedProfile)
                .where(
                    UserTrackedProfile.profile_id == profile_id,
                    UserTrackedProfile.frozen == False,  # noqa: E712
                )
            )
            active_count = active_count_result.scalar() or 0
            if active_count == 0:
                # No active users following this profile — mark cold
                await db.execute(
                    update(TrackedProfile)
                    .where(TrackedProfile.id == profile_id)
                    .values(check_priority="cold")
                )
            else:
                # Profile has active users again — restore normal priority
                await db.execute(
                    update(TrackedProfile)
                    .where(TrackedProfile.id == profile_id, TrackedProfile.check_priority == "cold")
                    .values(check_priority="normal")
                )

    if rows:
        frozen_count = sum(1 for utp, _ in rows if utp.frozen)
        logger.info(
            "[enforce_author_limits] user=%s tier=%s limit=%d total=%d frozen=%d",
            user_id, new_tier, limit, len(rows), frozen_count,
        )


# ── Profile creation ─────────────────────────────────────────────

async def ensure_tracked_profile(
    db: AsyncSession,
    platform: str,
    username: str,
    niche: str | None = None,
    display_name: str | None = None,
    topics: list[str] | None = None,
) -> TrackedProfile | None:
    """Create or update a tracked profile. Called from orchestrator after reel parsing."""
    if not username or not platform:
        return None

    username = username.strip().lower()

    result = await db.execute(
        select(TrackedProfile).where(
            TrackedProfile.platform == platform,
            TrackedProfile.username == username,
        )
    )
    profile = result.scalar_one_or_none()

    if profile:
        # Update niche if it was previously empty
        if not profile.niche and niche:
            profile.niche = niche
        if not profile.display_name and display_name:
            profile.display_name = display_name
        # Merge topics (union of existing + new)
        if topics:
            existing = set(profile.topics or [])
            merged = list(existing | set(topics))
            if merged != list(existing):
                profile.topics = merged
        return profile

    # Build profile URL
    if platform == "instagram":
        profile_url = f"https://www.instagram.com/{username}/"
    elif platform == "youtube":
        profile_url = f"https://www.youtube.com/@{username}"
    else:
        profile_url = None

    profile = TrackedProfile(
        platform=platform,
        username=username,
        display_name=display_name or username,
        profile_url=profile_url,
        niche=niche,
        topics=topics or None,
    )
    db.add(profile)
    await db.flush()
    logger.info(f"[trends] Created tracked profile: {platform}/{username} (niche={niche})")
    return profile


# ── Profile scraping ─────────────────────────────────────────────

async def _scrape_instagram_profile(username: str) -> dict | None:
    """Scrape an Instagram profile using Apify Profile Scraper.

    Returns raw Apify response dict with profile metadata and recent posts.
    """
    try:
        items = await run_actor(
            actor_id=settings.apify_instagram_profile_actor,
            input_data={
                "usernames": [username],
            },
            timeout=120,
        )
        if items and len(items) > 0:
            return items[0]
        return None
    except Exception as e:
        logger.warning(f"[trends] Failed to scrape profile @{username}: {e}")
        return None


async def _scrape_instagram_profiles_batch(usernames: list[str]) -> list[dict]:
    """Scrape multiple Instagram profiles in a single Apify run."""
    if not usernames:
        return []

    try:
        items = await run_actor(
            actor_id=settings.apify_instagram_profile_actor,
            input_data={
                "usernames": usernames,
            },
            timeout=max(120, len(usernames) * 10),
        )
        return items if isinstance(items, list) else []
    except Exception as e:
        logger.error(f"[trends] Batch profile scrape failed for {len(usernames)} profiles: {e}")
        return []


def _extract_reels_from_profile(profile_data: dict) -> list[dict]:
    """Extract reel entries from Apify profile scraper response.

    Returns list of dicts with normalized fields:
    {shortcode, url, caption, thumbnail, published_at, duration, views, likes, comments}
    """
    reels: dict[str, dict] = {}  # keyed by shortcode to deduplicate
    posts = profile_data.get("latestPosts") or profile_data.get("posts") or []

    for post in posts:
        # Filter: only video content (reels)
        post_type = post.get("type", "").lower()
        is_video = post.get("isVideo", False) or post_type in ("video", "reel", "clip")
        if not is_video:
            continue

        shortcode = post.get("shortCode") or post.get("shortcode") or post.get("id")
        if not shortcode:
            continue

        # Apify sometimes returns duplicate posts — keep first occurrence
        if shortcode in reels:
            continue

        url = post.get("url") or f"https://www.instagram.com/reel/{shortcode}/"

        # Parse timestamp
        published_at = None
        ts = post.get("timestamp") or post.get("takenAt")
        if ts:
            try:
                if isinstance(ts, (int, float)):
                    published_at = datetime.utcfromtimestamp(ts)
                elif isinstance(ts, str):
                    published_at = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, OSError):
                pass

        reels[shortcode] = {
            "shortcode": shortcode,
            "url": url,
            "caption": post.get("caption") or post.get("text"),
            "thumbnail": post.get("displayUrl") or post.get("thumbnailUrl"),
            "published_at": published_at,
            "duration": post.get("videoDuration"),
            "views": _parse_metric(
                post.get("videoPlayCount")
                or post.get("videoViewCount")
                or post.get("playCount")
            ),
            "likes": _parse_metric(post.get("likesCount") or post.get("likes")),
            "comments": _parse_metric(post.get("commentsCount") or post.get("comments")),
        }

    return list(reels.values())


# ── X-factor calculation ─────────────────────────────────────────

def _calculate_median(values: list[int]) -> float:
    """Calculate median of a list of integers. Returns 0.0 if empty."""
    if not values:
        return 0.0
    return float(statistics.median(values))


def _calculate_x_factor(views: int | None, median_views: float) -> float | None:
    """Calculate X-factor = views / median. Returns None if insufficient data."""
    if views is None or median_views <= 0:
        return None
    return round(views / median_views, 2)


# ── Hot score (composite) ───────────────────────────────────────

def _calculate_velocity(reel) -> float | None:
    """Calculate views gained per hour since last check."""
    if reel.previous_views is None or reel.views_updated_at is None:
        return None
    hours = (datetime.utcnow() - reel.views_updated_at).total_seconds() / 3600
    if hours < 0.5:
        return None
    delta = max(0, (reel.views or 0) - reel.previous_views)
    return round(delta / hours, 1)


def _normalize_x_factor(x: float | None) -> float:
    """Map x_factor [2.0, 20.0+] → [0.0, 1.0] using log scale."""
    if x is None or x < X_FACTOR_THRESHOLD:
        return 0.0
    return min(1.0, math.log(x / X_FACTOR_THRESHOLD) / math.log(10))


def _normalize_velocity(velocity: float | None) -> float:
    """Map velocity → [0, 1]. None (first check) → 0.3 conservative."""
    if velocity is None:
        return 0.3
    if velocity <= 0:
        return 0.0
    return min(1.0, math.log10(max(1, velocity)) / 5.0)


def _normalize_engagement(likes: int | None, comments: int | None, views: int | None) -> float:
    """Map engagement rate (likes + 5×comments) / views → [0, 1] via log scale.

    1% → 0.30, 3% → 0.57, 5% → 0.72, 10%+ → 1.0.
    """
    v = views or 0
    if v <= 0:
        return 0.0
    rate = ((likes or 0) + (comments or 0) * 5) / v
    return min(1.0, math.log10(1 + rate * 100) / 2.0)


def _calculate_time_decay(published_at: datetime | None) -> float:
    """Exponential decay, half-life 36h. 0h→1.0, 36h→0.50, 3d→0.16, 7d→0.02."""
    if published_at is None:
        return 0.5
    age_hours = (datetime.utcnow() - published_at).total_seconds() / 3600
    if age_hours < 0:
        return 1.0
    return math.exp(-0.693 * age_hours / 36.0)


def calculate_hot_score(
    x_factor: float | None,
    views: int | None,
    velocity: float | None,
    published_at: datetime | None,
    likes: int | None = None,
    comments: int | None = None,
) -> float | None:
    """Composite hot score [0, 1]. None if below thresholds.

    Formula: (0.40×velocity + 0.35×x_factor + 0.25×engagement) × time_decay
    - Velocity (40%): real-time signal — "gaining views right now"
    - X-factor (35%): quality signal — "above author's average"
    - Engagement (25%): audience signal — "people react, not just views"
    - Time decay: multiplier with 36h half-life — old reels can't be "hot"
    """
    if x_factor is None or x_factor < X_FACTOR_THRESHOLD:
        return None
    if views is None or views < MIN_VIEWS_THRESHOLD:
        return None

    quality = (
        0.40 * _normalize_velocity(velocity)
        + 0.35 * _normalize_x_factor(x_factor)
        + 0.25 * _normalize_engagement(likes, comments, views)
    )
    decay = _calculate_time_decay(published_at)

    return round(quality * decay, 4)


# ── Thumbnail persistence ────────────────────────────────────────

async def _persist_thumbnail(reel_id: str, cdn_url: str) -> str | None:
    """Download thumbnail from CDN and save to our storage. Returns storage key or None."""
    key = f"thumbnails/{reel_id}.jpg"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(cdn_url)
            if resp.status_code != 200:
                return None
            await storage.write_file(key, resp.content)
            return key
    except Exception as e:
        logger.warning("[trends] Failed to persist thumbnail for %s: %s", reel_id, e)
        return None


async def _persist_thumbnails_batch(
    reels: list[ProfileReel], concurrency: int = 20, *, mark_failed: bool = False,
) -> int:
    """Download and persist thumbnails for a batch of reels. Returns count of successes.

    If mark_failed=True, sets thumbnail_key="" for failed downloads so they are
    not retried in subsequent backfill batches (prevents infinite loop).
    """
    if not reels:
        return 0

    sem = asyncio.Semaphore(concurrency)
    count = 0

    async def _download(reel: ProfileReel) -> None:
        nonlocal count
        async with sem:
            key = await _persist_thumbnail(reel.id, reel.thumbnail_url)
            if key:
                reel.thumbnail_key = key
                count += 1
            elif mark_failed:
                reel.thumbnail_key = ""

    await asyncio.gather(*[_download(r) for r in reels])
    return count


# ── Profile check logic ─────────────────────────────────────────

async def _process_profile_data(
    db: AsyncSession, profile: TrackedProfile, profile_data: dict,
    *, redis=None,
) -> int:
    """Process scraped data for a single profile. Returns count of new reels found."""
    # Update profile metadata
    profile.followers_count = _parse_metric(
        profile_data.get("followersCount") or profile_data.get("followers")
    )
    if profile_data.get("fullName"):
        profile.display_name = profile_data["fullName"]

    # Extract reels
    total_posts = len(profile_data.get("latestPosts") or profile_data.get("posts") or [])
    raw_reels = _extract_reels_from_profile(profile_data)
    logger.info(
        "[trends] @%s: %d posts from Apify, %d are video reels",
        profile.username, total_posts, len(raw_reels),
    )
    new_count = 0

    # Pre-fetch all existing reels for this profile (avoids N+1)
    existing_result = await db.execute(
        select(ProfileReel).where(ProfileReel.profile_id == profile.id)
    )
    existing_reels = existing_result.scalars().all()
    existing_reels_map: dict[str, ProfileReel] = {
        r.platform_reel_id: r for r in existing_reels
    }
    existing_url_map: dict[str, ProfileReel] = {
        r.url: r for r in existing_reels if r.url
    }

    # Check for URL collisions with other profiles
    incoming_urls = [r["url"] for r in raw_reels if r.get("url")]
    if incoming_urls:
        url_collision_result = await db.execute(
            select(ProfileReel.url).where(
                ProfileReel.url.in_(incoming_urls),
                ProfileReel.profile_id != profile.id,
            )
        )
        cross_profile_urls: set[str] = {row[0] for row in url_collision_result.all()}
    else:
        cross_profile_urls = set()

    all_touched_reels: list[ProfileReel] = []

    for reel_data in raw_reels:
        existing_reel = (
            existing_reels_map.get(reel_data["shortcode"])
            or existing_url_map.get(reel_data.get("url"))
        )

        if existing_reel:
            # Delta-tracking: calculate velocity BEFORE overwriting previous_views
            if reel_data["views"] is not None:
                if (
                    existing_reel.views is not None
                    and existing_reel.views_updated_at is not None
                ):
                    hours = (datetime.utcnow() - existing_reel.views_updated_at).total_seconds() / 3600
                    if hours >= 0.5:
                        delta = max(0, reel_data["views"] - existing_reel.views)
                        existing_reel.velocity = round(delta / hours, 1)
                # Now save tracking fields
                if existing_reel.views is not None:
                    existing_reel.previous_views = existing_reel.views
                    existing_reel.views_updated_at = datetime.utcnow()
                existing_reel.views = reel_data["views"]
            if reel_data["likes"] is not None:
                existing_reel.likes = reel_data["likes"]
            if reel_data["comments"] is not None:
                existing_reel.comments = reel_data["comments"]
            if reel_data["thumbnail"]:
                existing_reel.thumbnail_url = reel_data["thumbnail"]
            all_touched_reels.append(existing_reel)
        elif reel_data.get("url") in cross_profile_urls:
            # URL already exists under a different profile — skip to avoid unique violation
            continue
        else:
            # New reel
            new_reel = ProfileReel(
                profile_id=profile.id,
                platform_reel_id=reel_data["shortcode"],
                url=reel_data["url"],
                caption=reel_data["caption"],
                thumbnail_url=reel_data["thumbnail"],
                published_at=reel_data["published_at"],
                duration=reel_data["duration"],
                views=reel_data["views"],
                likes=reel_data["likes"],
                comments=reel_data["comments"],
            )
            # Per-reel niche classification from caption
            if reel_data.get("caption"):
                new_reel.niche = await _infer_reel_niche(
                    reel_data["caption"], profile.username
                )
            db.add(new_reel)
            all_touched_reels.append(new_reel)
            new_count += 1

    await db.flush()

    # Persist thumbnails to our storage (skip YouTube — stable URLs)
    if profile.platform != "youtube":
        needs_thumbnail = [
            r for r in all_touched_reels
            if r.thumbnail_url and not r.thumbnail_key
        ]
        if needs_thumbnail:
            saved = await _persist_thumbnails_batch(needs_thumbnail)
            if saved:
                await db.flush()
                logger.info("[trends] Persisted %d thumbnail(s) for @%s", saved, profile.username)

    # Link profile_reels to library_reels where URLs match (batch, no N+1)
    unlinked = await db.execute(
        select(ProfileReel).where(
            ProfileReel.profile_id == profile.id,
            ProfileReel.library_reel_id.is_(None),
        )
    )
    unlinked_reels = unlinked.scalars().all()
    if unlinked_reels:
        unlinked_urls = [pr.url for pr in unlinked_reels if pr.url]
        lib_result = await db.execute(
            select(LibraryReel.id, LibraryReel.url)
            .where(LibraryReel.url.in_(unlinked_urls))
        )
        lib_map = {row.url: row.id for row in lib_result.all()}
        for pr in unlinked_reels:
            lib_id = lib_map.get(pr.url)
            if lib_id:
                pr.library_reel_id = lib_id

    # Recalculate median and X-factors (re-fetch to include newly added reels)
    all_reels_result = await db.execute(
        select(ProfileReel).where(ProfileReel.profile_id == profile.id)
    )
    all_reels = all_reels_result.scalars().all()

    views_list = [r.views for r in all_reels if r.views is not None and r.views > 0]
    median_views = _calculate_median(views_list)

    profile.median_views = median_views
    profile.avg_views = sum(views_list) / len(views_list) if views_list else 0.0
    profile.total_reels = len(all_reels)

    # Set of reels already touched by scrape (velocity pre-calculated)
    all_touched_reels_set = set(id(r) for r in all_touched_reels)

    # Calculate X-factor, velocity, hot_score for each reel
    has_enough_data = len(views_list) >= MIN_REELS_FOR_XFACTOR
    cutoff = datetime.utcnow() - timedelta(days=TRENDING_MAX_AGE_DAYS)

    if not has_enough_data:
        logger.info(
            "[trends] @%s: not enough reels for X-factor (%d/%d), skipping scoring",
            profile.username, len(views_list), MIN_REELS_FOR_XFACTOR,
        )

    for reel in all_reels:
        if has_enough_data:
            reel.x_factor = _calculate_x_factor(reel.views, median_views)
            # velocity already calculated in the update loop above;
            # only calculate here for reels not touched by scrape (e.g. old reels)
            if reel.velocity is None and id(reel) not in all_touched_reels_set:
                reel.velocity = _calculate_velocity(reel)
            reel.hot_score = calculate_hot_score(
                reel.x_factor, reel.views, reel.velocity, reel.published_at,
                reel.likes, reel.comments,
            )
            was_trending = reel.is_trending
            reel.is_trending = (
                reel.hot_score is not None
                and reel.published_at is not None
                and reel.published_at >= cutoff
            )
            if reel.is_trending and not was_trending:
                reel.trending_since = datetime.utcnow()
            elif not reel.is_trending and reel.trending_since is not None:
                reel.trending_since = None
            if reel.is_trending:
                logger.debug(
                    "[trends] @%s reel %s: x=%.1f vel=%s hot=%.4f TRENDING",
                    profile.username, reel.platform_reel_id,
                    reel.x_factor or 0, reel.velocity, reel.hot_score or 0,
                )
                await _publish_monitoring_event(
                    redis, "trend_found",
                    profile_username=profile.username, platform=profile.platform,
                    reel_url=reel.url, x_factor=round(reel.x_factor or 0, 1),
                    hot_score=round(reel.hot_score or 0, 3),
                    views=reel.views,
                )
                await _log_activity(
                    redis, "trend_found",
                    profile_username=profile.username, platform=profile.platform,
                    details={"reel_url": reel.url,
                             "x_factor": round(reel.x_factor or 0, 1),
                             "hot_score": round(reel.hot_score or 0, 3),
                             "views": reel.views},
                )
                await _increment_hourly(redis, "trends")
        else:
            reel.x_factor = None
            reel.velocity = None
            reel.hot_score = None
            reel.is_trending = False
            reel.trending_since = None

    # Update check priority + cold counter
    trending_count = sum(1 for r in all_reels if r.is_trending)
    hot_cutoff = datetime.utcnow() - timedelta(days=3)
    has_hot = any(
        r.is_trending and r.published_at and r.published_at >= hot_cutoff
        for r in all_reels
    )
    if trending_count > 0:
        profile.consecutive_cold_checks = 0
        profile.check_priority = "high" if has_hot else "normal"
    else:
        profile.consecutive_cold_checks = (profile.consecutive_cold_checks or 0) + 1
        if profile.consecutive_cold_checks >= COLD_CHECK_LIMIT:
            profile.check_priority = "cold"
        else:
            profile.check_priority = "normal"

    # Backfill per-reel niche for existing reels that don't have one yet
    reels_without_niche = [r for r in all_reels if r.niche is None and r.caption]
    if reels_without_niche:
        batch = reels_without_niche[:20]  # cap to avoid too many API calls
        niche_results = await asyncio.gather(
            *[_infer_reel_niche(r.caption, profile.username) for r in batch],
            return_exceptions=True,
        )
        for reel, result in zip(batch, niche_results):
            if isinstance(result, str):
                reel.niche = result

    # Derive profile-level niche as the most common niche across all reels
    reel_niches = [r.niche for r in all_reels if r.niche and r.niche in VALID_NICHES]
    if reel_niches:
        profile.niche = max(set(reel_niches), key=reel_niches.count)
    elif (profile.niche is None or profile.niche not in VALID_NICHES) and all_reels:
        # Fallback: infer from captions if no reel niches exist yet
        captions = " | ".join(r.caption or "" for r in all_reels[:10] if r.caption)
        if captions:
            profile.niche = await _infer_niche_from_captions(captions)

    # Infer topics via Haiku if missing
    if not profile.topics and all_reels:
        captions_text = " | ".join(r.caption or "" for r in all_reels[:10] if r.caption)
        if captions_text:
            inferred_topics = await _infer_topics_from_captions(captions_text)
            if inferred_topics:
                profile.topics = inferred_topics
                logger.info(f"[trends] Inferred topics for @{profile.username}: {inferred_topics}")

    profile.last_checked_at = datetime.utcnow()
    logger.info(
        f"[trends] Checked @{profile.username}: "
        f"{len(all_reels)} reels, {new_count} new, "
        f"median={median_views:.0f}, trending={sum(1 for r in all_reels if r.is_trending)}"
    )

    # ER drop alerts: snapshot + detection (best-effort)
    try:
        from app.services.er_alerts import check_and_alert_er_drops
        await check_and_alert_er_drops(db, profile, all_reels, redis=redis)
    except Exception:
        logger.debug("[trends] ER alert check failed for @%s", profile.username, exc_info=True)

    return new_count


async def check_profile(db: AsyncSession, profile: TrackedProfile) -> int:
    """Check a single profile for new/updated reels. Returns count of new reels found."""
    if profile.platform != "instagram":
        # Mark as checked so non-instagram profiles don't block Pass 0 forever
        profile.last_checked_at = datetime.utcnow()
        profile.check_priority = "cold"
        return 0

    profile_data = await _scrape_instagram_profile(profile.username)
    if profile_data is None:
        profile.consecutive_scrape_failures = (profile.consecutive_scrape_failures or 0) + 1
        if profile.consecutive_scrape_failures >= 3:
            logger.warning("[trends] Deactivating @%s after %d consecutive failures", profile.username, profile.consecutive_scrape_failures)
            profile.is_active = False
        else:
            logger.info("[trends] No data for @%s (failure %d/3)", profile.username, profile.consecutive_scrape_failures)
        profile.last_checked_at = datetime.utcnow()
        return 0

    profile.consecutive_scrape_failures = 0
    return await _process_profile_data(db, profile, profile_data)


async def _scrape_profiles_in_chunks(usernames: list[str], chunk_size: int = 100) -> list[dict]:
    """Scrape profiles in chunks to stay within Apify limits."""
    all_items = []
    for i in range(0, len(usernames), chunk_size):
        chunk = usernames[i : i + chunk_size]
        items = await _scrape_instagram_profiles_batch(chunk)
        all_items.extend(items)
    return all_items


async def check_stale_profiles(db: AsyncSession, redis=None) -> int:
    """Check stale profiles with four-pass prioritization.

    Pass 0: new profiles (never checked) — up to 10, immediate first scan.
    Pass 1: high-priority profiles (hot reels) — check every 4h, up to 40.
    Pass 2: normal profiles — check every 12h, remaining budget.
    Pass 3: cold profiles (never trending) — check every 48h, remaining budget.

    Args:
        redis: Optional Redis connection for publishing monitoring events
              to the admin trend-watching dashboard.
    """
    now = datetime.utcnow()
    BATCH_LIMIT = 100

    # Pass 0: brand-new profiles (never checked) — first scan ASAP
    new_result = await db.execute(
        select(TrackedProfile)
        .where(
            TrackedProfile.is_active == True,  # noqa: E712
            TrackedProfile.last_checked_at.is_(None),
        )
        .order_by(TrackedProfile.created_at.asc())
        .limit(10)
    )
    new_profiles = new_result.scalars().all()

    # Pass 1: high-priority (not checked > 4h)
    high_cutoff = now - timedelta(hours=4)
    high_limit = min(40, BATCH_LIMIT - len(new_profiles))
    high_result = await db.execute(
        select(TrackedProfile)
        .where(
            TrackedProfile.is_active == True,  # noqa: E712
            TrackedProfile.check_priority == "high",
            TrackedProfile.last_checked_at.isnot(None),
            TrackedProfile.last_checked_at < high_cutoff,
        )
        .order_by(TrackedProfile.last_checked_at.asc())
        .limit(high_limit)
    )
    high_profiles = high_result.scalars().all()

    # Pass 2: normal (not checked > 12h)
    normal_limit = BATCH_LIMIT - len(new_profiles) - len(high_profiles)
    normal_cutoff = now - timedelta(hours=12)
    normal_result = await db.execute(
        select(TrackedProfile)
        .where(
            TrackedProfile.is_active == True,  # noqa: E712
            TrackedProfile.check_priority == "normal",
            TrackedProfile.last_checked_at.isnot(None),
            TrackedProfile.last_checked_at < normal_cutoff,
        )
        .order_by(TrackedProfile.last_checked_at.asc())
        .limit(normal_limit)
    )
    normal_profiles = normal_result.scalars().all()

    # Pass 3: cold profiles (not checked > 48h), remaining budget
    cold_limit = BATCH_LIMIT - len(new_profiles) - len(high_profiles) - len(normal_profiles)
    cold_profiles = []
    if cold_limit > 0:
        cold_cutoff = now - timedelta(hours=48)
        cold_result = await db.execute(
            select(TrackedProfile)
            .where(
                TrackedProfile.is_active == True,  # noqa: E712
                TrackedProfile.check_priority == "cold",
                TrackedProfile.last_checked_at.isnot(None),
                TrackedProfile.last_checked_at < cold_cutoff,
            )
            .order_by(TrackedProfile.last_checked_at.asc())
            .limit(cold_limit)
        )
        cold_profiles = cold_result.scalars().all()

    profiles = new_profiles + high_profiles + normal_profiles + cold_profiles
    if not profiles:
        return 0

    logger.info(
        "[trends] Checking %d stale profiles "
        "(%d new, %d high, %d normal, %d cold)...",
        len(profiles), len(new_profiles), len(high_profiles),
        len(normal_profiles), len(cold_profiles),
    )
    total_new = 0

    # Group by platform
    ig_profiles = [p for p in profiles if p.platform == "instagram"]
    other_profiles = [p for p in profiles if p.platform != "instagram"]

    # Batch scrape Instagram profiles (with chunking for >100)
    ig_data_map: dict[str, dict] = {}
    if ig_profiles:
        usernames = [p.username for p in ig_profiles]
        logger.info(f"[trends] Batch scraping {len(usernames)} Instagram profiles...")
        await _publish_monitoring_event(
            redis, "batch_start",
            profile_count=len(usernames),
            priorities={"new": len(new_profiles), "high": len(high_profiles),
                        "normal": len(normal_profiles), "cold": len(cold_profiles)},
        )
        # Mark all profiles as "scraping" in Redis
        if redis is not None:
            for p in ig_profiles:
                try:
                    await redis.set(
                        f"trend:scraping:{p.id}",
                        _json.dumps({"username": p.username, "platform": "instagram",
                                     "started_at": datetime.utcnow().isoformat() + "Z"}),
                        ex=600,
                    )
                    await _publish_monitoring_event(
                        redis, "profile_status",
                        profile_id=str(p.id), status="scraping",
                        username=p.username, platform="instagram",
                    )
                except Exception:
                    pass
        batch_results = await _scrape_profiles_in_chunks(usernames)

        for item in batch_results:
            uname = (item.get("username") or item.get("userName") or "").strip().lower()
            if uname:
                ig_data_map[uname] = item

        # Clear all scraping keys — profiles move to analyzing individually
        if redis is not None:
            for p in ig_profiles:
                try:
                    await redis.delete(f"trend:scraping:{p.id}")
                except Exception:
                    pass

        logger.info(f"[trends] Batch scrape returned data for {len(ig_data_map)} profiles")

        # Circuit breaker: skip IG processing if >30% of profiles got no data
        missing = len(ig_profiles) - len(ig_data_map)
        failure_ratio = missing / len(ig_profiles)
        if failure_ratio > 0.30:
            logger.warning(
                "[trends] Circuit breaker: %d/%d profiles missing data (%.0f%%), skipping IG processing",
                missing, len(ig_profiles), failure_ratio * 100,
            )
            await _publish_monitoring_event(
                redis, "circuit_breaker",
                total=len(ig_profiles), missing=missing,
                ratio=round(failure_ratio, 2),
            )
            ig_profiles = []  # skip IG processing, continue with other_profiles + recovery

    # Cache profile metadata before processing loop —
    # prevents lazy-load errors if a savepoint rollback expires ORM state.
    profile_meta = {p.id: (str(p.id), p.username) for p in ig_profiles}

    # Process each Instagram profile using savepoints so that an error
    # on one profile does NOT invalidate the session for the rest.
    for profile in ig_profiles:
        profile_id_str, username = profile_meta[profile.id]
        try:
            async with db.begin_nested():
                profile_data = ig_data_map.get(username)
                if profile_data is None:
                    profile.consecutive_scrape_failures = (profile.consecutive_scrape_failures or 0) + 1
                    if profile.consecutive_scrape_failures >= 3:
                        profile.is_active = False
                        logger.warning(
                            "[trends] Deactivating @%s after %d consecutive scrape failures",
                            username, profile.consecutive_scrape_failures,
                        )
                    else:
                        logger.info(
                            "[trends] No data for @%s (failure %d/3), will retry next cycle",
                            username, profile.consecutive_scrape_failures,
                        )
                    profile.last_checked_at = datetime.utcnow()
                    await _publish_monitoring_event(
                        redis, "profile_status",
                        profile_id=profile_id_str, status="failed",
                        username=username, error="no_data_from_apify",
                    )
                    await _log_activity(
                        redis, "error",
                        profile_username=username, platform="instagram",
                        details={"error": "no_data_from_apify",
                                 "failures": profile.consecutive_scrape_failures},
                    )
                    await _increment_hourly(redis, "errors")
                else:
                    profile.consecutive_scrape_failures = 0
                    # Mark as "analyzing" in Redis
                    if redis is not None:
                        try:
                            await redis.set(
                                f"trend:analyzing:{profile_id_str}",
                                _json.dumps({"username": username, "platform": "instagram",
                                             "started_at": datetime.utcnow().isoformat() + "Z"}),
                                ex=600,
                            )
                        except Exception:
                            pass
                    await _publish_monitoring_event(
                        redis, "profile_status",
                        profile_id=profile_id_str, status="analyzing",
                        username=username, platform="instagram",
                    )
                    new_count = await _process_profile_data(db, profile, profile_data, redis=redis)
                    total_new += new_count
                    # Clear "analyzing" key and publish completed
                    if redis is not None:
                        try:
                            await redis.delete(f"trend:analyzing:{profile_id_str}")
                        except Exception:
                            pass
                    trending_cnt_result = await db.execute(
                        select(func.count()).select_from(ProfileReel).where(
                            ProfileReel.profile_id == profile.id,
                            ProfileReel.is_trending == True,  # noqa: E712
                        )
                    )
                    trending_cnt = trending_cnt_result.scalar() or 0
                    await _publish_monitoring_event(
                        redis, "profile_status",
                        profile_id=profile_id_str, status="completed",
                        username=username, platform="instagram",
                        details={"new_reels": new_count, "trending_count": trending_cnt,
                                 "check_priority": profile.check_priority},
                    )
                    await _log_activity(
                        redis, "check_complete",
                        profile_username=username, platform="instagram",
                        details={"new_reels": new_count, "trending_count": trending_cnt,
                                 "check_priority": profile.check_priority},
                    )
                    await _increment_hourly(redis, "checks")
            # Savepoint committed — flush to outer transaction
            await db.commit()
        except Exception as e:
            # Savepoint already rolled back by begin_nested() context manager.
            # Outer session remains valid for the next profile.
            logger.error(f"[trends] Error processing @{username}: {e}")
            # Clean up Redis state on error
            if redis is not None:
                try:
                    await redis.delete(f"trend:analyzing:{profile_id_str}")
                except Exception:
                    pass
            await _publish_monitoring_event(
                redis, "profile_status",
                profile_id=profile_id_str, status="failed",
                username=username, error=str(e)[:200],
            )
            await _log_activity(
                redis, "error",
                profile_username=username, platform="instagram",
                details={"error": str(e)[:200]},
            )
            await _increment_hourly(redis, "errors")
            # Re-fetch profile from DB to get fresh ORM state after rollback
            try:
                refreshed = await db.get(TrackedProfile, profile.id)
                if refreshed:
                    idx = ig_profiles.index(profile)
                    ig_profiles[idx] = refreshed
            except Exception:
                pass

    # Process non-Instagram profiles individually (YouTube TBD)
    for profile in other_profiles:
        username = profile.username
        try:
            async with db.begin_nested():
                new_count = await check_profile(db, profile)
                total_new += new_count
            await db.commit()
        except Exception as e:
            logger.error(f"[trends] Error checking @{username}: {e}")

    # Recovery pass: retry deactivated profiles once a week (up to 5)
    recovery_cutoff = now - timedelta(days=7)
    recovery_result = await db.execute(
        select(TrackedProfile)
        .where(
            TrackedProfile.is_active == False,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            (TrackedProfile.last_checked_at.is_(None)) | (TrackedProfile.last_checked_at < recovery_cutoff),
        )
        .order_by(TrackedProfile.last_checked_at.asc().nullsfirst())
        .limit(5)
    )
    recovery_profiles = recovery_result.scalars().all()
    if recovery_profiles:
        logger.info(f"[trends] Retrying {len(recovery_profiles)} deactivated profiles...")
        recovery_usernames = [p.username for p in recovery_profiles if p.platform == "instagram"]
        if recovery_usernames:
            recovery_data = await _scrape_instagram_profiles_batch(recovery_usernames)
            recovery_map = {
                (item.get("username") or item.get("userName") or "").strip().lower(): item
                for item in recovery_data
            }
            for profile in recovery_profiles:
                username = profile.username
                try:
                    async with db.begin_nested():
                        data = recovery_map.get(username)
                        if data:
                            profile.is_active = True
                            profile.consecutive_scrape_failures = 0
                            new_count = await _process_profile_data(db, profile, data)
                            total_new += new_count
                            logger.info(f"[trends] Reactivated @{username}")
                        else:
                            profile.last_checked_at = datetime.utcnow()
                    await db.commit()
                except Exception as e:
                    logger.error(f"[trends] Recovery error for @{username}: {e}")

    logger.info(f"[trends] Done. {total_new} new reels across {len(profiles)} profiles.")
    return total_new


# ── Thumbnail backfill ────────────────────────────────────────────

async def backfill_thumbnails(db: AsyncSession, batch_size: int = 50) -> int:
    """Download and persist thumbnails for existing reels that lack thumbnail_key.

    Skips YouTube reels (stable URLs that never expire).
    Returns total number of thumbnails persisted.
    """
    total = 0
    while True:
        result = await db.execute(
            select(ProfileReel)
            .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
            .where(
                ProfileReel.thumbnail_url.isnot(None),
                ProfileReel.thumbnail_key.is_(None),
                TrackedProfile.platform != "youtube",
            )
            .limit(batch_size)
        )
        reels = result.scalars().all()
        if not reels:
            break

        saved = await _persist_thumbnails_batch(reels, mark_failed=True)
        total += saved
        await db.commit()
        logger.info("[trends] Backfill batch: %d/%d thumbnails persisted", saved, len(reels))

    logger.info("[trends] Thumbnail backfill complete: %d total", total)
    return total


async def repair_thumbnails(db: AsyncSession, include_orphans: bool = False) -> dict:
    """Re-scrape profiles to refresh expired CDN URLs, then persist thumbnails.

    Phase 1: Batch re-scrape Instagram profiles that have reels without thumbnail_key.
             This refreshes thumbnail_url to valid CDN links.
    Phase 2: Run backfill to download fresh CDN URLs into persistent storage.
    Phase 3 (if include_orphans): Scrape individual reels that are too old to
             appear in profile feeds.

    Returns stats dict.
    """
    from sqlalchemy import distinct

    # ── Phase 1: find profiles needing thumbnail repair ──────────
    result = await db.execute(
        select(distinct(ProfileReel.profile_id))
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.thumbnail_key.is_(None),
            TrackedProfile.platform == "instagram",
            TrackedProfile.is_active == True,  # noqa: E712
        )
    )
    profile_ids = [row[0] for row in result.all()]

    if not profile_ids:
        logger.info("[repair] No profiles need thumbnail repair")
        backfilled = await backfill_thumbnails(db)
        return {"profiles_checked": 0, "thumbnails_fixed": backfilled, "still_broken": 0}

    # Load profiles
    profiles_result = await db.execute(
        select(TrackedProfile).where(TrackedProfile.id.in_(profile_ids))
    )
    profiles = profiles_result.scalars().all()
    logger.info("[repair] Phase 1: re-scraping %d profiles to refresh CDN URLs...", len(profiles))

    # Batch scrape and process
    usernames = [p.username for p in profiles]
    batch_data = await _scrape_profiles_in_chunks(usernames)

    ig_data_map: dict[str, dict] = {}
    for item in batch_data:
        uname = (item.get("username") or item.get("userName") or "").strip().lower()
        if uname:
            ig_data_map[uname] = item

    profiles_checked = 0
    for profile in profiles:
        profile_data = ig_data_map.get(profile.username)
        if profile_data is None:
            logger.warning("[repair] No data for @%s, skipping", profile.username)
            continue
        try:
            await _process_profile_data(db, profile, profile_data)
            profiles_checked += 1
            await db.commit()
        except Exception as e:
            logger.error("[repair] Error processing @%s: %s", profile.username, e)
            await db.rollback()

    logger.info("[repair] Phase 1 done: %d/%d profiles refreshed", profiles_checked, len(profiles))

    # ── Phase 2: persist fresh thumbnails ────────────────────────
    logger.info("[repair] Phase 2: persisting thumbnails...")
    backfilled = await backfill_thumbnails(db)
    logger.info("[repair] Phase 2 done: %d thumbnails persisted", backfilled)

    # ── Phase 3 (optional): scrape orphan reels individually ─────
    orphan_fixed = 0
    if include_orphans:
        from app.services.scraper._platform import detect_platform, normalize_url
        from app.services.scraper import _get_scraper

        orphan_result = await db.execute(
            select(ProfileReel)
            .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
            .where(
                ProfileReel.thumbnail_key.is_(None),
                TrackedProfile.platform != "youtube",
            )
            .limit(200)
        )
        orphans = orphan_result.scalars().all()

        if orphans:
            logger.info("[repair] Phase 3: scraping %d orphan reels individually...", len(orphans))
            sem = asyncio.Semaphore(5)

            async def _fix_orphan(reel: ProfileReel) -> bool:
                async with sem:
                    try:
                        url = normalize_url(reel.url)
                        platform = detect_platform(url)
                        scraper = _get_scraper(platform)
                        sr = await scraper.scrape(url)
                        if sr.thumbnail:
                            reel.thumbnail_url = sr.thumbnail
                            key = await _persist_thumbnail(reel.id, sr.thumbnail)
                            if key:
                                reel.thumbnail_key = key
                                return True
                    except Exception as e:
                        logger.warning("[repair] Orphan scrape failed for %s: %s", reel.id, e)
                    return False

            results = await asyncio.gather(*[_fix_orphan(r) for r in orphans])
            orphan_fixed = sum(1 for r in results if r)
            await db.commit()
            logger.info("[repair] Phase 3 done: %d/%d orphans fixed", orphan_fixed, len(orphans))

    # ── Count remaining broken ───────────────────────────────────
    still_broken_result = await db.execute(
        select(func.count())
        .select_from(ProfileReel)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.thumbnail_key.is_(None),
            TrackedProfile.platform != "youtube",
        )
    )
    still_broken = still_broken_result.scalar() or 0

    stats = {
        "profiles_checked": profiles_checked,
        "thumbnails_fixed": backfilled + orphan_fixed,
        "still_broken": still_broken,
    }
    logger.info("[repair] Thumbnail repair complete: %s", stats)
    return stats


# ── Niche inference ──────────────────────────────────────────────

_NICHE_CLASSIFICATION_PROMPT = """\
Classify this creator into ONE niche based on their recent reel captions.

NICHE DEFINITIONS (choose the BEST fit):
{niche_list}

{rules}
- Respond with EXACTLY one niche slug from the list above, nothing else.

Captions:
{captions}"""


async def _infer_niche_from_captions(captions: str) -> str | None:
    """Classify creator niche via Haiku from multiple captions. Fallback: GPT-5.4."""
    prompt_text = _NICHE_CLASSIFICATION_PROMPT.format(
        niche_list=niche_prompt_detailed(),
        rules=DISAMBIGUATION_RULES,
        captions=captions[:3000],
    )
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=10.0)
        response = await client.messages.create(
            model=settings.light_text_model,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt_text}],
        )
        await _track_ai_usage(response.usage.input_tokens + response.usage.output_tokens)
        niche = response.content[0].text.strip().lower()
        return niche if niche in VALID_NICHES else "other"
    except Exception as e:
        logger.warning(f"[trends] Claude niche inference failed ({e}), trying GPT fallback")
    # ── GPT-5.4 fallback ──
    try:
        from app.core.openai_client import get_openai_client
        oai = get_openai_client()
        resp = await oai.chat.completions.create(
            model=settings.fallback_text_model,
            messages=[{"role": "user", "content": prompt_text}],
            max_completion_tokens=20,
        )
        niche = resp.choices[0].message.content.strip().lower()
        return niche if niche in VALID_NICHES else "other"
    except Exception as e2:
        logger.warning(f"[trends] GPT niche fallback also failed: {e2}")
        return None


_REEL_NICHE_PROMPT = """\
Classify this single reel into ONE niche based on its caption.

NICHE DEFINITIONS:
{niche_list}

{rules}
- Respond with EXACTLY one niche slug, nothing else.

Author: @{author}
Caption:
{caption}"""


async def _infer_reel_niche(caption: str, author: str = "") -> str | None:
    """Classify a single reel's niche via Haiku. Fallback: GPT-5.4."""
    prompt_text = _REEL_NICHE_PROMPT.format(
        niche_list=niche_prompt_detailed(),
        rules=DISAMBIGUATION_RULES,
        author=author,
        caption=caption[:2000],
    )
    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=10.0)
        response = await client.messages.create(
            model=settings.light_text_model,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt_text}],
        )
        await _track_ai_usage(response.usage.input_tokens + response.usage.output_tokens)
        niche = response.content[0].text.strip().lower()
        return niche if niche in VALID_NICHES else "other"
    except Exception as e:
        logger.warning(f"[trends] Claude reel niche failed ({e}), trying GPT fallback")
    # ── GPT-5.4 fallback ──
    try:
        from app.core.openai_client import get_openai_client
        oai = get_openai_client()
        resp = await oai.chat.completions.create(
            model=settings.fallback_text_model,
            messages=[{"role": "user", "content": prompt_text}],
            max_completion_tokens=20,
        )
        niche = resp.choices[0].message.content.strip().lower()
        return niche if niche in VALID_NICHES else "other"
    except Exception as e2:
        logger.warning(f"[trends] GPT reel niche fallback also failed: {e2}")
        return None


_TOPIC_EXTRACTION_PROMPT = """\
Extract 5-10 specific topic tags from these reel captions.

Return ONLY a JSON array of lowercase hyphenated tags.
Examples: ["ai-tools", "chatgpt", "automation", "no-code", "saas"]

Focus on specific, granular topics - NOT broad categories.
Bad: ["business", "tech"] - too broad
Good: ["ai-agents", "prompt-engineering", "cursor-ide", "vibe-coding"]

Captions:
{captions}"""


async def _infer_topics_from_captions(captions: str) -> list[str] | None:
    """Extract topic tags from captions via Haiku. Fallback: GPT-5.4."""
    import json as json_mod
    prompt_text = _TOPIC_EXTRACTION_PROMPT.format(captions=captions[:3000])

    def _parse_topics(raw: str) -> list[str] | None:
        topics = json_mod.loads(raw.strip())
        if isinstance(topics, list) and all(isinstance(t, str) for t in topics):
            return [t.lower().strip() for t in topics[:10]]
        return None

    try:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=15.0)
        response = await client.messages.create(
            model=settings.light_text_model,
            max_tokens=150,
            messages=[{"role": "user", "content": prompt_text}],
        )
        await _track_ai_usage(response.usage.input_tokens + response.usage.output_tokens)
        return _parse_topics(response.content[0].text)
    except Exception as e:
        logger.warning(f"[trends] Claude topic extraction failed ({e}), trying GPT fallback")
    # ── GPT-5.4 fallback ──
    try:
        from app.core.openai_client import get_openai_client
        oai = get_openai_client()
        resp = await oai.chat.completions.create(
            model=settings.fallback_text_model,
            messages=[{"role": "user", "content": prompt_text}],
            max_completion_tokens=150,
        )
        return _parse_topics(resp.choices[0].message.content)
    except Exception as e2:
        logger.warning(f"[trends] GPT topic fallback also failed: {e2}")
        return None
