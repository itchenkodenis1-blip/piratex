"""Admin Trend Watching endpoints — monitoring dashboard for trend pipeline.

Provides stats, pipeline state, activity log, and sparkline data for the
admin trend-watching dashboard.
"""

import json
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import get_admin_user
from app.database import get_db
from app.models.trends import ProfileReel, TrackedProfile
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_redis_from_request(request: Request):
    """Get Redis connection from app state (web process)."""
    managed = getattr(request.app.state, "managed_arq_pool", None)
    if managed:
        try:
            return await managed.get_pool()
        except Exception:
            pass
    return getattr(request.app.state, "arq_pool", None)


# ---------------------------------------------------------------------------
# GET /stats — aggregated metrics
# ---------------------------------------------------------------------------

@router.get("/stats")
async def trend_watching_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # DB queries
    total_profiles = (await db.execute(
        select(func.count()).select_from(TrackedProfile).where(
            TrackedProfile.is_active == True,  # noqa: E712
        )
    )).scalar() or 0

    checked_today = (await db.execute(
        select(func.count()).select_from(TrackedProfile).where(
            TrackedProfile.is_active == True,  # noqa: E712
            TrackedProfile.last_checked_at >= today_start,
        )
    )).scalar() or 0

    trends_found_today = (await db.execute(
        select(func.count()).select_from(ProfileReel).where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.updated_at >= today_start,
        )
    )).scalar() or 0

    hot_trends_today = (await db.execute(
        select(func.count()).select_from(ProfileReel).where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.updated_at >= today_start,
            ProfileReel.x_factor >= 5.0,
        )
    )).scalar() or 0

    notifications_sent_today = (await db.execute(
        select(func.count()).select_from(ProfileReel).where(
            ProfileReel.radar_notified_at >= today_start,
        )
    )).scalar() or 0

    # Priority distribution
    priority_rows = (await db.execute(
        select(TrackedProfile.check_priority, func.count())
        .where(TrackedProfile.is_active == True)  # noqa: E712
        .group_by(TrackedProfile.check_priority)
    )).all()
    profiles_by_priority = {row[0]: row[1] for row in priority_rows}

    scrape_errors_24h = (await db.execute(
        select(func.count()).select_from(TrackedProfile).where(
            TrackedProfile.consecutive_scrape_failures > 0,
        )
    )).scalar() or 0

    # Queue size: profiles that are stale (due for check)
    queue_size = 0
    for priority, hours in [("high", 4), ("normal", 12), ("cold", 48)]:
        cutoff = now - timedelta(hours=hours)
        cnt = (await db.execute(
            select(func.count()).select_from(TrackedProfile).where(
                TrackedProfile.is_active == True,  # noqa: E712
                TrackedProfile.check_priority == priority,
                TrackedProfile.last_checked_at.isnot(None),
                TrackedProfile.last_checked_at < cutoff,
            )
        )).scalar() or 0
        queue_size += cnt
    # Add never-checked profiles
    never_checked = (await db.execute(
        select(func.count()).select_from(TrackedProfile).where(
            TrackedProfile.is_active == True,  # noqa: E712
            TrackedProfile.last_checked_at.is_(None),
        )
    )).scalar() or 0
    queue_size += never_checked

    # Redis: currently scraping/analyzing counts (SCAN instead of KEYS)
    currently_scraping = 0
    currently_analyzing = 0
    redis = await _get_redis_from_request(request)
    if redis:
        for pattern, attr in [("trend:scraping:*", "scraping"), ("trend:analyzing:*", "analyzing")]:
            try:
                cursor, count = b"0", 0
                while True:
                    cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                    count += len(keys)
                    if cursor == 0 or cursor == b"0":
                        break
                if attr == "scraping":
                    currently_scraping = count
                else:
                    currently_analyzing = count
            except Exception:
                pass

    # Last check time and next estimate
    last_checked_result = (await db.execute(
        select(func.max(TrackedProfile.last_checked_at))
    )).scalar()
    last_check_run_at = last_checked_result.isoformat() + "Z" if last_checked_result else None
    next_check_run_at = None
    if last_checked_result:
        next_run = last_checked_result + timedelta(minutes=30)
        next_check_run_at = next_run.isoformat() + "Z"

    # Apify budget + cost data
    apify_balance_pct = None
    apify_used_usd = None
    apify_remaining_usd = None
    apify_runs_today = 0
    ai_tokens_today = 0
    ai_calls_today = 0
    ai_cost_estimate_usd = 0.0

    if redis:
        try:
            cached = await redis.get("apify:balance:cached")
            if cached:
                balance_data = json.loads(cached)
                apify_used_usd = balance_data.get("used_monthly_usd")
                apify_remaining_usd = balance_data.get("remaining_usd")
                max_monthly = balance_data.get("max_monthly_usd", 0)
                if max_monthly and max_monthly > 0 and apify_remaining_usd is not None:
                    apify_balance_pct = round(apify_remaining_usd / max_monthly * 100, 1)
        except Exception:
            pass

        # Apify daily runs
        try:
            today_key = f"apify:runs:{date.today().isoformat()}"
            runs_raw = await redis.get(today_key)
            apify_runs_today = int(runs_raw.decode() if isinstance(runs_raw, bytes) else runs_raw) if runs_raw else 0
        except Exception:
            pass

        # AI usage today
        try:
            today_str = date.today().isoformat()
            tok_raw = await redis.get(f"trend:ai:tokens:{today_str}")
            call_raw = await redis.get(f"trend:ai:calls:{today_str}")
            ai_tokens_today = int(tok_raw.decode() if isinstance(tok_raw, bytes) else tok_raw) if tok_raw else 0
            ai_calls_today = int(call_raw.decode() if isinstance(call_raw, bytes) else call_raw) if call_raw else 0
            # Haiku pricing: $0.80/M input + $4/M output ≈ avg $1/M tokens
            ai_cost_estimate_usd = round(ai_tokens_today * 1.0 / 1_000_000, 4)
        except Exception:
            pass

    return {
        "total_profiles": total_profiles,
        "checked_today": checked_today,
        "queue_size": queue_size,
        "currently_scraping": currently_scraping,
        "currently_analyzing": currently_analyzing,
        "trends_found_today": trends_found_today,
        "hot_trends_today": hot_trends_today,
        "notifications_sent_today": notifications_sent_today,
        "profiles_by_priority": {
            "high": profiles_by_priority.get("high", 0),
            "normal": profiles_by_priority.get("normal", 0),
            "cold": profiles_by_priority.get("cold", 0),
        },
        "scrape_errors_24h": scrape_errors_24h,
        "last_check_run_at": last_check_run_at,
        "next_check_run_at": next_check_run_at,
        "apify_balance_pct": apify_balance_pct,
        "apify_used_usd": apify_used_usd,
        "apify_remaining_usd": apify_remaining_usd,
        "apify_runs_today": apify_runs_today,
        "ai_tokens_today": ai_tokens_today,
        "ai_calls_today": ai_calls_today,
        "ai_cost_estimate_usd": ai_cost_estimate_usd,
    }


