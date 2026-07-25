"""Content Radar — push notifications for trending reels matching user niches.

Detects newly trending reels (is_trending=True, radar_notified_at IS NULL),
matches them against user interests/niches/tracked authors, and sends
Telegram notifications. Zero extra cost: no scripts are generated upfront.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.trends import ProfileReel, TrackedProfile, UserTrackedProfile
from app.models.user import User, UserSettings
from app.schemas.profile import UserProfile
from app.services.telegram import send_telegram_message, send_telegram_photo

logger = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_RADAR_MODE = "instant"
DEFAULT_MIN_X_FACTOR = 3.0
DEFAULT_QUIET_HOURS = True

# ── Limits ────────────────────────────────────────────────────────────
TELEGRAM_RATE_LIMIT = 20        # sleep after N messages (Telegram limit: 30/sec)
MAX_PER_USER_PER_TICK = 3       # anti-spam: max notifications per user per 10-min tick
MAX_REELS_PER_TICK = 50         # max reels to process in one radar tick


# ── Data structures ───────────────────────────────────────────────────

@dataclass
class RadarUser:
    user_id: str
    telegram_user_id: str
    niches: list[str]
    interests: list[str]
    mode: str                                   # "instant" | "digest" | "both"
    min_x_factor: float
    quiet_hours: bool
    tracked_profile_ids: set[str] = field(default_factory=set)


# ── Query helpers ─────────────────────────────────────────────────────

async def get_unnotified_trending_reels(
    db: AsyncSession, limit: int = MAX_REELS_PER_TICK,
) -> list[tuple[ProfileReel, TrackedProfile]]:
    """Fetch trending reels that haven't been sent via radar yet."""
    result = await db.execute(
        select(ProfileReel, TrackedProfile)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.is_hidden == False,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            ProfileReel.radar_notified_at.is_(None),
            ProfileReel.hot_score.isnot(None),
        )
        .order_by(ProfileReel.hot_score.desc().nullslast())
        .limit(limit)
    )
    return list(result.all())


def _parse_profile(user_settings: UserSettings | None) -> UserProfile | None:
    if not user_settings or not user_settings.profile_json:
        return None
    try:
        return UserProfile(**user_settings.profile_json)
    except Exception:
        logger.warning("Failed to parse profile_json for user %s", user_settings.user_id)
        return None


async def get_radar_eligible_users(db: AsyncSession) -> list[RadarUser]:
    """Load all users eligible for radar notifications with their preferences."""
    result = await db.execute(
        select(User, UserSettings)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.telegram_user_id.isnot(None),
            User.is_anonymous == False,  # noqa: E712
        )
    )

    users: list[RadarUser] = []
    for user, user_settings in result.all():
        profile = _parse_profile(user_settings)

        # Skip if radar is explicitly disabled
        if profile and profile.radar_enabled is False:
            continue

        niches: list[str] = []
        interests: list[str] = []
        if profile:
            niches = profile.radar_niches or profile.niches or []
            interests = profile.interests or []

        mode = (profile.radar_mode if profile and profile.radar_mode else DEFAULT_RADAR_MODE)
        min_x = (profile.radar_min_x_factor if profile and profile.radar_min_x_factor else DEFAULT_MIN_X_FACTOR)
        quiet = (profile.radar_quiet_hours if profile and profile.radar_quiet_hours is not None else DEFAULT_QUIET_HOURS)

        users.append(RadarUser(
            user_id=user.id,
            telegram_user_id=user.telegram_user_id,
            niches=niches,
            interests=interests,
            mode=mode,
            min_x_factor=min_x,
            quiet_hours=quiet,
        ))

    # Batch-load tracked profile IDs for all users (N+1 prevention)
    if users:
        user_ids = [u.user_id for u in users]
        tp_result = await db.execute(
            select(UserTrackedProfile.user_id, UserTrackedProfile.profile_id)
            .where(UserTrackedProfile.user_id.in_(user_ids))
        )
        user_profiles_map: dict[str, set[str]] = {}
        for uid, pid in tp_result.all():
            user_profiles_map.setdefault(uid, set()).add(pid)
        for u in users:
            u.tracked_profile_ids = user_profiles_map.get(u.user_id, set())

    return users


# ── Matching ──────────────────────────────────────────────────────────

