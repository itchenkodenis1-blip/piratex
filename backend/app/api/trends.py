from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_admin_user, get_current_user, get_optional_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.trends import ProfileReel, TrackedProfile, UserTrackedProfile
from app.models.user import User
from app.models.library import LibraryReel, UserBookmark, UserScript
from app.models.user import UserSettings
from app.schemas.profile import UserProfile
from app.schemas.trends import (
    AddAuthorRequest,
    ForYouResponse,
    MyAuthorsResponse,
    NicheStats,
    TrackedAuthorResponse,
    TrendAuthor,
    TrendItem,
    TrendsListResponse,
)
from app.services.niche_inference import infer_user_interests, infer_user_niches
from app.services.trend_monitor import AUTHOR_LIMITS, add_user_author, get_frozen_count, get_user_authors, parse_author_input, remove_user_author

trends_router = APIRouter(prefix="/trends", tags=["trends"])


def _escape_like(value: str) -> str:
    """Escape LIKE-special characters so they match literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_trend_item(
    reel: ProfileReel, profile: TrackedProfile, followed_ids: set[str],
    frame_count: int = 0,
) -> TrendItem:
    """Build a TrendItem from ORM objects."""
    return TrendItem(
        id=reel.id,
        url=reel.url,
        caption=reel.caption,
        thumbnail_url=reel.thumbnail_url,
        published_at=reel.published_at,
        duration=reel.duration,
        views=reel.views,
        likes=reel.likes,
        comments=reel.comments,
        x_factor=reel.x_factor,
        velocity=reel.velocity,
        hot_score=reel.hot_score,
        niche=reel.niche,
        author=TrendAuthor(
            profile_id=profile.id,
            username=profile.username,
            display_name=profile.display_name,
            platform=profile.platform,
            followers_count=profile.followers_count,
            median_views=profile.median_views,
            niche=profile.niche,
        ),
        is_parsed=reel.library_reel_id is not None,
        library_reel_id=reel.library_reel_id,
        trending_since=reel.trending_since,
        frame_count=frame_count,
        is_followed=profile.id in followed_ids,
    )


async def _resolve_user_preferences(
    db: AsyncSession, user: User,
) -> tuple[list[str], str, list[str], str]:
    """Resolve user niches & interests from settings or auto-inference.

    Returns (user_niches, niche_source, user_interests, interest_source).
    """
    niche_source = "none"
    interest_source = "none"
    user_niches: list[str] = []
    user_interests: list[str] = []

    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_result.scalar_one_or_none()

    if user_settings and user_settings.profile_json:
        try:
            profile = UserProfile(**user_settings.profile_json)
            if profile.niches:
                user_niches = profile.niches
                niche_source = "manual"
            if profile.interests:
                user_interests = profile.interests
                interest_source = "manual"
        except Exception:
            pass

    if not user_interests:
        detected = await infer_user_interests(db, user.id, top_n=15)
        if detected:
            user_interests = [d["topic"] for d in detected]
            interest_source = "auto"

    if not user_niches:
        user_niches = await infer_user_niches(db, user.id)
        if user_niches:
            niche_source = "auto"

    return user_niches, niche_source, user_interests, interest_source


async def _get_exclude_ids(db: AsyncSession, user_id: str) -> set[str]:
    """Collect library_reel IDs the user already interacted with."""
    parsed_result = await db.execute(
        select(LibraryReel.id).where(LibraryReel.submitted_by == user_id)
    )
    exclude_ids = {r[0] for r in parsed_result.all()}

    bm_result = await db.execute(
        select(UserBookmark.library_reel_id).where(UserBookmark.user_id == user_id)
    )
    exclude_ids |= {r[0] for r in bm_result.all()}

    sc_result = await db.execute(
        select(UserScript.library_reel_id).where(UserScript.user_id == user_id)
    )
    exclude_ids |= {r[0] for r in sc_result.all()}

    return exclude_ids


@trends_router.get("", response_model=TrendsListResponse)
async def list_trends(
    tab: str = Query("global", description="global, my_authors, or for_you"),
    niche: str = Query("", description="Filter by profile niche"),
    platform: str = Query("", description="Filter by platform"),
    min_x: float = Query(2.0, ge=0, description="Minimum X-factor"),
    sort: str = Query("hot_score", description="Sort: hot_score, x_factor, views, recent"),
    days: int | None = Query(None, ge=1, le=3650, description="Trending within N days (None = all time)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    q: str = Query("", description="Search by caption or author username"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """List trending reels with X-factor filtering."""
    from datetime import datetime, timedelta

    empty = TrendsListResponse(items=[], total=0, page=page, per_page=per_page)

    # ── Tier checks ───────────────────────────────────────────────
    if not user:
        # Anonymous: page 1 only, no filters/search
        if page > 1 or q or niche or platform or sort != "hot_score":
            raise HTTPException(429, detail={"detail": "auth_required_trends"})
    elif user.tier in ("FREE", "REGISTERED"):
        # Free: max 3 pages on "Все", no search
        if tab in ("global", "for_you") and page > 3:
            raise HTTPException(429, detail={"detail": "upgrade_required_trends"})
        if q:
            raise HTTPException(429, detail={"detail": "upgrade_required_search"})

    # ── Auth-required tabs ────────────────────────────────────────
    if tab in ("my_authors", "for_you") and not user:
        return empty

    cutoff = datetime.utcnow() - timedelta(days=days) if days else None

    # Pre-fetch followed profile IDs (non-frozen only)
    followed_ids: set[str] = set()
    if user:
        result = await db.execute(
            select(UserTrackedProfile.profile_id)
            .where(UserTrackedProfile.user_id == user.id, UserTrackedProfile.frozen == False)  # noqa: E712
        )
        followed_ids = {r[0] for r in result.all()}

    # ── For You tab — tiered recommendation logic ─────────────────
    if tab == "for_you" and user:
        return await _list_for_you(
            db, user, followed_ids, cutoff, min_x,
            niche, platform, sort, q, page, per_page,
        )

    # ── Standard tabs (global / my_authors) ───────────────────────
    frame_count_col = func.coalesce(
        func.json_array_length(LibraryReel.frames_json), 0
    ).label("frame_count")

    base_where = [
        ProfileReel.is_trending == True,  # noqa: E712
        ProfileReel.is_hidden == False,  # noqa: E712
        TrackedProfile.is_blocked == False,  # noqa: E712
        ProfileReel.x_factor >= min_x,
    ]
    if cutoff:
        # "Сегодня" = what the system caught today OR published today
        base_where.append(
            or_(
                ProfileReel.trending_since >= cutoff,
                ProfileReel.published_at >= cutoff,
            )
        )

    query = (
        select(ProfileReel, TrackedProfile, frame_count_col)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .outerjoin(LibraryReel, LibraryReel.id == ProfileReel.library_reel_id)
        .where(*base_where)
    )

    if tab == "my_authors" and user:
        query = query.where(TrackedProfile.id.in_(followed_ids))

    # Filters — niche param: comma-separated slugs/groups, resolved to union
    if niche:
        from app.core.niche_cache import niche_cache
        slugs = niche_cache.resolve_multi_filter_slugs(niche)
        if len(slugs) > 1:
            query = query.where(ProfileReel.niche.in_(slugs))
        elif slugs:
            query = query.where(ProfileReel.niche == next(iter(slugs)))
        else:
            query = query.where(ProfileReel.niche == niche)
    if platform:
        query = query.where(TrackedProfile.platform == platform)
    if q:
        like = f"%{_escape_like(q)}%"
        query = query.where(
            or_(ProfileReel.caption.ilike(like), TrackedProfile.username.ilike(like), TrackedProfile.display_name.ilike(like))
        )

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort
    if sort == "views":
        query = query.order_by(ProfileReel.views.desc().nullslast())
    elif sort == "recent":
        query = query.order_by(ProfileReel.published_at.desc().nullslast())
    elif sort == "x_factor":
        query = query.order_by(ProfileReel.x_factor.desc().nullslast())
    else:  # hot_score — sort by x_factor (freshness already filtered by cutoff)
        query = query.order_by(ProfileReel.x_factor.desc().nullslast())

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = [
        _build_trend_item(reel, profile, followed_ids, fc)
        for reel, profile, fc in rows
    ]

    return TrendsListResponse(items=items, total=total, page=page, per_page=per_page)


async def _collect_user_signals(db: AsyncSession, user_id: str) -> dict:
    """Collect author-level affinity signals for personalization scoring."""
    from app.models.library import UserReelLike

    # 1. Followed authors (non-frozen only)
    followed = await db.execute(
        select(UserTrackedProfile.profile_id)
        .where(UserTrackedProfile.user_id == user_id, UserTrackedProfile.frozen == False)  # noqa: E712
    )
    followed_profile_ids = {r[0] for r in followed.all()}

    # 2. Authors whose reels user liked
    liked_result = await db.execute(
        select(ProfileReel.profile_id).distinct()
        .join(UserReelLike, UserReelLike.url == ProfileReel.url)
        .where(UserReelLike.user_id == user_id)
    )
    liked_author_ids = {r[0] for r in liked_result.all()}

    # 3. Authors whose reels user parsed
    parsed_result = await db.execute(
        select(ProfileReel.profile_id).distinct()
        .join(LibraryReel, LibraryReel.url == ProfileReel.url)
        .where(LibraryReel.submitted_by == user_id)
    )
    parsed_author_ids = {r[0] for r in parsed_result.all()}

    # 4. Niches from liked reels (per-reel niche)
    liked_niches_result = await db.execute(
        select(ProfileReel.niche).distinct()
        .join(UserReelLike, UserReelLike.url == ProfileReel.url)
        .where(UserReelLike.user_id == user_id, ProfileReel.niche.isnot(None))
    )
    liked_niches = {r[0] for r in liked_niches_result.all()}

    return {
        "followed_profile_ids": followed_profile_ids,
        "liked_author_ids": liked_author_ids,
        "parsed_author_ids": parsed_author_ids,
        "liked_niches": liked_niches,
    }


def _personal_score(
    reel: ProfileReel,
    profile: TrackedProfile,
    signals: dict,
    interest_vector: dict[str, float],
    user_interests: list[str],
    user_niches: list[str],
) -> float:
    """Calculate personalization score for a reel based on Interest Graph.

    Components:
    A. Author affinity (followed +0.5, liked +0.3, parsed +0.2)
    B. Topic relevance via Interest Vector (weighted sum, max +0.5)
    C. Niche match (+0.1)
    D. Engagement quality bonus (max +0.15)
    """
    score = 0.0

    # A. Author affinity
    if profile.id in signals["followed_profile_ids"]:
        score += 0.5
    if profile.id in signals["liked_author_ids"]:
        score += 0.3
    if profile.id in signals["parsed_author_ids"]:
        score += 0.2

    # B. Topic relevance via Interest Vector
    if interest_vector and profile.topics:
        topic_score = sum(interest_vector.get(t, 0) for t in profile.topics)
        score += min(topic_score / 10.0, 0.5)
    elif user_interests and profile.topics:
        overlap = len(set(user_interests) & set(profile.topics))
        score += 0.1 * overlap

    # C. Niche match (prefer per-reel niche, fallback to profile)
    all_niches = set(user_niches) | signals.get("liked_niches", set())
    effective_niche = reel.niche or profile.niche
    if effective_niche and effective_niche in all_niches:
        score += 0.1

    # D. Engagement quality bonus
    views = reel.views or 0
    if views > 0:
        likes = reel.likes or 0
        comments = reel.comments or 0
        engagement_rate = (likes + comments * 3) / views
        score += min(engagement_rate / 0.10, 0.15)

    return score


async def _list_for_you(
    db: AsyncSession,
    user: User,
    followed_ids: set[str],
    cutoff,
    min_x: float,
    niche: str,
    platform: str,
    sort: str,
    q: str,
    page: int,
    per_page: int,
) -> TrendsListResponse:
    """Build personalized 'for you' trends.

    Personalization is a FILTER (by user niches/interests), not a score boost.
    For hot_score sort: order by x_factor DESC (hot = viral + fresh).
    For other sorts: order by the requested field, with niche relevance as tiebreaker.
    """
    from app.services.interest_signals import get_interest_vector

    # 1. Resolve user preferences for niche-based filtering
    interest_vector = await get_interest_vector(db, user.id, top_n=30)
    user_niches, niche_source, user_interests, interest_source = (
        await _resolve_user_preferences(db, user)
    )
    signals = await _collect_user_signals(db, user.id)
    exclude_ids = await _get_exclude_ids(db, user.id)

    if interest_vector:
        interest_source = "signals"

    # Enrich niches from liked reels
    enriched_niches = list(set(user_niches) | signals.get("liked_niches", set()))
    if enriched_niches and not user_niches:
        niche_source = "auto"

    # 2. Build query with niche-based personalization as SQL filter
    base_conditions = [
        ProfileReel.is_trending == True,  # noqa: E712
        ProfileReel.is_hidden == False,  # noqa: E712
        TrackedProfile.is_blocked == False,  # noqa: E712
        ProfileReel.x_factor >= min_x,
    ]
    if cutoff:
        # For "for you" tab: use trending_since (when system caught it),
        # not published_at — user wants "what the system found today for me"
        base_conditions.append(
            or_(
                ProfileReel.trending_since >= cutoff,
                ProfileReel.published_at >= cutoff,
            )
        )

    # Personalization filter: niche match OR topic match OR followed author
    # This narrows results to user's interests without boosting scores
    personalization_conditions = []
    if enriched_niches:
        personalization_conditions.append(ProfileReel.niche.in_(enriched_niches))
        personalization_conditions.append(TrackedProfile.niche.in_(enriched_niches))
    if followed_ids:
        personalization_conditions.append(TrackedProfile.id.in_(followed_ids))

    extra_conditions = []
    if personalization_conditions:
        extra_conditions.append(or_(*personalization_conditions))
    if niche:
        from app.core.niche_cache import niche_cache
        slugs = niche_cache.resolve_multi_filter_slugs(niche)
        if len(slugs) > 1:
            extra_conditions.append(ProfileReel.niche.in_(slugs))
        elif slugs:
            extra_conditions.append(ProfileReel.niche == next(iter(slugs)))
        else:
            extra_conditions.append(ProfileReel.niche == niche)
    if platform:
        extra_conditions.append(TrackedProfile.platform == platform)
    if q:
        like = f"%{_escape_like(q)}%"
        extra_conditions.append(
            or_(ProfileReel.caption.ilike(like), TrackedProfile.username.ilike(like), TrackedProfile.display_name.ilike(like))
        )

    frame_count_col = func.coalesce(
        func.json_array_length(LibraryReel.frames_json), 0
    ).label("frame_count")

    query = (
        select(ProfileReel, TrackedProfile, frame_count_col)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .outerjoin(LibraryReel, LibraryReel.id == ProfileReel.library_reel_id)
        .where(*base_conditions, *extra_conditions)
    )

    # Count total
    count_q = (
        select(func.count(ProfileReel.id))
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(*base_conditions, *extra_conditions)
    )
    total = (await db.execute(count_q)).scalar() or 0

    # 3. Sort — hot_score sort uses x_factor (hot = viral + fresh)
    if sort == "views":
        query = query.order_by(ProfileReel.views.desc().nullslast())
    elif sort == "recent":
        query = query.order_by(ProfileReel.published_at.desc().nullslast())
    elif sort == "x_factor":
        query = query.order_by(ProfileReel.x_factor.desc().nullslast())
    else:  # hot_score — sort by x_factor (freshness already filtered by cutoff)
        query = query.order_by(ProfileReel.x_factor.desc().nullslast())

    # 4. Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    # Exclude already-interacted reels
    items = []
    for reel, profile, fc in rows:
        if reel.library_reel_id and reel.library_reel_id in exclude_ids:
            continue
        item = _build_trend_item(reel, profile, followed_ids, fc)
        items.append(item)

    return TrendsListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        interest_source=interest_source,
        niche_source=niche_source,
    )


@trends_router.get("/for-you", response_model=ForYouResponse)
async def get_for_you(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Deprecated: use GET /trends?tab=for_you instead.

    Kept for backward compatibility.
    """
    from datetime import datetime, timedelta

    LIMIT = 10

    user_niches, niche_source, user_interests, interest_source = (
        await _resolve_user_preferences(db, user)
    )
    exclude_ids = await _get_exclude_ids(db, user.id)

    followed_result = await db.execute(
        select(UserTrackedProfile.profile_id)
        .where(UserTrackedProfile.user_id == user.id, UserTrackedProfile.frozen == False)  # noqa: E712
    )
    followed_ids = {r[0] for r in followed_result.all()}

    cutoff = datetime.utcnow() - timedelta(days=7)
    base_conditions = [
        ProfileReel.is_trending == True,  # noqa: E712
        ProfileReel.is_hidden == False,  # noqa: E712
        TrackedProfile.is_blocked == False,  # noqa: E712
        ProfileReel.published_at >= cutoff,
        ProfileReel.x_factor >= 2.0,
    ]

    items: list[TrendItem] = []
    seen_ids: set[str] = set()

    # Tier 1: Topic overlap
    if user_interests:
        topic_result = await db.execute(
            select(ProfileReel, TrackedProfile)
            .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
            .where(*base_conditions)
            .where(TrackedProfile.topics.isnot(None))
            .order_by(ProfileReel.hot_score.desc().nullslast())
            .limit(LIMIT * 5)
        )
        interest_set = set(user_interests)
        scored = []
        for reel, profile in topic_result.all():
            if reel.library_reel_id and reel.library_reel_id in exclude_ids:
                continue
            overlap = len(interest_set & set(profile.topics or []))
            if overlap > 0:
                scored.append((overlap, reel, profile))
        scored.sort(key=lambda x: (-x[0], -(x[1].hot_score or 0)))
        for _, reel, profile in scored:
            if len(items) >= LIMIT:
                break
            items.append(_build_trend_item(reel, profile, followed_ids))
            seen_ids.add(reel.id)

    # Tier 2: Niche fallback
    if len(items) < LIMIT and user_niches:
        niche_result = await db.execute(
            select(ProfileReel, TrackedProfile)
            .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
            .where(*base_conditions)
            .where(ProfileReel.niche.in_(user_niches))
            .order_by(ProfileReel.hot_score.desc().nullslast())
            .limit(LIMIT * 3)
        )
        for reel, profile in niche_result.all():
            if len(items) >= LIMIT:
                break
            if reel.id in seen_ids:
                continue
            if reel.library_reel_id and reel.library_reel_id in exclude_ids:
                continue
            items.append(_build_trend_item(reel, profile, followed_ids))
            seen_ids.add(reel.id)

    # Tier 3: Global fallback
    if len(items) < LIMIT:
        fallback_result = await db.execute(
            select(ProfileReel, TrackedProfile)
            .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
            .where(*base_conditions)
            .order_by(ProfileReel.hot_score.desc().nullslast())
            .limit((LIMIT - len(items)) * 3)
        )
        for reel, profile in fallback_result.all():
            if len(items) >= LIMIT:
                break
            if reel.id in seen_ids:
                continue
            if reel.library_reel_id and reel.library_reel_id in exclude_ids:
                continue
            items.append(_build_trend_item(reel, profile, followed_ids))

    # Batch-resolve frame counts
    lr_ids = [it.library_reel_id for it in items if it.library_reel_id]
    if lr_ids:
        fc_result = await db.execute(
            select(
                LibraryReel.id,
                func.coalesce(func.json_array_length(LibraryReel.frames_json), 0),
            ).where(LibraryReel.id.in_(lr_ids))
        )
        fc_map = {rid: cnt for rid, cnt in fc_result.all()}
        for it in items:
            if it.library_reel_id:
                it.frame_count = fc_map.get(it.library_reel_id, 0)

    return ForYouResponse(
        items=items,
        user_niches=user_niches,
        niche_source=niche_source,
        user_interests=user_interests,
        interest_source=interest_source,
    )