# ---------------------------------------------------------------------------
# GET /pipeline — Kanban board state
# ---------------------------------------------------------------------------

@router.get("/pipeline")
async def trend_watching_pipeline(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    now = datetime.utcnow()
    redis = await _get_redis_from_request(request)

    def _profile_dict(p: TrackedProfile, extra: dict | None = None) -> dict:
        d = {
            "profile_id": str(p.id),
            "username": p.username,
            "platform": p.platform,
            "display_name": p.display_name,
            "followers_count": p.followers_count,
            "niche": p.niche,
            "check_priority": p.check_priority,
            "last_checked_at": p.last_checked_at.isoformat() + "Z" if p.last_checked_at else None,
            "trending_count": 0,
        }
        if extra:
            d.update(extra)
        return d

    # Scraping / Analyzing from Redis keys
    scraping = []
    analyzing = []
    active_profile_ids = set()

    if redis:
        try:
            for prefix, target in [("trend:scraping:", scraping), ("trend:analyzing:", analyzing)]:
                # Use SCAN instead of KEYS to avoid blocking Redis
                keys = []
                cursor = b"0"
                while True:
                    cursor, batch = await redis.scan(cursor, match=f"{prefix}*", count=100)
                    keys.extend(batch)
                    if cursor == 0 or cursor == b"0":
                        break
                for key in keys:
                    raw = await redis.get(key)
                    if raw:
                        try:
                            data = json.loads(raw)
                            profile_id = key.replace(prefix, "")
                            active_profile_ids.add(profile_id)
                            target.append({
                                "profile_id": profile_id,
                                "username": data.get("username", ""),
                                "platform": data.get("platform", "instagram"),
                                "display_name": None,
                                "followers_count": None,
                                "niche": None,
                                "check_priority": "high",
                                "last_checked_at": None,
                                "trending_count": 0,
                                "started_at": data.get("started_at"),
                            })
                        except Exception:
                            pass
        except Exception:
            pass

    # ── Queued: stale profiles + "next up" profiles approaching check time ──
    queued = []
    PRIORITY_INTERVALS = {"high": 4, "normal": 12, "cold": 48}

    # 1. Actually stale profiles (past their check interval)
    for priority, hours in PRIORITY_INTERVALS.items():
        cutoff = now - timedelta(hours=hours)
        result = await db.execute(
            select(TrackedProfile)
            .where(
                TrackedProfile.is_active == True,  # noqa: E712
                TrackedProfile.check_priority == priority,
                TrackedProfile.last_checked_at.isnot(None),
                TrackedProfile.last_checked_at < cutoff,
            )
            .order_by(TrackedProfile.last_checked_at.asc())
            .limit(15)
        )
        for p in result.scalars().all():
            if str(p.id) not in active_profile_ids:
                stale_mins = int((now - p.last_checked_at).total_seconds() / 60) if p.last_checked_at else 0
                queued.append(_profile_dict(p, {"stale_since_minutes": stale_mins, "status": "stale"}))

    # 2. Never-checked profiles
    never_result = await db.execute(
        select(TrackedProfile)
        .where(
            TrackedProfile.is_active == True,  # noqa: E712
            TrackedProfile.last_checked_at.is_(None),
        )
        .order_by(TrackedProfile.created_at.asc())
        .limit(10)
    )
    for p in never_result.scalars().all():
        if str(p.id) not in active_profile_ids:
            queued.append(_profile_dict(p, {"stale_since_minutes": None, "check_priority": "new", "status": "new"}))

    # 3. "Next up" — profiles closest to their check interval (shows life between cycles)
    if len(queued) < 20:
        next_up_limit = 20 - len(queued)
        queued_ids = {item["profile_id"] for item in queued}
        for priority, hours in PRIORITY_INTERVALS.items():
            cutoff = now - timedelta(hours=hours)
            # Profiles checked but NOT yet stale — ordered by soonest-to-check
            result = await db.execute(
                select(TrackedProfile)
                .where(
                    TrackedProfile.is_active == True,  # noqa: E712
                    TrackedProfile.check_priority == priority,
                    TrackedProfile.last_checked_at.isnot(None),
                    TrackedProfile.last_checked_at >= cutoff,
                )
                .order_by(TrackedProfile.last_checked_at.asc())
                .limit(next_up_limit)
            )
            for p in result.scalars().all():
                pid = str(p.id)
                if pid not in active_profile_ids and pid not in queued_ids:
                    interval_sec = hours * 3600
                    elapsed = (now - p.last_checked_at).total_seconds() if p.last_checked_at else 0
                    remaining_min = max(0, int((interval_sec - elapsed) / 60))
                    queued.append(_profile_dict(p, {
                        "stale_since_minutes": -remaining_min,  # negative = minutes until check
                        "status": "next_up",
                    }))
                    queued_ids.add(pid)

    # ── Completed: from Redis activity log, fallback to DB ──
    completed = []
    failed = []

    # Try Redis activity log first
    if redis:
        try:
            hour_ago = (now - timedelta(hours=1)).timestamp()
            entries = await redis.zrevrangebyscore(
                "trend:activity", "+inf", hour_ago, start=0, num=50,
            )
            for raw_entry in entries:
                try:
                    event = json.loads(raw_entry)
                    item = {
                        "profile_id": None,
                        "username": event.get("profile_username", ""),
                        "platform": event.get("platform", "instagram"),
                        "display_name": None,
                        "followers_count": None,
                        "niche": None,
                        "check_priority": event.get("details", {}).get("check_priority", "normal"),
                        "last_checked_at": event.get("timestamp"),
                        "trending_count": event.get("details", {}).get("trending_count", 0),
                    }
                    if event.get("type") == "check_complete":
                        item["details"] = event.get("details", {})
                        completed.append(item)
                    elif event.get("type") == "error":
                        item["error"] = event.get("details", {}).get("error", "unknown")
                        failed.append(item)
                except Exception:
                    pass
        except Exception:
            pass

    # Fallback: if no Redis data, show recently checked profiles from DB
    if not completed:
        recent_cutoff = now - timedelta(hours=2)
        # Subquery for trending count
        trending_sq = (
            select(func.count())
            .where(
                ProfileReel.profile_id == TrackedProfile.id,
                ProfileReel.is_trending == True,  # noqa: E712
            )
            .correlate(TrackedProfile)
            .scalar_subquery()
        )
        recent_result = await db.execute(
            select(TrackedProfile, trending_sq.label("trending_cnt"))
            .where(
                TrackedProfile.is_active == True,  # noqa: E712
                TrackedProfile.last_checked_at >= recent_cutoff,
            )
            .order_by(TrackedProfile.last_checked_at.desc())
            .limit(20)
        )
        for row in recent_result.all():
            p = row[0]
            trending_cnt = row[1] or 0
            if str(p.id) not in active_profile_ids:
                completed.append(_profile_dict(p, {
                    "trending_count": trending_cnt,
                    "status": "recently_checked",
                }))

    # Failed: profiles with scrape failures (from DB)
    if not failed:
        fail_result = await db.execute(
            select(TrackedProfile)
            .where(
                TrackedProfile.consecutive_scrape_failures > 0,
            )
            .order_by(TrackedProfile.consecutive_scrape_failures.desc())
            .limit(10)
        )
        for p in fail_result.scalars().all():
            failed.append(_profile_dict(p, {
                "error": f"scrape failures: {p.consecutive_scrape_failures}/3",
                "status": "scrape_error",
            }))

    # ── Enrich completed profiles with trending reels ──
    completed = completed[:20]
    completed_usernames = list({c["username"] for c in completed if c.get("username")})
    if completed_usernames:
        try:
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_ago = now - timedelta(days=7)
            reels_result = await db.execute(
                select(ProfileReel, TrackedProfile.username)
                .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
                .where(
                    TrackedProfile.username.in_(completed_usernames),
                    ProfileReel.is_trending == True,  # noqa: E712
                    ProfileReel.published_at >= week_ago,
                )
                .order_by(ProfileReel.x_factor.desc().nullslast())
                .limit(60)  # max 3 per profile * 20 profiles
            )
            reels_by_username: dict[str, list] = {}
            for reel, username in reels_result.all():
                if len(reels_by_username.get(username, [])) < 3:
                    reels_by_username.setdefault(username, []).append({
                        "thumbnail_url": reel.thumbnail_url,
                        "url": reel.url,
                        "x_factor": round(reel.x_factor, 1) if reel.x_factor else None,
                        "views": reel.views,
                        "caption": (reel.caption or "")[:60],
                    })
            for item in completed:
                item["trending_reels"] = reels_by_username.get(item["username"], [])
        except Exception:
            logger.warning("[admin-trends] Failed to enrich trending reels", exc_info=True)

    return {
        "queued": queued[:40],
        "scraping": scraping,
        "analyzing": analyzing,
        "completed": completed,
        "failed": failed[:10],
    }


# ---------------------------------------------------------------------------
# GET /activity — event log
# ---------------------------------------------------------------------------

@router.get("/activity")
async def trend_watching_activity(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
    limit: int = 50,
):
    redis = await _get_redis_from_request(request)
    events = []

    # Try Redis activity log
    if redis:
        try:
            total = await redis.zcard("trend:activity")
            raw_entries = await redis.zrevrangebyscore(
                "trend:activity", "+inf", "-inf", start=0, num=min(limit, 200),
            )
            for raw in raw_entries:
                try:
                    events.append(json.loads(raw))
                except Exception:
                    pass
            if events:
                return {"events": events, "total": total}
        except Exception as e:
            logger.warning("[admin-trends] Failed to read activity: %s", e)

    # Fallback: generate activity from recent DB data
    now = datetime.utcnow()
    recent_cutoff = now - timedelta(hours=6)

    # Recently checked profiles as "check_complete" events
    result = await db.execute(
        select(TrackedProfile)
        .where(
            TrackedProfile.last_checked_at >= recent_cutoff,
        )
        .order_by(TrackedProfile.last_checked_at.desc())
        .limit(min(limit, 50))
    )
    for p in result.scalars().all():
        events.append({
            "type": "check_complete",
            "timestamp": p.last_checked_at.isoformat() + "Z" if p.last_checked_at else now.isoformat() + "Z",
            "profile_username": p.username,
            "platform": p.platform,
            "details": {
                "check_priority": p.check_priority,
                "niche": p.niche,
                "source": "db_fallback",
            },
        })

    # Recently found trending reels
    trending_result = await db.execute(
        select(ProfileReel, TrackedProfile.username, TrackedProfile.platform)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.updated_at >= recent_cutoff,
        )
        .order_by(ProfileReel.updated_at.desc())
        .limit(20)
    )
    for row in trending_result.all():
        reel, username, platform = row
        events.append({
            "type": "trend_found",
            "timestamp": reel.updated_at.isoformat() + "Z" if reel.updated_at else now.isoformat() + "Z",
            "profile_username": username,
            "platform": platform,
            "details": {
                "x_factor": round(reel.x_factor or 0, 1),
                "hot_score": round(reel.hot_score or 0, 3),
                "views": reel.views,
                "source": "db_fallback",
            },
        })

    # Sort by timestamp descending
    events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return {"events": events[:limit], "total": len(events)}