def _match_reason(
    user: RadarUser,
    profile: TrackedProfile,
    reel: ProfileReel | None = None,
) -> str | None:
    """Return match reason string or None if no match.

    Matching tiers (cumulative):
      1. User tracks this specific author (My Authors) -> always match
      2. Topic overlap (user interests vs profile.topics) -> match if overlap >= 1
      3. Niche match (user niches vs reel.niche or profile.niche) -> match
    """
    # Tier 1: user tracks this specific author
    if profile.id in user.tracked_profile_ids:
        return "author"

    # Tier 2: topic overlap
    profile_topics = profile.topics or []
    if user.interests and profile_topics:
        overlap = set(user.interests) & set(profile_topics)
        if overlap:
            return f"topic({next(iter(overlap))})"

    # Tier 3: niche match — prefer per-reel niche, fall back to profile niche
    reel_niche = reel.niche if reel and reel.niche else None
    effective_niche = reel_niche or profile.niche
    if user.niches and effective_niche and effective_niche in user.niches:
        return f"niche({effective_niche})"

    return None


# ── Relevance scoring ────────────────────────────────────────────────

# Minimum relevance score to send a notification (filters noise).
MIN_RELEVANCE_SCORE = 0.25

_MATCH_QUALITY: dict[str, float] = {
    "author": 1.0,
    "topic": 0.7,
    "niche": 0.5,
}


def _relevance_score(
    reel: ProfileReel,
    match_reason: str,
) -> float:
    """Score how valuable this reel is for a matched user [0, 1].

    Components:
      - hot_score (40%): composite trending signal
      - match_quality (30%): how strong the user<>reel connection is
      - x_factor_norm (30%): how much this reel overperforms
    """
    import math

    # hot_score component (already [0, 1])
    hot = reel.hot_score or 0.0

    # match quality component
    match_type = match_reason.split("(")[0]  # "niche(ai)" -> "niche"
    quality = _MATCH_QUALITY.get(match_type, 0.3)

    # x_factor normalized: x=3 -> 0.18, x=5 -> 0.40, x=10 -> 0.70, x=20+ -> 1.0
    x = reel.x_factor or 2.0
    x_norm = min(1.0, math.log(max(x, 2.0) / 2.0) / math.log(10))

    return 0.40 * hot + 0.30 * quality + 0.30 * x_norm


def match_reel_to_users(
    reel: ProfileReel,
    profile: TrackedProfile,
    users: list[RadarUser],
) -> list[tuple[RadarUser, str]]:
    """Return users who should be notified about this reel.

    Returns list of (RadarUser, match_reason) tuples.
    """
    matched: list[tuple[RadarUser, str]] = []
    now = datetime.utcnow()
    skipped_digest = 0
    skipped_x = 0
    skipped_quiet = 0

    for user in users:
        # Skip digest-only users (handled in daily digest)
        if user.mode == "digest":
            skipped_digest += 1
            continue

        # Check X-factor threshold
        if (reel.x_factor or 0) < user.min_x_factor:
            skipped_x += 1
            continue

        # Check quiet hours (22:00-08:00 UTC = 01:00-11:00 MSK)
        if user.quiet_hours and (now.hour >= 22 or now.hour < 8):
            skipped_quiet += 1
            continue

        reason = _match_reason(user, profile, reel)
        if not reason:
            continue

        # Relevance filter: skip low-value matches (tracked authors always pass)
        if reason != "author":
            score = _relevance_score(reel, reason)
            if score < MIN_RELEVANCE_SCORE:
                continue

        matched.append((user, reason))

    if matched or skipped_digest or skipped_x or skipped_quiet:
        logger.debug(
            "[radar] Reel %s (@%s): matched=%d, skipped(digest=%d, x_factor=%d, quiet=%d)",
            reel.platform_reel_id, profile.username,
            len(matched), skipped_digest, skipped_x, skipped_quiet,
        )

    return matched


# ── Formatting ────────────────────────────────────────────────────────

# ── Niche display names (for match reason) ────────────────────────────
_NICHE_NAMES: dict[str, str] = {
    "ai": "AI & технологии", "tech": "Технологии", "business": "Бизнес",
    "marketing": "Маркетинг", "ecommerce": "E-commerce", "crypto": "Крипто",
    "finance": "Финансы", "real-estate": "Недвижимость", "personal-brand": "Личный бренд",
    "design": "Дизайн", "health": "Здоровье", "education": "Образование",
    "lifestyle": "Лайфстайл", "entertainment": "Развлечения",
    "vibe-coding": "Vibe Coding", "software-dev": "Разработка", "saas": "SaaS",
    "no-code": "No-code", "cybersecurity": "Кибербезопасность",
    "startups": "Стартапы", "investing": "Инвестиции",
    "freelance": "Фриланс", "copywriting": "Копирайтинг",
    "seo": "SEO", "smm": "SMM", "photography": "Фотография",
    "video-production": "Видеопродакшн", "music": "Музыка",
    "science": "Наука", "data-science": "Data Science",
}


