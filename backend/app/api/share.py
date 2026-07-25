from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_optional_user
from app.core.rate_limit import limiter

from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.library import UserScript
from app.models.user import User
from app.schemas.job import SharedJobResponse
from app.storage.local import get_frames_dir

router = APIRouter()


@router.get("/{token}", response_model=SharedJobResponse)
@limiter.limit("30/minute")
async def get_shared_job(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
):
    """View a shared job result by token. No authentication required."""
    result = await db.execute(
        select(Job).where(Job.share_token == token)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Not found")

    if job.status != JobStatus.COMPLETED or not job.adaptation_summary:
        raise HTTPException(status_code=404, detail="Not found")

    summary = job.adaptation_summary

    # Prefer user's latest script over original job summary
    script_text = summary.get("script") or ""
    description_text = summary.get("description") or ""
    editor_text = summary.get("editor_instructions") or ""

    if job.library_reel_id:
        us_result = await db.execute(
            select(UserScript).where(
                UserScript.user_id == job.user_id,
                UserScript.library_reel_id == job.library_reel_id,
            )
        )
        us = us_result.scalar_one_or_none()
        if us:
            if us.script:
                script_text = us.script
            if us.description:
                description_text = us.description
            if us.editor_instructions:
                editor_text = us.editor_instructions

    # If the viewer is the owner, include library_reel_id for redirect
    owner_reel_id = None
    if viewer and viewer.id == job.user_id and job.library_reel_id:
        owner_reel_id = job.library_reel_id

    return SharedJobResponse(
        video_title=job.video_title,
        video_duration=job.video_duration,
        video_platform=job.video_platform,
        video_author=job.video_author,
        video_url=job.url,
        script=script_text,
        description=description_text,
        editor_instructions=editor_text,
        frames=job.frames,
        created_at=job.created_at,
        library_reel_id=owner_reel_id,
    )


@router.get("/{token}/frames/{frame_index}")
async def get_shared_frame(
    token: str,
    frame_index: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a frame image from a shared job. No authentication required."""
    from app.config import settings as app_settings
    from app.storage import storage

    result = await db.execute(
        select(Job.id).where(Job.share_token == token)
    )
    job_id = result.scalar_one_or_none()
    if not job_id:
        raise HTTPException(status_code=404, detail="Not found")

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

    # Fallback: serve from local disk
    frames_dir = get_frames_dir(job_id)
    pattern = f"frame_{frame_index:04d}_*.jpg"
    matches = list(frames_dir.glob(pattern))
    if not matches:
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(matches[0], media_type="image/jpeg")
