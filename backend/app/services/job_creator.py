"""Shared job creation logic, used by both HTTP API and Telegram webhook.

Extracts the core flow from api/jobs.py: dedup, tier enforcement, job creation,
and arq enqueueing. Returns a typed result so callers can format responses
appropriate to their channel (HTTP JSON vs Telegram message).
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.models.library import LibraryReel
from app.models.user import User, UserSettings
from app.services.scraper._platform import normalize_url, validate_video_url
from app.services.usage import check_can_create_analysis

logger = logging.getLogger(__name__)

PENDING_STALE_MINUTES = 10  # active job older than this is treated as a zombie

Outcome = Literal[
    "created",
    "existing_completed",
    "existing_in_progress",
    "limit_exceeded",
    "activation_required",
    "queue_unavailable",
]


@dataclass
class JobCreationResult:
    outcome: Outcome
    job: Job | None = None
    library_reel_id: str | None = None
    share_token: str | None = None
    used: int = 0
    limit: int = 0
    detail: str | None = None


async def create_job_from_url(
    db: AsyncSession,
    user: User,
    url: str,
    arq_pool,
    *,
    source: str = "web",
    telegram_chat_id: str | None = None,
    telegram_message_id: int | None = None,
    client_ip: str | None = None,
) -> JobCreationResult:
    """Create a job from a URL with full dedup and tier enforcement.

    This is the shared core extracted from api/jobs.py POST /jobs.
    """
    # Reject invalid/malicious URLs before creating a job or touching the DB
    from app.core.exceptions import InvalidURLError

    rejection = validate_video_url(url)
    if rejection:
        logger.warning("URL_REJECTED url=%s reason=%s user=%s", url, rejection, user.id)
        raise InvalidURLError(rejection)

    url_str = normalize_url(url)

    # Advisory lock to prevent concurrent duplicate job creation
    # Use hashlib (not hash()) for deterministic results across processes
    lock_key = int(hashlib.sha256(f"{user.id}:{url_str}".encode()).hexdigest(), 16) % (2**31)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})

    # Fast-path 1: User's completed job with same URL
    existing_job_result = await db.execute(
        select(Job).where(
            Job.user_id == user.id,
            Job.url == url_str,
            Job.status == JobStatus.COMPLETED,
        ).order_by(Job.created_at.desc()).limit(1)
    )
    existing_job = existing_job_result.scalar_one_or_none()
    if existing_job:
        return JobCreationResult(
            outcome="existing_completed",
            job=existing_job,
            library_reel_id=existing_job.library_reel_id,
            share_token=existing_job.share_token,
        )

    # Fast-path 2: Active job for same URL by this user
    # (checked BEFORE library_hit to avoid creating duplicate cached replay jobs)
    active_result = await db.execute(
        select(Job).where(
            Job.user_id == user.id,
            Job.url == url_str,
            Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]),
        ).order_by(Job.created_at.desc()).limit(1)
    )
    active_job = active_result.scalar_one_or_none()
    if active_job:
        # A "zombie" — job exists in DB but never got picked up by a worker
        # (lost from the arq queue on a restart) and has gone stale. It will
        # never progress on its own, so fail it and let a fresh job supersede
        # it instead of letting the UI hang on it forever.
        zombie_cutoff = datetime.utcnow() - timedelta(minutes=PENDING_STALE_MINUTES)
        is_zombie = active_job.updated_at is not None and active_job.updated_at < zombie_cutoff
        if is_zombie:
            active_job.status = JobStatus.FAILED
            active_job.error = f"Задача зависла при обработке (последнее обновление {active_job.updated_at:%H:%M:%S}) — запущена заново"
            await db.commit()
            logger.info(
                "URL_DEDUP_ZOMBIE_FOUND job=%s url=%s user=%s — failing & creating new",
                active_job.id, url_str, user.id,
            )
        else:
            return JobCreationResult(
                outcome="existing_in_progress",
                job=active_job,
            )

    # Fast-path 3: URL parsed by another user — cached replay
    # Instead of returning library_hit instantly, create a real Job
    # that replays cached data with progress animation, then generates
    # a personalized script for this user.
    lib_result = await db.execute(
        select(LibraryReel).where(LibraryReel.url == url_str).limit(1)
    )
    lib_reel = lib_result.scalar_one_or_none()
    if lib_reel:
        # Lock user row (same as new-job path)
        await db.execute(
            select(User).where(User.id == user.id).with_for_update()
        )

        # Tier enforcement — cached replay costs 1 analysis
        can, used, limit, detail = await check_can_create_analysis(db, user)
        if not can:
            if detail == "activation_required":
                return JobCreationResult(
                    outcome="activation_required",
                    used=used, limit=limit, detail=detail,
                )
            # Onboarding drip: FREE limit reached
            if detail == "monthly_limit" and (user.tier or "").upper() == "FREE":
                try:
                    from app.services.onboarding_drip import drip_free_limit_reached
                    await drip_free_limit_reached(user)
                except Exception:
                    pass
            return JobCreationResult(
                outcome="limit_exceeded",
                used=used, limit=limit, detail=detail,
            )

        # Load user settings for personalized script generation
        us_result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        user_settings = us_result.scalar_one_or_none()

        language = (user_settings.language if user_settings and user_settings.language else "ru")
        custom_content_prompt = user_settings.custom_content_prompt if user_settings else None
        custom_strategy_prompt = user_settings.custom_strategy_prompt if user_settings else None
        profile_json = user_settings.profile_json if user_settings else None

        if not arq_pool:
            return JobCreationResult(
                outcome="queue_unavailable",
                detail="Task queue unavailable",
            )

        # Create Job WITHOUT metadata/transcript/frames — task_cached_replay
        # will load them from LibraryReel and broadcast with delays.
        # This prevents _send_current_state from leaking all data instantly
        # on WebSocket connect (defeating the progress animation).
        job = Job(
            url=url_str,
            user_id=user.id,
            status=JobStatus.PENDING,
            source=source,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            library_reel_id=lib_reel.id,
            client_ip=client_ip,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        # Enqueue cached replay task
        enqueue_kwargs: dict = {}
        if detail == "throttled" and used and limit:
            enqueue_kwargs["_defer_by"] = timedelta(minutes=10)

        await arq_pool.enqueue_job(
            "task_cached_replay",
            job.id,
            language,
            custom_content_prompt,
            custom_strategy_prompt,
            profile_json,
            **enqueue_kwargs,
        )

        try:
            from app.core.showcase_tracker import emit_showcase_event

            await emit_showcase_event("analysis")
        except Exception:
            pass

        return JobCreationResult(
            outcome="created",
            job=job,
            share_token=job.share_token,
            used=used, limit=limit, detail=detail,
        )

    # Lock user row to serialise concurrent requests (TOCTOU protection)
    await db.execute(
        select(User).where(User.id == user.id).with_for_update()
    )

    # Tier enforcement
    can, used, limit, detail = await check_can_create_analysis(db, user)
    if not can:
        if detail == "activation_required":
            return JobCreationResult(
                outcome="activation_required",
                used=used, limit=limit, detail=detail,
            )
        # Onboarding drip: FREE limit reached
        if detail == "monthly_limit" and (user.tier or "").upper() == "FREE":
            try:
                from app.services.onboarding_drip import drip_free_limit_reached
                await drip_free_limit_reached(user)
            except Exception:
                pass
        return JobCreationResult(
            outcome="limit_exceeded",
            used=used, limit=limit, detail=detail,
        )

    # Load user settings
    us_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = us_result.scalar_one_or_none()

    language = (user_settings.language if user_settings and user_settings.language else "ru")
    custom_content_prompt = user_settings.custom_content_prompt if user_settings else None
    custom_strategy_prompt = user_settings.custom_strategy_prompt if user_settings else None
    profile_json = user_settings.profile_json if user_settings else None

    # Check arq_pool BEFORE creating job to avoid orphaned records
    if not arq_pool:
        return JobCreationResult(
            outcome="queue_unavailable",
            detail="Task queue unavailable",
        )

    # Create job
    job = Job(
        url=url_str,
        user_id=user.id,
        status=JobStatus.PENDING,
        source=source,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
        client_ip=client_ip,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Throttle for UNLIMITED users past soft cap
    enqueue_kwargs: dict = {}
    if detail == "throttled" and used and limit:
        enqueue_kwargs["_defer_by"] = timedelta(minutes=10)

    await arq_pool.enqueue_job(
        "task_scrape_and_download",
        job.id,
        url_str,
        language,
        custom_content_prompt,
        custom_strategy_prompt,
        profile_json,
        **enqueue_kwargs,
    )

    try:
        from app.core.showcase_tracker import emit_showcase_event

        await emit_showcase_event("analysis")
    except Exception:
        pass

    return JobCreationResult(
        outcome="created",
        job=job,
        share_token=job.share_token,
        used=used, limit=limit, detail=detail,
    )