def _format_views(n: int) -> str:
    """Format view count: 1234567 -> 1.2M, 12345 -> 12.3K."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _pick_headline_emoji(
    reel: ProfileReel, is_my_author: bool,
) -> str:
    """Pick headline emoji based on reel characteristics, not niche."""
    if is_my_author:
        return "\u2b50"       # ⭐ tracked author — top priority
    x = reel.x_factor or 0
    v = reel.velocity or 0
    if x >= 10:
        return "\U0001f48e"   # 💎 mega hit
    if v >= 5000:
        return "\u26a1"       # ⚡ fast-growing
    return "\U0001f525"       # 🔥 standard trending


def _format_match_reason(match_reason: str | None) -> str | None:
    """Human-readable match reason line."""
    if not match_reason:
        return None
    if match_reason == "author":
        return "\u2b50 \u0412\u0430\u0448 \u0430\u0432\u0442\u043e\u0440"  # ⭐ Ваш автор
    if match_reason.startswith("niche("):
        niche_slug = match_reason[6:-1]
        name = _NICHE_NAMES.get(niche_slug, niche_slug)
        return f"\U0001f4a1 \u0421\u043e\u0432\u043f\u0430\u0434\u0435\u043d\u0438\u0435: {name}"  # 💡
    if match_reason.startswith("topic("):
        topic = match_reason[6:-1]
        return f"\U0001f4a1 \u0422\u0435\u043c\u0430: {topic}"  # 💡
    return None


def format_radar_message(
    reel: ProfileReel, profile: TrackedProfile, is_my_author: bool,
    match_reason: str | None = None,
) -> tuple[str, dict | None, str | None]:
    """Format a Telegram notification for a trending reel.

    Returns (caption_text, reply_markup, photo_url) tuple.
    photo_url may be None if reel has no thumbnail.
    """
    from app.services.telegram import escape_html

    views_str = _format_views(reel.views or 0)
    x_str = f"{reel.x_factor:.1f}" if reel.x_factor else "?"
    emoji = _pick_headline_emoji(reel, is_my_author)

    # ── Headline ──
    headline = f"{emoji} <b>\u0417\u0430\u043b\u0451\u0442 X{x_str}</b> \u2014 {views_str} \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u043e\u0432"

    # ── Author line ──
    username = escape_html(profile.username or "")
    followers = ""
    if profile.followers_count and profile.followers_count > 0:
        followers = f" \u00b7 {_format_views(profile.followers_count)} \u043f\u043e\u0434\u043f\u0438\u0441\u0447\u0438\u043a\u043e\u0432"
    author_line = f"\U0001f464 @{username}{followers}"

    # ── Metrics line ──
    metrics_parts: list[str] = []
    if reel.velocity and reel.velocity > 0:
        metrics_parts.append(f"\U0001f4c8 +{_format_views(int(reel.velocity))}/\u0447\u0430\u0441")
    if reel.likes and reel.likes > 0:
        metrics_parts.append(f"\u2764\ufe0f {_format_views(reel.likes)}")
    if reel.comments and reel.comments > 0:
        metrics_parts.append(f"\U0001f4ac {_format_views(reel.comments)}")
    metrics_line = " \u00b7 ".join(metrics_parts) if metrics_parts else ""

    # ── Caption preview ──
    caption_text = ""
    raw_caption = reel.caption or ""
    if raw_caption:
        preview = raw_caption[:120]
        if len(raw_caption) > 120:
            preview += "..."
        caption_text = escape_html(preview)

    # ── Match reason ──
    reason_line = _format_match_reason(match_reason)

    # ── Reel link ──
    reel_link = ""
    if reel.url:
        reel_link = f'\U0001f517 <a href="{reel.url}">\u0421\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u0440\u0438\u043b\u0441</a>'

    # ── Assemble ──
    lines = [headline, "", author_line]
    if metrics_line:
        lines.append(metrics_line)
    if reel_link:
        lines.append("")
        lines.append(reel_link)
    if caption_text:
        lines.append("")
        lines.append(caption_text)
    if reason_line:
        lines.append("")
        lines.append(reason_line)

    text = "\n".join(lines)

    # Telegram sendPhoto caption limit: 1024 chars.
    # If over limit, trim caption preview to fit.
    if len(text) > 1000 and caption_text:
        over = len(text) - 950
        trimmed_len = max(20, len(caption_text) - over)
        caption_text = caption_text[:trimmed_len] + "..."
        # Rebuild
        lines = [headline, "", author_line]
        if metrics_line:
            lines.append(metrics_line)
        if reel_link:
            lines.append("")
            lines.append(reel_link)
        if caption_text:
            lines.append("")
            lines.append(caption_text)
        if reason_line:
            lines.append("")
            lines.append(reason_line)
        text = "\n".join(lines)

    # ── Buttons ──
    buttons_row: list[dict] = []
    if reel.url:
        buttons_row.append({"text": "\u25b6\ufe0f \u0421\u043c\u043e\u0442\u0440\u0435\u0442\u044c", "url": reel.url})
    buttons_row.append(
        {"text": "\U0001f50d \u0420\u0430\u0437\u043e\u0431\u0440\u0430\u0442\u044c", "callback_data": f"analyze:{reel.id}"},
    )
    reply_markup = {"inline_keyboard": [buttons_row]}

    # ── Photo URL ──
    photo_url = reel.thumbnail_url if reel.thumbnail_url else None

    return text, reply_markup, photo_url


def _format_digest_message(
    reels: list[tuple[ProfileReel, TrackedProfile, bool]],
) -> tuple[str, dict | None]:
    """Format a digest of multiple reels. Returns (text, reply_markup)."""
    from app.services.telegram import escape_html

    lines = [
        f"\U0001f4e1 <b>\u0420\u0430\u0434\u0430\u0440 \u0442\u0440\u0435\u043d\u0434\u043e\u0432</b> \u2014 {len(reels)} \u043d\u043e\u0432\u044b\u0445 \u0437\u0430\u043b\u0451\u0442\u043e\u0432",
        "",
    ]

    for i, (reel, profile, is_my) in enumerate(reels, 1):
        emoji = _pick_headline_emoji(reel, is_my)
        views = _format_views(reel.views or 0)
        x_str = f"X{reel.x_factor:.1f}" if reel.x_factor else ""
        username = escape_html(profile.username or "")

        lines.append(f"{i}. {emoji} <b>@{username}</b> \u2022 {x_str} \u2022 {views}")

        caption = (reel.caption or "")[:60]
        if caption:
            if len(reel.caption or "") > 60:
                caption += "..."
            lines.append(f"   {escape_html(caption)}")

        if reel.url:
            lines.append(f'   <a href="{reel.url}">\u25b6\ufe0f \u0421\u043c\u043e\u0442\u0440\u0435\u0442\u044c</a>')
        lines.append("")

    text = "\n".join(lines)

    reply_markup = {
        "inline_keyboard": [[
            {"text": "\U0001f4ca \u0412\u0441\u0435 \u0442\u0440\u0435\u043d\u0434\u044b", "url": f"{settings.app_url}/trends"},
        ]]
    }

    return text, reply_markup


# ── Main entry points ─────────────────────────────────────────────────

async def send_radar_notifications(db: AsyncSession, *, redis=None) -> int:
    """Main radar tick: detect new trending reels, match to users, send.

    Returns total notifications sent.

    Args:
        redis: Optional Redis connection for publishing monitoring events.
    """
    if not settings.telegram_bot_token:
        return 0

    # Step 1: Get un-notified trending reels
    reel_pairs = await get_unnotified_trending_reels(db)
    if not reel_pairs:
        return 0

    logger.info("[radar] Found %d new trending reels to process", len(reel_pairs))

    # Step 2: Get eligible users (cached for this tick)
    users = await get_radar_eligible_users(db)
    if not users:
        # No eligible users -> still mark reels as notified to avoid re-processing
        reel_ids = [reel.id for reel, _ in reel_pairs]
        await db.execute(
            update(ProfileReel)
            .where(ProfileReel.id.in_(reel_ids))
            .values(radar_notified_at=datetime.utcnow())
        )
        try:
            await db.commit()
        except Exception as e:
            logger.error("[radar] Failed to commit reel marks: %s", e)
            await db.rollback()
        return 0

    # Step 3: Match and send
    total_sent = 0
    user_send_counts: dict[str, int] = {}

    for reel, profile in reel_pairs:
        matched = match_reel_to_users(reel, profile, users)

        for radar_user, reason in matched:
            # Anti-spam: max N per user per tick
            count = user_send_counts.get(radar_user.user_id, 0)
            if count >= MAX_PER_USER_PER_TICK:
                continue

            is_my_author = profile.id in radar_user.tracked_profile_ids
            text, reply_markup, photo_url = format_radar_message(
                reel, profile, is_my_author, match_reason=reason,
            )

            try:
                if photo_url:
                    await send_telegram_photo(
                        radar_user.telegram_user_id,
                        settings.telegram_bot_token,
                        photo_url,
                        text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                else:
                    await send_telegram_message(
                        radar_user.telegram_user_id,
                        settings.telegram_bot_token,
                        text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                total_sent += 1
                user_send_counts[radar_user.user_id] = count + 1
            except Exception:
                pass  # best-effort

            # Rate limit: sleep briefly if approaching Telegram limit
            if total_sent % TELEGRAM_RATE_LIMIT == 0:
                await asyncio.sleep(1.1)

        # Mark reel as notified regardless of how many users received it
        reel.radar_notified_at = datetime.utcnow()

    try:
        await db.commit()
    except Exception as e:
        logger.error("[radar] Failed to commit: %s", e)
        await db.rollback()

    logger.info("[radar] Sent %d notifications for %d reels", total_sent, len(reel_pairs))

    # Publish monitoring events for admin dashboard
    if redis is not None and total_sent > 0:
        try:
            from app.services.trend_monitor import (
                _publish_monitoring_event, _log_activity, _increment_hourly,
            )
            await _publish_monitoring_event(
                redis, "notifications_sent",
                total_sent=total_sent, reels_count=len(reel_pairs),
            )
            await _log_activity(
                redis, "notification_sent",
                profile_username="radar", platform="all",
                details={"total_sent": total_sent, "reels_count": len(reel_pairs)},
            )
            # Single HINCRBY for all notifications (not N round-trips)
            hour_key = f"trend:hourly:{datetime.utcnow().strftime('%Y-%m-%d')}:{datetime.utcnow().hour}"
            await redis.hincrby(hour_key, "notifications", total_sent)
            await redis.expire(hour_key, 172800)
        except Exception:
            logger.debug("[radar] Failed to publish monitoring events", exc_info=True)

    return total_sent


async def send_radar_daily_digest(db: AsyncSession) -> int:
    """Send morning digest of trending reels from the last 24h.

    Only sent to users with mode="digest" (not "both" — those already got
    instant notifications and don't need duplicates in the digest).

    Returns number of digest messages sent.
    """
    if not settings.telegram_bot_token:
        return 0

    # Get all trending reels notified in the last 24h
    cutoff = datetime.utcnow() - timedelta(hours=24)
    result = await db.execute(
        select(ProfileReel, TrackedProfile)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.is_hidden == False,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            ProfileReel.radar_notified_at.isnot(None),
            ProfileReel.radar_notified_at >= cutoff,
        )
        .order_by(ProfileReel.hot_score.desc().nullslast())
        .limit(20)
    )
    reel_pairs = list(result.all())

    if not reel_pairs:
        return 0

    # Digest-only users (mode="both" already got instant notifications)
    users = await get_radar_eligible_users(db)
    digest_users = [u for u in users if u.mode == "digest"]

    if not digest_users:
        return 0

    sent = 0
    for user in digest_users:
        # Filter reels relevant to this user
        relevant: list[tuple[ProfileReel, TrackedProfile, bool]] = []
        for reel, profile in reel_pairs:
            if (reel.x_factor or 0) < user.min_x_factor:
                continue
            reason = _match_reason(user, profile, reel)
            if reason:
                is_my = profile.id in user.tracked_profile_ids
                relevant.append((reel, profile, is_my))

        if not relevant:
            continue

        text, reply_markup = _format_digest_message(relevant[:10])

        try:
            await send_telegram_message(
                user.telegram_user_id, settings.telegram_bot_token, text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            sent += 1
        except Exception:
            pass

        if sent % TELEGRAM_RATE_LIMIT == 0 and sent > 0:
            await asyncio.sleep(1.1)

    logger.info("[radar] Daily digest sent to %d users", sent)
    return sent