@trends_router.get("/authors", response_model=MyAuthorsResponse)
async def list_my_authors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List authors tracked by current user with limit info."""
    tier = user.tier or "FREE"
    limit = AUTHOR_LIMITS.get(tier, 0)
    profiles = await get_user_authors(db, user.id)  # excludes frozen by default
    frozen = await get_frozen_count(db, user.id)

    if not profiles:
        return MyAuthorsResponse(authors=[], count=0, limit=limit, frozen_count=frozen)

    # Batch fetch trending counts (NOT N+1)
    profile_ids = [p.id for p in profiles]
    trending_counts_result = await db.execute(
        select(ProfileReel.profile_id, func.count(ProfileReel.id))
        .where(ProfileReel.is_trending == True)  # noqa: E712
        .where(ProfileReel.is_hidden == False)  # noqa: E712
        .where(ProfileReel.profile_id.in_(profile_ids))
        .group_by(ProfileReel.profile_id)
    )
    trending_map = dict(trending_counts_result.all())

    authors = [
        TrackedAuthorResponse(
            id=p.id,
            platform=p.platform,
            username=p.username,
            display_name=p.display_name,
            profile_url=p.profile_url,
            followers_count=p.followers_count,
            median_views=p.median_views,
            niche=p.niche,
            total_reels=p.total_reels or 0,
            last_checked_at=p.last_checked_at,
            trending_count=trending_map.get(p.id, 0),
        )
        for p in profiles
    ]
    return MyAuthorsResponse(authors=authors, count=len(authors), limit=limit, frozen_count=frozen)


@trends_router.post("/authors", response_model=TrackedAuthorResponse)
@limiter.limit("5/minute")
async def add_my_author(
    payload: AddAuthorRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an author to track. Validates via Apify (may take 10-30s)."""
    platform, username = parse_author_input(payload.input)
    profile = await add_user_author(db, user, platform, username)

    # Get trending count
    tc_result = await db.execute(
        select(func.count(ProfileReel.id))
        .where(ProfileReel.is_trending == True)  # noqa: E712
        .where(ProfileReel.is_hidden == False)  # noqa: E712
        .where(ProfileReel.profile_id == profile.id)
    )
    trending_count = tc_result.scalar() or 0

    return TrackedAuthorResponse(
        id=profile.id,
        platform=profile.platform,
        username=profile.username,
        display_name=profile.display_name,
        profile_url=profile.profile_url,
        followers_count=profile.followers_count,
        median_views=profile.median_views,
        niche=profile.niche,
        total_reels=profile.total_reels or 0,
        last_checked_at=profile.last_checked_at,
        trending_count=trending_count,
    )


