"""Shooting Queue API — admin-only filming task queue."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_admin_user
from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.library import LibraryReel, ShootingQueueItem, UserScript
from app.models.user import User

router = APIRouter()


@router.get("")
async def list_queue(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all items in the shooting queue, ordered by position."""
    result = await db.execute(
        select(ShootingQueueItem, UserScript, LibraryReel)
        .join(UserScript, ShootingQueueItem.user_script_id == UserScript.id)
        .join(LibraryReel, UserScript.library_reel_id == LibraryReel.id)
        .where(ShootingQueueItem.user_id == user.id)
        .order_by(ShootingQueueItem.filmed_at.is_(None).desc(), ShootingQueueItem.position)
    )
    rows = result.all()

    items = []
    for queue_item, script, reel in rows:
        items.append({
            "id": queue_item.id,
            "position": queue_item.position,
            "added_at": queue_item.added_at.isoformat() if queue_item.added_at else None,
            "filmed_at": queue_item.filmed_at.isoformat() if queue_item.filmed_at else None,
            "script_id": script.id,
            "script_text": script.script,
            "description": script.description,
            "library_reel_id": reel.id,
            "video_title": reel.video_title,
            "video_author": reel.video_author,
            "video_platform": reel.video_platform,
            "video_duration": reel.video_duration,
            "url": reel.url,
            "job_id": reel.job_id,
        })

    return {"items": items}


@router.post("/add/{job_id}")
async def add_to_queue(
    job_id: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a job's script to the shooting queue. Auto-creates UserScript if needed."""
    # Find completed job
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id, Job.status == JobStatus.COMPLETED)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Completed job not found")

    if not job.library_reel_id:
        raise HTTPException(status_code=400, detail="Job has no library reel")

    if not job.adaptation_summary:
        raise HTTPException(status_code=400, detail="Job has no adaptation summary")

    # Find or create UserScript
    us_result = await db.execute(
        select(UserScript).where(
            UserScript.user_id == user.id,
            UserScript.library_reel_id == job.library_reel_id,
        )
    )
    script = us_result.scalar_one_or_none()

    if not script:
        summary = job.adaptation_summary if isinstance(job.adaptation_summary, dict) else {}
        script = UserScript(
            id=str(uuid.uuid4()),
            user_id=user.id,
            library_reel_id=job.library_reel_id,
            script=summary.get("script", ""),
            description=summary.get("description", ""),
            editor_instructions=summary.get("editor_instructions", ""),
            original_script=summary.get("script", ""),
            original_description=summary.get("description", ""),
            original_editor_instructions=summary.get("editor_instructions", ""),
        )
        db.add(script)
        await db.flush()

    # Check if already in queue
    existing = await db.execute(
        select(ShootingQueueItem).where(
            ShootingQueueItem.user_id == user.id,
            ShootingQueueItem.user_script_id == script.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Already in shooting queue")

    # Get next position
    max_pos = await db.execute(
        select(func.coalesce(func.max(ShootingQueueItem.position), -1)).where(
            ShootingQueueItem.user_id == user.id,
        )
    )
    next_position = max_pos.scalar() + 1

    item = ShootingQueueItem(
        id=str(uuid.uuid4()),
        user_id=user.id,
        user_script_id=script.id,
        position=next_position,
        added_at=datetime.utcnow(),
    )
    db.add(item)
    await db.commit()

    return {"ok": True, "item_id": item.id, "script_id": script.id}


@router.post("/{item_id}/done")
async def mark_done(
    item_id: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a queue item as filmed (sets filmed_at timestamp)."""
    result = await db.execute(
        select(ShootingQueueItem).where(
            ShootingQueueItem.id == item_id,
            ShootingQueueItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    item.filmed_at = datetime.utcnow()
    await db.commit()

    return {"ok": True}


@router.delete("/{item_id}")
async def remove_from_queue(
    item_id: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an item from the shooting queue entirely."""
    result = await db.execute(
        select(ShootingQueueItem).where(
            ShootingQueueItem.id == item_id,
            ShootingQueueItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    await db.delete(item)
    await db.commit()

    return {"ok": True}


@router.post("/{item_id}/unfilm")
async def unfilm(
    item_id: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Undo filming — move back to pending queue."""
    result = await db.execute(
        select(ShootingQueueItem).where(
            ShootingQueueItem.id == item_id,
            ShootingQueueItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    item.filmed_at = None
    await db.commit()

    return {"ok": True}


@router.get("/check/{job_id}")
async def check_in_queue(
    job_id: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if a job's script is already in the shooting queue."""
    # Find the job's library_reel_id
    result = await db.execute(select(Job.library_reel_id).where(Job.id == job_id, Job.user_id == user.id))
    library_reel_id = result.scalar_one_or_none()
    if not library_reel_id:
        return {"in_queue": False, "item_id": None}

    # Find UserScript
    us_result = await db.execute(
        select(UserScript.id).where(
            UserScript.user_id == user.id,
            UserScript.library_reel_id == library_reel_id,
        )
    )
    script_id = us_result.scalar_one_or_none()
    if not script_id:
        return {"in_queue": False, "item_id": None}

    # Check queue
    qi_result = await db.execute(
        select(ShootingQueueItem.id).where(
            ShootingQueueItem.user_id == user.id,
            ShootingQueueItem.user_script_id == script_id,
        )
    )
    item_id = qi_result.scalar_one_or_none()

    return {"in_queue": item_id is not None, "item_id": item_id}