# ---------------------------------------------------------------------------
# GET /sparklines — hourly counters for 24h charts
# ---------------------------------------------------------------------------

@router.get("/sparklines")
async def trend_watching_sparklines(
    request: Request,
    _admin: User = Depends(get_admin_user),
):
    redis = await _get_redis_from_request(request)
    if not redis:
        return {
            "checks_per_hour": [0] * 24,
            "trends_per_hour": [0] * 24,
            "notifications_per_hour": [0] * 24,
            "errors_per_hour": [0] * 24,
        }

    now = datetime.utcnow()
    checks = []
    trends = []
    notifications = []
    errors = []

    try:
        # Build all keys first, then fetch in parallel
        hour_keys = []
        for i in range(23, -1, -1):
            t = now - timedelta(hours=i)
            hour_keys.append(f"trend:hourly:{t.strftime('%Y-%m-%d')}:{t.hour}")

        # Fetch all 24 hashes (parallel via gather for reduced latency)
        import asyncio as _aio
        results = await _aio.gather(
            *(redis.hgetall(key) for key in hour_keys),
            return_exceptions=True,
        )
        for data in results:
            if isinstance(data, Exception):
                data = {}
            checks.append(int(data.get("checks", 0)))
            trends.append(int(data.get("trends", 0)))
            notifications.append(int(data.get("notifications", 0)))
            errors.append(int(data.get("errors", 0)))
    except Exception as e:
        logger.warning("[admin-trends] Failed to read sparklines: %s", e)
        return {
            "checks_per_hour": [0] * 24,
            "trends_per_hour": [0] * 24,
            "notifications_per_hour": [0] * 24,
            "errors_per_hour": [0] * 24,
        }

    return {
        "checks_per_hour": checks,
        "trends_per_hour": trends,
        "notifications_per_hour": notifications,
        "errors_per_hour": errors,
    }
