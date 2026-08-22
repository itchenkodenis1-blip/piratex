import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anonymous import ensure_user
from app.core.auth import get_current_user
from app.core.exceptions import InvalidURLError
from app.core.rate_limit import limiter
from app.database import get_db
from app.core.error_classifier import get_user_friendly_error
from app.models.feedback import ScriptRating
from app.models.job import Job, JobStatus
from app.models.trends import ProfileReel
from app.models.user import User
from app.schemas.feedback import RateJobRequest, RatingResponse
from app.schemas.job import JobCardResponse, JobCreate, JobListResponse, JobResultResponse, JobStatusResponse, UpdateJobFieldsRequest
from app.services.job_creator import create_job_from_url
from app.services.teaser import build_teaser_result
from app.storage.local import get_frames_dir

logger = logging.getLogger(__name__)

router = APIRouter()


_TIER_RATE_LIMITS = {
    "ANONYMOUS": 30,
    "FREE": 5,
    "START": 10,
    "PRO": 15,
    "UNLIMITED": 30,
}


@router.post("", response_model=JobStatusResponse)
@limiter.limit("30/minute")  # global ceiling, tier limits enforced below
async def create_job(
    payload: JobCreate,
    request: Request,
    user: User = Depends(ensure_user),
    db: AsyncSession = Depends(get_db),
):
    client_ip = get_remote_address(request)

    # Turnstile verification for anonymous users (bot protection)
    if user.is_anonymous:
        from app.core.turnstile import verify_turnstile

        if not await verify_turnstile(payload.turnstile_token or "", client_ip):
            raise HTTPException(status_code=403, detail="captcha_failed")

    # Tier-based rate limiting: count jobs created in last minute
    from datetime import datetime, timedelta

    one_min_ago = datetime.utcnow() - timedelta(minutes=1)
    recent_jobs = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.user_id == user.id,
            Job.created_at >= one_min_ago,
        )
    )
    recent_count = recent_jobs.scalar() or 0
    tier_limit = _TIER_RATE_LIMITS.get(user.tier, 5)
    if recent_count >= tier_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Лимит запросов: {tier_limit}/мин для вашего тарифа.",
        )

    # IP-based abuse detection for anonymous users:
    # Block IPs with too many failed jobs (sign of scanning/attack)
    if user.is_anonymous and client_ip:
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        failed_by_ip = await db.execute(
            select(func.count()).select_from(Job).where(
                Job.client_ip == client_ip,
                Job.status == JobStatus.FAILED,
                Job.created_at >= one_hour_ago,
            )
        )
        ip_failed_count = failed_by_ip.scalar() or 0
        if ip_failed_count >= 5:
            logger.warning(
                "ABUSE_BLOCKED ip=%s user=%s failed_1h=%d url=%s",
                client_ip, user.id, ip_failed_count, str(payload.url),
            )
            raise HTTPException(
                status_code=429,
                detail="Too many failed requests. Please try again later.",
            )

    # Dedup: if this IP already has a pending/processing job for the same URL, return it
    if user.is_anonymous and client_ip:
        from app.services.scraper._platform import normalize_url
        try:
            normalized = normalize_url(str(payload.url))
        except Exception:
            normalized = str(payload.url)
        existing_dup = await db.execute(
            select(Job).where(
                Job.client_ip == client_ip,
                Job.url == normalized,
                Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]),
            ).limit(1)
        )
        dup_job = existing_dup.scalar_one_or_none()
        if dup_job:
            logger.info("DEDUP_HIT ip=%s job=%s url=%s", client_ip, dup_job.id, normalized)
            return JobStatusResponse(
                job_id=dup_job.id,
                status=dup_job.status,
                progress=dup_job.progress,
            )

    managed = getattr(request.app.state, "managed_arq_pool", None)
    arq_pool = await managed.get_pool() if managed else getattr(request.app.state, "arq_pool", None)
    if not arq_pool:
        raise HTTPException(status_code=503, detail="Task queue unavailable. Please try again later.")

    # Backpressure: reject low-tier users when queue is overloaded
    try:
        queue_depth = await arq_pool.zcard(b"arq:queue")
    except Exception:
        queue_depth = 0

    if queue_depth > 100 and user.tier not in ("UNLIMITED",):
        raise HTTPException(
            status_code=503,
            detail="Сервис загружен. Попробуйте через несколько минут.",
        )
    if queue_depth > 50 and user.tier in ("FREE", "ANONYMOUS"):
        raise HTTPException(
            status_code=503,
            detail="Сервис загружен. Попробуйте через несколько минут.",
        )

    try:
        result = await create_job_from_url(
            db, user, str(payload.url), arq_pool, source="web",
            client_ip=client_ip,
        )
    except InvalidURLError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if result.outcome == "existing_completed":
        return JobStatusResponse(
            job_id=result.job.id,
            status=result.job.status,
            progress=result.job.progress,
            share_token=result.job.share_token,
            library_reel_id=result.job.library_reel_id,
        )

    # NOTE: "library_hit" outcome is no longer returned by job_creator —
    # it now creates a cached replay job instead (outcome="created").

    if result.outcome == "existing_in_progress":
        return JobStatusResponse(
            job_id=result.job.id,
            status=result.job.status,
            progress=result.job.progress,
        )

    if result.outcome == "queue_unavailable":
        raise HTTPException(status_code=503, detail="Task queue unavailable. Please try again later.")

    if result.outcome in ("limit_exceeded", "activation_required"):
        raise HTTPException(
            status_code=429,
            detail={"detail": result.detail, "meta": {"used": result.used, "limit": result.limit}},
        )

    # outcome == "created"
    return JobStatusResponse(
        job_id=result.job.id,
        status=result.job.status,
        progress=result.job.progress,
        share_token=result.job.share_token,
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status_filter: str = Query("", description="Filter: processing, completed, failed"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(ensure_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's jobs for 'My Videos' page."""
    query = select(Job).where(Job.user_id == user.id, Job.is_hidden != True)

    if status_filter == "processing":
        query = query.where(Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]))
    elif status_filter == "completed":
        query = query.where(Job.status == JobStatus.COMPLETED)
    elif status_filter == "failed":
        query = query.where(Job.status == JobStatus.FAILED)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(Job.created_at.desc())
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    jobs = result.scalars().all()

    # Look up x_factor from ProfileReel by matching URLs
    url_to_xfactor: dict[str, float | None] = {}
    if jobs:
        job_urls = [j.url for j in jobs]
        # ProfileReel URLs may have trailing slash, Job URLs are normalized without
        all_urls = list(set(job_urls + [u + "/" for u in job_urls]))
        pr_result = await db.execute(
            select(ProfileReel.url, ProfileReel.x_factor)
            .where(ProfileReel.url.in_(all_urls))
        )
        for pr_url, xf in pr_result:
            url_to_xfactor[pr_url.rstrip("/")] = xf

    # Look up UserScript id + production_status for completed jobs with library_reel_id
    from app.models.library import UserScript as US

    reel_ids = [j.library_reel_id for j in jobs if j.library_reel_id]
    script_map: dict[str, tuple[str, str | None]] = {}  # library_reel_id -> (script_id, production_status)
    if reel_ids:
        us_result = await db.execute(
            select(US.library_reel_id, US.id, US.production_status)
            .where(US.user_id == user.id, US.library_reel_id.in_(reel_ids))
        )
        for lr_id, s_id, p_status in us_result:
            script_map[lr_id] = (s_id, p_status)

    items = [
        JobCardResponse(
            job_id=j.id,
            url=j.url,
            status=j.status,
            progress=j.progress,
            progress_message=j.progress_message,
            video_title=j.video_title,
            video_duration=j.video_duration,
            video_platform=j.video_platform,
            video_author=j.video_author,
            video_views=j.video_views,
            video_likes=j.video_likes,
            video_comments=j.video_comments,
            thumbnail_url=j.thumbnail_url,
            is_filmed=j.is_filmed or False,
            library_reel_id=j.library_reel_id,
            share_token=j.share_token,
            x_factor=url_to_xfactor.get(j.url.rstrip("/")),
            user_script_id=script_map[j.library_reel_id][0] if j.library_reel_id and j.library_reel_id in script_map else None,
            production_status=script_map[j.library_reel_id][1] if j.library_reel_id and j.library_reel_id in script_map else None,
            created_at=j.created_at,
            completed_at=j.completed_at,
            error=get_user_friendly_error(j.error) if j.error else None,
        )
        for j in jobs
    ]

    return JobListResponse(items=items, total=total, page=page, per_page=per_page)


@router.patch("/{job_id}/filmed")
async def toggle_filmed(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle the 'filmed' status of a job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.is_filmed = not (job.is_filmed or False)
    await db.commit()
    return {"ok": True, "is_filmed": job.is_filmed}


@router.delete("/{job_id}")
async def hide_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hide a job from the user's 'My Videos' list (soft delete)."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job.is_hidden = True
    await db.commit()
    return {"ok": True}


@router.patch("/{job_id}/fields")
async def update_job_fields(
    job_id: str,
    body: UpdateJobFieldsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update individual fields in adaptation_summary (e.g. after refine)."""
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.user_id == user.id,
            Job.status == JobStatus.COMPLETED,
        )
    )
    job = result.scalar_one_or_none()
    if not job or not job.adaptation_summary:
        raise HTTPException(status_code=404, detail="Job not found")

    summary = dict(job.adaptation_summary)
    updated = False
    for key in ("script", "description", "editor_instructions"):
        value = getattr(body, key)
        if value is not None:
            summary[key] = value
            updated = True

    if updated:
        job.adaptation_summary = summary

        # Sync changes to UserScript so Library shows the updated text
        if job.library_reel_id:
            from app.models.library import UserScript

            us_result = await db.execute(
                select(UserScript).where(
                    UserScript.user_id == user.id,
                    UserScript.library_reel_id == job.library_reel_id,
                )
            )
            user_script = us_result.scalar_one_or_none()
            if user_script:
                # Backfill original_* for records created before this feature
                if not user_script.original_script:
                    user_script.original_script = user_script.script
                    user_script.original_description = user_script.description
                    user_script.original_editor_instructions = user_script.editor_instructions
                for key in ("script", "description", "editor_instructions"):
                    value = getattr(body, key)
                    if value is not None:
                        setattr(user_script, key, value)
            else:
                # Create UserScript if it doesn't exist yet
                user_script = UserScript(
                    user_id=user.id,
                    library_reel_id=job.library_reel_id,
                    script=summary.get("script", ""),
                    description=summary.get("description", ""),
                    editor_instructions=summary.get("editor_instructions", ""),
                    original_script=summary.get("script", ""),
                    original_description=summary.get("description", ""),
                    original_editor_instructions=summary.get("editor_instructions", ""),
                )
                db.add(user_script)

        await db.commit()

    return {"ok": True}


@router.post("/{job_id}/rate", response_model=RatingResponse)
async def rate_job(
    job_id: str,
    body: RateJobRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rate a completed job (1-5 stars). Upserts: one rating per user per job."""
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            Job.user_id == user.id,
            Job.status == JobStatus.COMPLETED,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Completed job not found")

    # Upsert: find existing or create
    existing = await db.execute(
        select(ScriptRating).where(
            ScriptRating.user_id == user.id,
            ScriptRating.job_id == job_id,
        )
    )
    rating = existing.scalar_one_or_none()
    is_update = rating is not None
    if rating:
        rating.rating = body.rating
        rating.comment = body.comment
    else:
        rating = ScriptRating(
            user_id=user.id,
            job_id=job_id,
            rating=body.rating,
            comment=body.comment,
        )
        db.add(rating)

    await db.commit()
    await db.refresh(rating)

    # Emit showcase event for real-time dashboard
    try:
        from app.core.showcase_tracker import emit_showcase_event

        # Mask email: "user@mail.com" → "us***@mail.com"
        masked = ""
        if user.email:
            local, _, domain = user.email.partition("@")
            if len(local) <= 2:
                masked = f"{local[0]}***@{domain}" if local else f"***@{domain}"
            else:
                masked = f"{local[:2]}***@{domain}"

        await emit_showcase_event(
            "rating",
            rating=str(rating.rating),
            has_comment=str(bool(rating.comment)),
            user_id=str(user.id),
            is_update=str(is_update),
            masked_email=masked,
        )
    except Exception:
        pass  # best-effort, never block rating flow

    return RatingResponse(
        rating=rating.rating,
        comment=rating.comment,
        created_at=rating.created_at,
    )


@router.get("/{job_id}/rating", response_model=RatingResponse)
async def get_rating(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's rating for a job."""
    result = await db.execute(
        select(ScriptRating).where(
            ScriptRating.user_id == user.id,
            ScriptRating.job_id == job_id,
        )
    )
    rating = result.scalar_one_or_none()
    if not rating:
        raise HTTPException(status_code=404, detail="No rating found")
    return RatingResponse(
        rating=rating.rating,
        comment=rating.comment,
        created_at=rating.created_at,
    )


@router.get("/{job_id}", response_model=JobResultResponse)
async def get_job(
    job_id: str,
    user: User = Depends(ensure_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Look up UserScript for pipeline info
    script_id = None
    prod_status = None
    if job.library_reel_id:
        from app.models.library import UserScript as US
        us_result = await db.execute(
            select(US.id, US.production_status)
            .where(US.user_id == user.id, US.library_reel_id == job.library_reel_id)
        )
        us_row = us_result.first()
        if us_row:
            script_id, prod_status = us_row

    # Look up user's rating for this job
    my_rating = None
    if not user.is_anonymous and job.status == JobStatus.COMPLETED:
        rating_result = await db.execute(
            select(ScriptRating.rating).where(
                ScriptRating.user_id == user.id,
                ScriptRating.job_id == job_id,
            )
        )
        my_rating = rating_result.scalar_one_or_none()

    return JobResultResponse(
        job_id=job.id,
        url=job.url,
        status=job.status,
        progress=job.progress,
        video_title=job.video_title,
        video_duration=job.video_duration,
        video_platform=job.video_platform,
        video_author=job.video_author,
        video_description=job.video_description,
        video_views=job.video_views,
        video_likes=job.video_likes,
        video_comments=job.video_comments,
        transcript=job.transcript,
        frames=job.frames,
        adaptation_summary=job.adaptation_summary,
        share_token=job.share_token,
        library_reel_id=job.library_reel_id,
        user_script_id=script_id,
        production_status=prod_status,
        my_rating=my_rating,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error=get_user_friendly_error(job.error) if job.error else None,
    )


@router.get("/{job_id}/frames/{frame_index}")
async def get_frame_image(
    job_id: str,
    frame_index: int,
    user: User = Depends(ensure_user),
    db: AsyncSession = Depends(get_db),
):
    from app.config import settings as app_settings
    from app.storage import storage

    # Verify the job belongs to the requesting user
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")

    # Try job_id first, then fallback to original job via LibraryReel
    # (cached replay jobs store frames under the original job_id in S3)
    prefix = f"frames/{job_id}/frame_{frame_index:04d}_"

    # Try S3 first if configured
    if app_settings.s3_bucket:
        from fastapi.responses import RedirectResponse

        try:
            keys = await storage.find_keys(prefix, limit=1)
            if keys:
                url = await storage.get_url(keys[0])
                return RedirectResponse(url=url, status_code=302)
        except Exception:
            pass

        # Fallback: resolve original job_id via LibraryReel (cached replay)
        from app.models.library import LibraryReel

        result = await db.execute(
            select(Job.library_reel_id).where(Job.id == job_id)
        )
        library_reel_id = result.scalar_one_or_none()
        if library_reel_id:
            lr_result = await db.execute(
                select(LibraryReel.job_id).where(LibraryReel.id == library_reel_id)
            )
            original_job_id = lr_result.scalar_one_or_none()
            if original_job_id and original_job_id != job_id:
                fallback_prefix = f"frames/{original_job_id}/frame_{frame_index:04d}_"
                try:
                    keys = await storage.find_keys(fallback_prefix, limit=1)
                    if keys:
                        url = await storage.get_url(keys[0])
                        return RedirectResponse(url=url, status_code=302)
                except Exception:
                    pass

    # Fallback: serve from local disk
    frames_dir = get_frames_dir(job_id)
    pattern = f"frame_{frame_index:04d}_*.jpg"
    matches = list(frames_dir.glob(pattern))
    if not matches:
        # Cached replay jobs store frames under the original job_id
        from app.models.library import LibraryReel

        try:
            result = await db.execute(
                select(Job.library_reel_id).where(Job.id == job_id)
            )
            library_reel_id = result.scalar_one_or_none()
            if library_reel_id:
                lr_result = await db.execute(
                    select(LibraryReel.job_id).where(LibraryReel.id == library_reel_id)
                )
                original_job_id = lr_result.scalar_one_or_none()
                if original_job_id and original_job_id != job_id:
                    orig_dir = get_frames_dir(original_job_id)
                    matches = list(orig_dir.glob(pattern))
        except Exception:
            pass
    if not matches:
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(matches[0], media_type="image/jpeg")


