"""Storage cleanup helpers — delete intermediate and orphaned files."""

import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus
from app.models.trends import ProfileReel
from app.storage import storage

logger = logging.getLogger(__name__)


async def cleanup_job_intermediates(
    video_path: Path | None,
    audio_path: Path | None,
) -> None:
    """Delete video and audio from local disk and bucket after processing.

    Safe to call with None paths — silently skips.
    Never raises — logs errors instead so the pipeline is not interrupted.
    """
    for label, local_path, key_prefix in [
        ("video", video_path, "videos/"),
        ("audio", audio_path, "audio/"),
    ]:
        if local_path is None:
            continue
        # Remote
        try:
            key = f"{key_prefix}{local_path.name}"
            await storage.delete_file(key)
            logger.info("[cleanup] Deleted %s from bucket: %s", label, key)
        except Exception as exc:
            logger.warning("[cleanup] Failed to delete %s from bucket: %s", label, exc)
        # Local
        try:
            local_path.unlink(missing_ok=True)
            logger.info("[cleanup] Deleted local %s: %s", label, local_path)
        except Exception as exc:
            logger.warning("[cleanup] Failed to delete local %s: %s", label, exc)


async def cleanup_job_storage(job_id: str) -> int:
    """Delete all frame files for a job from both bucket and local disk."""
    deleted = 0
    try:
        deleted = await storage.delete_prefix(f"frames/{job_id}/")
        logger.info("[cleanup] Deleted %d frame(s) from bucket for job %s", deleted, job_id)
    except Exception as exc:
        logger.warning("[cleanup] Failed to delete frames from bucket for job %s: %s", job_id, exc)
    return deleted


async def garbage_collect_orphaned_files(db: AsyncSession) -> dict:
    """Find and delete storage files whose jobs/reels no longer exist in DB.

    Returns summary: {"orphaned_jobs": [...], "deleted_frames": int, "deleted_thumbnails": int}
    """
    # ── Orphaned frames ──────────────────────────────────────────
    frame_dirs = await storage.list_prefixes("frames/")
    storage_job_ids = set()
    for prefix in frame_dirs:
        parts = prefix.strip("/").split("/")
        if len(parts) >= 2:
            storage_job_ids.add(parts[1])

    orphaned_ids: list[str] = []
    total_frames_deleted = 0

    if storage_job_ids:
        result = await db.execute(
            select(Job.id).where(Job.id.in_(list(storage_job_ids)))
        )
        existing_ids = {row[0] for row in result.all()}
        orphaned_ids = sorted(storage_job_ids - existing_ids)

        for job_id in orphaned_ids:
            deleted = await cleanup_job_storage(job_id)
            total_frames_deleted += deleted

    if orphaned_ids:
        logger.info(
            "[gc] Cleaned up %d orphaned job(s), %d frame(s) deleted",
            len(orphaned_ids), total_frames_deleted,
        )

    # ── Orphaned thumbnails ──────────────────────────────────────
    thumbnail_keys = await storage.find_keys("thumbnails/", limit=10000)
    total_thumbnails_deleted = 0

    if thumbnail_keys:
        # Extract reel IDs from keys like "thumbnails/{reel_id}.jpg"
        storage_reel_ids = set()
        key_to_id: dict[str, str] = {}
        for key in thumbnail_keys:
            name = key.rsplit("/", 1)[-1].rsplit(".", 1)[0]  # "thumbnails/uuid.jpg" → "uuid"
            storage_reel_ids.add(name)
            key_to_id[key] = name

        # Check which reel IDs still exist
        result = await db.execute(
            select(ProfileReel.id).where(ProfileReel.id.in_(list(storage_reel_ids)))
        )
        existing_reel_ids = {row[0] for row in result.all()}

        for key, reel_id in key_to_id.items():
            if reel_id not in existing_reel_ids:
                try:
                    await storage.delete_file(key)
                    total_thumbnails_deleted += 1
                except Exception as exc:
                    logger.warning("[gc] Failed to delete orphaned thumbnail %s: %s", key, exc)

    if total_thumbnails_deleted:
        logger.info("[gc] Deleted %d orphaned thumbnail(s)", total_thumbnails_deleted)

    return {
        "orphaned_jobs": orphaned_ids,
        "deleted_frames": total_frames_deleted,
        "deleted_thumbnails": total_thumbnails_deleted,
    }


async def cleanup_failed_jobs(db: AsyncSession, ttl_days: int = 7) -> dict:
    """Delete failed jobs older than ttl_days, including their storage files.

    Returns summary: {"deleted_jobs": int, "deleted_frames": int}
    """
    cutoff = datetime.utcnow() - timedelta(days=ttl_days)

    result = await db.execute(
        select(Job.id).where(
            Job.status == JobStatus.FAILED,
            Job.updated_at < cutoff,
        )
    )
    job_ids = result.scalars().all()

    if not job_ids:
        return {"deleted_jobs": 0, "deleted_frames": 0}

    # Delete frames from storage
    total_frames = 0
    for job_id in job_ids:
        total_frames += await cleanup_job_storage(job_id)

    # Delete jobs from DB (cascades to related records)
    await db.execute(delete(Job).where(Job.id.in_(job_ids)))
    await db.commit()

    logger.info(
        "[cleanup] Deleted %d failed job(s) older than %d days, %d frame(s)",
        len(job_ids), ttl_days, total_frames,
    )
    return {
        "deleted_jobs": len(job_ids),
        "deleted_frames": total_frames,
    }