@trends_router.delete("/authors/{profile_id}")
async def remove_my_author(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an author from tracking."""
    removed = await remove_user_author(db, user.id, profile_id)
    if not removed:
        raise HTTPException(404, "Author not found in your list")
    return {"ok": True}


@trends_router.get("/niches", response_model=list[NicheStats])
async def list_trend_niches(
    db: AsyncSession = Depends(get_db),
):
    """Get niche stats: how many trending reels per niche."""
    # Count trending reels per reel-level niche
    trending_q = (
        select(
            ProfileReel.niche,
            func.count(ProfileReel.id).label("trending_count"),
        )
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.is_hidden == False,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            ProfileReel.niche.isnot(None),
        )
        .group_by(ProfileReel.niche)
    )
    trending_result = await db.execute(trending_q)
    trending_map = {row.niche: row.trending_count for row in trending_result.all()}

    # Count total profiles per niche (still profile-level for context)
    profiles_q = (
        select(
            TrackedProfile.niche,
            func.count(TrackedProfile.id).label("total_profiles"),
        )
        .where(
            TrackedProfile.is_active == True,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            TrackedProfile.niche.isnot(None),
        )
        .group_by(TrackedProfile.niche)
    )
    profiles_result = await db.execute(profiles_q)
    profiles_map = {row.niche: row.total_profiles for row in profiles_result.all()}

    # Merge: include all niches that have either trending reels or profiles
    all_niches = set(trending_map.keys()) | set(profiles_map.keys())
    items = []
    for niche_slug in all_niches:
        items.append(NicheStats(
            niche=niche_slug,
            trending_count=trending_map.get(niche_slug, 0),
            total_profiles=profiles_map.get(niche_slug, 0),
        ))

    # Sort by trending count descending
    items.sort(key=lambda x: x.trending_count, reverse=True)
    return items


_ALLOWED_CDN_DOMAINS = {
    # Instagram / Facebook
    "cdninstagram.com",
    "instagram.com",
    "fbcdn.net",
    # YouTube
    "i.ytimg.com",
    "img.youtube.com",
    # TikTok
    "tiktokcdn.com",
    "p16-sign.tiktokcdn.com",
    "p77-sign.tiktokcdn.com",
}


def _is_allowed_cdn(url: str) -> bool:
    """Check that URL points to a known CDN domain."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    return any(host == d or host.endswith(f".{d}") for d in _ALLOWED_CDN_DOMAINS)


@trends_router.get("/thumbnail/{reel_id}")
async def get_trend_thumbnail(
    reel_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Serve reel thumbnail from our storage, falling back to CDN proxy."""
    from app.config import settings as app_settings
    from app.storage import storage

    result = await db.execute(
        select(ProfileReel.thumbnail_key, ProfileReel.thumbnail_url)
        .where(ProfileReel.id == reel_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    thumbnail_key, thumbnail_url = row

    # Priority 1: Serve from our persistent storage
    if thumbnail_key:
        try:
            if app_settings.s3_bucket:
                url = await storage.get_url(thumbnail_key)
                return RedirectResponse(url=url, status_code=302)
            else:
                local_path = Path(app_settings.storage_dir) / thumbnail_key
                if local_path.is_file():
                    return FileResponse(
                        local_path,
                        media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=86400"},
                    )
        except Exception:
            pass  # fall through to CDN proxy

    # Priority 2: Fallback — proxy from platform CDN
    if not thumbnail_url:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    if not _is_allowed_cdn(thumbnail_url):
        raise HTTPException(status_code=403, detail="URL not on allowed CDN")

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(thumbnail_url)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch thumbnail")

            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Failed to fetch thumbnail")


@trends_router.post("/backfill-thumbnails")
async def run_thumbnail_backfill(_admin: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    """Download and persist thumbnails for reels that lack thumbnail_key."""
    from app.services.trend_monitor import backfill_thumbnails

    count = await backfill_thumbnails(db)
    return {"persisted": count}


@trends_router.post("/repair-thumbnails")
async def run_thumbnail_repair(
    include_orphans: bool = False,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-scrape profiles to refresh expired CDN URLs, then persist thumbnails.

    Set include_orphans=true to also scrape individual reels that are too old
    to appear in profile feeds (slower, more Apify calls).
    """
    from app.services.trend_monitor import repair_thumbnails

    stats = await repair_thumbnails(db, include_orphans=include_orphans)
    return stats


@trends_router.get("/{reel_id}/frames/{frame_index}")
async def get_trend_frame(
    reel_id: str,
    frame_index: int,
    db: AsyncSession = Depends(get_db),
):
    """Serve an extracted frame for a parsed trend reel."""
    from app.config import settings as app_settings
    from app.storage import storage
    from app.storage.local import get_frames_dir

    # Resolve chain: ProfileReel → LibraryReel → Job
    result = await db.execute(
        select(LibraryReel.job_id)
        .join(ProfileReel, ProfileReel.library_reel_id == LibraryReel.id)
        .where(ProfileReel.id == reel_id)
    )
    job_id = result.scalar_one_or_none()
    if not job_id:
        raise HTTPException(status_code=404, detail="Frames not available")

    prefix = f"frames/{job_id}/frame_{frame_index:04d}_"

    # Try S3 first
    if app_settings.s3_bucket:
        try:
            keys = await storage.find_keys(prefix, limit=1)
            if keys:
                url = await storage.get_url(keys[0])
                return RedirectResponse(url=url, status_code=302)
        except Exception:
            pass

    # Fallback: local disk
    frames_dir = get_frames_dir(job_id)
    pattern = f"frame_{frame_index:04d}_*.jpg"
    matches = list(frames_dir.glob(pattern))
    if not matches:
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(
        matches[0],
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
