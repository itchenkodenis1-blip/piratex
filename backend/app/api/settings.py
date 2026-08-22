import asyncio
import logging
import re
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.auth import get_current_user, get_optional_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User, UserSettings
from app.schemas.profile import AnalyzeInstagramRequest, DeepAnalyzeRequest, UserProfile
from app.schemas.settings import UserSettingsResponse, UserSettingsUpdate

logger = logging.getLogger(__name__)
router = APIRouter()

_INSTAGRAM_USERNAME_RE = re.compile(r"^[a-zA-Z0-9._]{1,30}$")


def _profile_from_db(user_settings: UserSettings) -> UserProfile | None:
    """Deserialize profile_json into UserProfile, or None."""
    if not user_settings.profile_json:
        return None
    try:
        return UserProfile(**user_settings.profile_json)
    except Exception:
        logger.warning("Failed to deserialize profile_json for user %s", user_settings.user_id, exc_info=True)
        return None


@router.get("", response_model=UserSettingsResponse)
async def get_settings(
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        return UserSettingsResponse(language="ru")

    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        return UserSettingsResponse(language="ru")

    return UserSettingsResponse(
        language=user_settings.language or "ru",
        custom_content_prompt=user_settings.custom_content_prompt,
        custom_strategy_prompt=user_settings.custom_strategy_prompt,
        profile=_profile_from_db(user_settings),
        onboarding_completed=user_settings.onboarding_completed or False,
    )


@router.put("", response_model=UserSettingsResponse)
async def update_settings(
    payload: UserSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings:
        user_settings = UserSettings(user_id=user.id)
        db.add(user_settings)

    if payload.language is not None:
        user_settings.language = payload.language
    if payload.custom_content_prompt is not None:
        # Empty string = reset to default (store as NULL)
        user_settings.custom_content_prompt = payload.custom_content_prompt or None
    if payload.custom_strategy_prompt is not None:
        user_settings.custom_strategy_prompt = payload.custom_strategy_prompt or None
    if payload.profile is not None:
        # Merge incoming profile fields with existing (preserve fields not in this update)
        existing = dict(user_settings.profile_json or {})
        new_fields = payload.profile.model_dump(exclude_none=True)
        existing.update(new_fields)
        user_settings.profile_json = existing or None
        flag_modified(user_settings, "profile_json")
    if payload.onboarding_completed is not None:
        user_settings.onboarding_completed = payload.onboarding_completed

    # Audit log: track prompt/profile changes
    changed_fields = []
    if payload.custom_content_prompt is not None:
        changed_fields.append("custom_content_prompt")
    if payload.custom_strategy_prompt is not None:
        changed_fields.append("custom_strategy_prompt")
    if payload.profile is not None:
        profile_fields = list(payload.profile.model_dump(exclude_none=True).keys())
        if profile_fields:
            changed_fields.append(f"profile({','.join(profile_fields)})")
    if changed_fields:
        logger.info("Settings updated by user %s: %s", user.id, ", ".join(changed_fields))

    await db.commit()
    await db.refresh(user_settings)

    return UserSettingsResponse(
        language=user_settings.language or "ru",
        custom_content_prompt=user_settings.custom_content_prompt,
        custom_strategy_prompt=user_settings.custom_strategy_prompt,
        profile=_profile_from_db(user_settings),
        onboarding_completed=user_settings.onboarding_completed or False,
    )


@router.get("/radar")
async def get_radar_settings(
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current Content Radar notification preferences with defaults."""
    defaults = {
        "radar_enabled": True,
        "radar_mode": "instant",
        "radar_min_x_factor": 3.0,
        "radar_niches": None,
        "radar_quiet_hours": True,
        "has_telegram": False,
    }

    if not user:
        return defaults

    defaults["has_telegram"] = user.telegram_user_id is not None

    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    if not user_settings or not user_settings.profile_json:
        return defaults

    profile = _profile_from_db(user_settings)
    if not profile:
        return defaults

    return {
        "radar_enabled": profile.radar_enabled if profile.radar_enabled is not None else True,
        "radar_mode": profile.radar_mode or "instant",
        "radar_min_x_factor": profile.radar_min_x_factor or 3.0,
        "radar_niches": profile.radar_niches,
        "radar_quiet_hours": profile.radar_quiet_hours if profile.radar_quiet_hours is not None else True,
        "has_telegram": user.telegram_user_id is not None,
    }


@router.get("/interests")
async def get_interests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return user's saved interests + auto-detected suggestions from parsed reels."""
    from app.services.niche_inference import infer_user_interests

    # Get saved interests from profile
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = result.scalar_one_or_none()

    saved_interests: list[str] = []
    if user_settings and user_settings.profile_json:
        try:
            profile = UserProfile(**user_settings.profile_json)
            saved_interests = profile.interests or []
        except Exception:
            pass

    # Auto-detect from parsed reels
    detected = await infer_user_interests(db, user.id, top_n=30)

    # Split into saved and suggested (not yet saved)
    saved_set = set(saved_interests)
    suggested = [d for d in detected if d["topic"] not in saved_set]

    return {
        "interests": saved_interests,
        "suggested": suggested,
    }


@router.get("/default-prompts")
async def get_default_prompts(user: User = Depends(get_current_user)):
    """Return default prompts so users can reset or use as a starting point."""
    if user.tier not in ("START", "PRO", "UNLIMITED"):
        return {"content_prompt": "", "strategy_prompt": ""}

    from app.services.summarizer import DEFAULT_CONTENT_PROMPT
    from app.services.strategist import DEFAULT_STRATEGY_PROMPT

    return {
        "content_prompt": DEFAULT_CONTENT_PROMPT,
        "strategy_prompt": DEFAULT_STRATEGY_PROMPT,
    }


@router.get("/profile-presets")
async def get_profile_presets(user: User = Depends(get_current_user)):
    """Return tone and video format presets for the profile editor."""
    from app.services.prompt_composer import (
        DEFAULT_ABOUT_ME,
        DEFAULT_DESCRIPTION_CTA,
        DEFAULT_FORBIDDEN_WORDS,
        DEFAULT_SCRIPT_CTA,
        TONE_LABELS,
        TONE_PRESETS,
        VIDEO_FORMAT_LABELS,
        VIDEO_FORMAT_PRESETS,
    )

    return {
        "tone_presets": {
            key: {"text": text, "labels": TONE_LABELS[key]}
            for key, text in TONE_PRESETS.items()
        },
        "video_format_presets": {
            key: {"text": text, "labels": VIDEO_FORMAT_LABELS[key]}
            for key, text in VIDEO_FORMAT_PRESETS.items()
        },
        "defaults": {
            "about_me": DEFAULT_ABOUT_ME,
            "script_cta": DEFAULT_SCRIPT_CTA,
            "description_cta": DEFAULT_DESCRIPTION_CTA,
            "forbidden_words": DEFAULT_FORBIDDEN_WORDS,
        },
    }


@router.post("/analyze-instagram")
async def analyze_instagram(
    request: Request,
    body: AnalyzeInstagramRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Analyze user's Instagram profile to extract interests for personalization."""
    # Rate limit by user_id: 1/hour + 10/month
    from app.core.redis_pool import get_redis
    redis = await get_redis()
    if redis:
        hour_key = f"ig_analyze:hour:{user.id}"
        month_key = f"ig_analyze:month:{user.id}"
        if await redis.get(hour_key):
            raise HTTPException(429, detail="Можно анализировать профиль раз в час.")
        month_count = await redis.get(month_key)
        if month_count and int(month_count) >= 10:
            raise HTTPException(429, detail="Лимит: 10 анализов профиля в месяц.")

    username = body.username.strip().lstrip("@").lower()
    if not username or not _INSTAGRAM_USERNAME_RE.match(username):
        raise HTTPException(400, detail="Invalid Instagram username")

    # 1. Scrape profile via Apify
    from app.services.trend_monitor import _scrape_instagram_profile
    profile_data = await _scrape_instagram_profile(username)
    if not profile_data:
        raise HTTPException(404, detail="Profile not found or private")

    # 2. Extract bio + captions
    bio = profile_data.get("biography", "") or ""
    posts = profile_data.get("latestPosts", []) or profile_data.get("posts", [])
    captions = [p.get("caption", "") or "" for p in posts[:12] if p.get("caption")]
    text_for_analysis = f"Bio: {bio}\n\nRecent posts:\n" + "\n---\n".join(captions)

    if len(text_for_analysis.strip()) < 20:
        raise HTTPException(400, detail="Not enough content to analyze")

    # 3. AI analysis via Haiku
    from app.services.trend_monitor import _infer_niche_from_captions, _infer_topics_from_captions
    niche = await _infer_niche_from_captions(text_for_analysis)
    topics = await _infer_topics_from_captions(text_for_analysis) or []

    # 4. Record signals
    from app.services.interest_signals import record_signals
    all_topics = topics + ([niche] if niche else [])
    signals_count = await record_signals(
        db, user_id=user.id, topics=all_topics,
        source="instagram", weight=0.8, source_id=username,
    )

    # 5. Optionally enrich user profile
    settings_row = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_row.scalar_one_or_none()
    if user_settings and user_settings.profile_json:
        try:
            profile = UserProfile(**user_settings.profile_json)
            if not profile.niches and niche:
                profile.niches = [niche]
            if not profile.interests and topics:
                profile.interests = topics[:15]
            user_settings.profile_json = profile.model_dump(exclude_none=True)
        except Exception:
            pass

    await db.commit()

    # Record successful analysis in Redis rate counters
    if redis:
        await redis.set(hour_key, "1", ex=3600)  # 1 hour cooldown
        await redis.incr(month_key)
        # Set TTL on month key if it's new (30 days)
        if not month_count:
            await redis.expire(month_key, 30 * 86400)

    return {
        "username": username,
        "niche": niche,
        "topics": topics,
        "signals_count": signals_count,
    }


@router.post("/deep-analyze")
async def deep_analyze_instagram(
    request: Request,
    body: DeepAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Deep-analyze user's Instagram blog: download reels, transcribe, analyze frames, generate profile."""
    username = body.username.strip().lstrip("@").lower()
    if not username or not _INSTAGRAM_USERNAME_RE.match(username):
        raise HTTPException(400, detail="Invalid Instagram username")

    # Validate analysis_id if provided (must be valid UUID), otherwise generate server-side
    analysis_id = str(uuid4())
    if body.analysis_id:
        try:
            from uuid import UUID
            UUID(body.analysis_id, version=4)
            analysis_id = body.analysis_id
        except ValueError:
            pass  # Ignore invalid client IDs, use server-generated

    # Concurrency lock — prevent parallel analyses per user
    from app.core.redis_pool import get_redis as _get_redis
    lock_key = f"deep_analysis_lock:{user.id}"
    redis = await _get_redis()

    # Rate limit by user_id: 1/hour + 10/month
    if redis:
        hour_key = f"ig_deep:hour:{user.id}"
        month_key = f"ig_deep:month:{user.id}"
        if await redis.get(hour_key):
            raise HTTPException(429, detail="Можно анализировать профиль раз в час.")
        month_count = await redis.get(month_key)
        if month_count and int(month_count) >= 10:
            raise HTTPException(429, detail="Лимит: 10 анализов профиля в месяц.")
    if redis:
        existing = await redis.get(lock_key)
        if existing:
            raise HTTPException(429, detail="Analysis already in progress, please wait")
        await redis.set(lock_key, "1", ex=600)  # 10 min TTL

    from app.services.blog_analyzer import (
        EmptyProfileError,
        ProfileGenerationError,
        ProfileNotFoundError,
        analyze_blog,
    )
    from app.models.user import ProfileParsing
    import time as _time

    # Record parsing run
    parsing = ProfileParsing(
        user_id=user.id,
        analysis_id=analysis_id,
        platform="instagram",
        username=username,
        status="running",
    )
    db.add(parsing)
    await db.commit()

    _start_time = _time.monotonic()

    try:
        result = await asyncio.wait_for(
            analyze_blog(username, analysis_id=analysis_id),
            timeout=480,  # 8 min hard cap — prevents infinite hangs
        )
    except asyncio.TimeoutError:
        logger.error("Deep-analyze timed out (480s) for user %s, @%s", user.id, username)
        parsing.status = "failed"
        parsing.error = "Analysis timed out (8 min limit)"
        parsing.duration_seconds = round(_time.monotonic() - _start_time, 1)
        await db.commit()
        raise HTTPException(504, detail="Analysis timed out. Please try again later.")
    except ProfileNotFoundError:
        parsing.status = "failed"
        parsing.error = "Profile not found or private"
        parsing.duration_seconds = round(_time.monotonic() - _start_time, 1)
        await db.commit()
        raise HTTPException(404, detail="Profile not found or private")
    except EmptyProfileError:
        parsing.status = "failed"
        parsing.error = "Profile has no posts to analyze"
        parsing.duration_seconds = round(_time.monotonic() - _start_time, 1)
        await db.commit()
        raise HTTPException(400, detail="У профиля нет постов для анализа. Добавьте хотя бы несколько публикаций.")
    except ProfileGenerationError:
        parsing.status = "failed"
        parsing.error = "Failed to generate profile from analysis"
        parsing.duration_seconds = round(_time.monotonic() - _start_time, 1)
        await db.commit()
        raise HTTPException(500, detail="Failed to generate profile from analysis")
    except Exception as exc:
        logger.exception("Unhandled error in deep-analyze for user %s, @%s", user.id, username)
        parsing.status = "failed"
        parsing.error = str(exc)[:500]
        parsing.duration_seconds = round(_time.monotonic() - _start_time, 1)
        await db.commit()
        raise HTTPException(500, detail="Internal error during analysis. Please try again later.")
    finally:
        # Release concurrency lock
        if redis:
            await redis.delete(lock_key)
        # Safety net: if parsing is still "running" (e.g. CancelledError, unexpected BaseException),
        # mark it failed so it doesn't stay stuck forever
        if parsing.status == "running":
            try:
                parsing.status = "failed"
                parsing.error = "Analysis interrupted (connection lost or server timeout)"
                parsing.duration_seconds = round(_time.monotonic() - _start_time, 1)
                await db.commit()
            except Exception:
                logger.warning("Failed to mark parsing %s as failed in finally block", parsing.id)

    # Mark parsing as completed
    parsing.status = "completed"
    parsing.duration_seconds = round(_time.monotonic() - _start_time, 1)
    parsing.completed_at = datetime.utcnow()
    parsing.result_json = result.model_dump()

    # Save results to UserSettings
    settings_row = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_row.scalar_one_or_none()

    if not user_settings:
        user_settings = UserSettings(user_id=user.id)
        db.add(user_settings)

    # Build profile from result
    profile = UserProfile(
        about_me=result.about_me,
        tone=result.tone,
        niches=result.niches,
        interests=result.interests,
        video_format=result.video_format,
        script_cta=result.script_cta,
        description_cta=result.description_cta,
        forbidden_words=result.forbidden_words,
        content_prompt_additions=result.content_prompt_additions,
    )
    user_settings.profile_json = profile.model_dump(exclude_none=True)

    # Save raw analysis results
    user_settings.blog_analysis_json = result.model_dump()

    # Mark onboarding as completed
    user_settings.onboarding_completed = True

    # Record interest signals (non-critical — don't block profile save)
    try:
        from app.services.interest_signals import record_signals
        await record_signals(
            db, user_id=user.id,
            topics=result.interests + result.niches,
            source="instagram_deep", weight=1.0, source_id=username,
        )
    except Exception:
        logger.warning("Failed to record interest signals for user %s", user.id, exc_info=True)

    await db.commit()

    # Record successful analysis in Redis rate counters
    if redis:
        await redis.set(hour_key, "1", ex=3600)
        await redis.incr(month_key)
        if not month_count:
            await redis.expire(month_key, 30 * 86400)

    logger.info("Deep analysis completed for user %s, username @%s", user.id, username)

    return {
        "analysis_id": analysis_id,
        **result.model_dump(),
    }


# ---------------------------------------------------------------------------
# Delete Account (GDPR Article 17 — right to erasure)
# ---------------------------------------------------------------------------

@router.delete("/me")
@limiter.limit("3/hour")
async def delete_my_account(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Permanently delete the current user's account and all associated data.
    GDPR Article 17 — right to erasure.
    """
    if user.is_anonymous:
        raise HTTPException(status_code=400, detail="Anonymous users cannot delete accounts")

    user_id = user.id
    logger.info("Account deletion requested by user %s (%s)", user_id, user.email)

    # 1. Cancel active subscription (if any)
    try:
        from app.services.billing import cancel_subscription
        await cancel_subscription(db, user)
    except Exception:
        logger.warning("Failed to cancel subscription for user %s during deletion", user_id, exc_info=True)

    # 2. Clean up storage files for all user's jobs
    try:
        from app.models.job import Job
        from app.services.storage_cleanup import cleanup_job_storage
        job_ids = (await db.execute(select(Job.id).where(Job.user_id == user_id))).scalars().all()
        for jid in job_ids:
            await cleanup_job_storage(jid)
    except Exception:
        logger.warning("Failed to clean up storage for user %s during deletion", user_id, exc_info=True)

    # 3. Delete the user — CASCADE handles all related records
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()

    # 4. Clear auth cookies
    response.delete_cookie("piratex_auth")
    response.delete_cookie("piratex_session")

    logger.info("Account deleted: user %s", user_id)

    return {"deleted": True}
