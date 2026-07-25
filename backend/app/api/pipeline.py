"""Production Pipeline API — Kanban workflow endpoints."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.config import settings
from app.core.auth import get_current_user
from app.database import get_db
from app.models.library import UserScript
from app.models.production import ProductionAsset, ProductionComment
from app.models.user import User
from app.schemas.pipeline import (
    AssetConfirmRequest,
    AssetResponse,
    CommentCreate,
    CommentResponse,
    PresignRequest,
    PresignResponse,
    StatusChangeRequest,
)
from app.services.pipeline_service import (
    get_pipeline_detail,
    get_pipeline_items,
    transition_status,
)


ALLOWED_CONTENT_PREFIXES = ("image/", "video/", "audio/", "application/pdf")
BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".ps1", ".py", ".js", ".php", ".jsp", ".html"}
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB


class AssignRequest(BaseModel):
    assignee_id: str | None = None


class ScheduleRequest(BaseModel):
    scheduled_publish_at: datetime | None = None

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────

async def _get_user_script(db: AsyncSession, script_id: str, user: User) -> UserScript:
    """Fetch UserScript owned by user, or raise 404."""
    result = await db.execute(
        select(UserScript).where(
            UserScript.id == script_id,
            UserScript.user_id == user.id,
        )
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="Script not found")
    return script


# ── Endpoints ────────────────────────────────────────────────────

@router.get("")
async def list_pipeline(
    status: str | None = Query(None, description="Filter by production_status"),
    assignee: str | None = Query(None, description="Filter by assignee_id"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all scripts in the pipeline (Kanban board data)."""
    items = await get_pipeline_items(db, user.id, status_filter=status, assignee_filter=assignee)
    return {"items": [item.model_dump() for item in items]}


@router.get("/{script_id}")
async def get_pipeline_item(
    script_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full detail for a pipeline item: script + assets + comments + history."""
    script = await _get_user_script(db, script_id, user)

    if script.production_status is None:
        raise HTTPException(status_code=404, detail="Script is not in pipeline")

    detail = await get_pipeline_detail(db, script)
    return {
        "item": detail["item"].model_dump(),
        "assets": [a.model_dump() for a in detail["assets"]],
        "comments": [c.model_dump() for c in detail["comments"]],
        "history": [h.model_dump() for h in detail["history"]],
    }


@router.post("/add/{script_id}")
async def add_to_pipeline(
    script_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a script to the pipeline (set status to script_ready)."""
    script = await _get_user_script(db, script_id, user)

    if script.production_status is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Script is already in pipeline with status '{script.production_status}'",
        )

    script = await transition_status(db, script, "script_ready", user)

    return {"ok": True, "script_id": script.id, "production_status": script.production_status}


@router.post("/add-by-job/{job_id}")
async def add_to_pipeline_by_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a job's script to the pipeline. Auto-creates UserScript if it doesn't exist."""
    from app.models.job import Job, JobStatus

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

    # Find existing UserScript or create one
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

    if script.production_status is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Script is already in pipeline with status '{script.production_status}'",
        )

    script = await transition_status(db, script, "script_ready", user)

    return {"ok": True, "script_id": script.id, "production_status": script.production_status}


@router.patch("/{script_id}/status")
async def change_status(
    script_id: str,
    body: StatusChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change production status (state machine validated)."""
    script = await _get_user_script(db, script_id, user)

    if script.production_status is None:
        raise HTTPException(status_code=400, detail="Script is not in pipeline")

    script = await transition_status(db, script, body.new_status.value, user, body.comment)

    return {"ok": True, "script_id": script.id, "production_status": script.production_status}


@router.patch("/{script_id}/assign")
async def assign_script(
    script_id: str,
    body: AssignRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a script to a team member (or unassign with null)."""
    script = await _get_user_script(db, script_id, user)

    if script.production_status is None:
        raise HTTPException(status_code=400, detail="Script is not in pipeline")

    # Only owner can assign
    if user.team_role not in (None, "owner"):
        raise HTTPException(status_code=403, detail="Only owner can assign scripts")

    script.assignee_id = body.assignee_id
    await db.commit()
    await db.refresh(script)

    return {"ok": True, "script_id": script.id, "assignee_id": script.assignee_id}


@router.patch("/{script_id}/schedule")
async def schedule_script(
    script_id: str,
    body: ScheduleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear the scheduled publish date for a script."""
    script = await _get_user_script(db, script_id, user)

    if script.production_status is None:
        raise HTTPException(status_code=400, detail="Script is not in pipeline")

    # Only owner can schedule
    if user.team_role not in (None, "owner"):
        raise HTTPException(status_code=403, detail="Only owner can schedule scripts")

    script.scheduled_publish_at = body.scheduled_publish_at
    await db.commit()
    await db.refresh(script)

    return {
        "ok": True,
        "script_id": script.id,
        "scheduled_publish_at": script.scheduled_publish_at.isoformat() if script.scheduled_publish_at else None,
    }


class DueDateRequest(BaseModel):
    due_date: datetime | None = None


@router.patch("/{script_id}/due-date")
async def set_due_date(
    script_id: str,
    body: DueDateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear the due date for a script."""
    script = await _get_user_script(db, script_id, user)

    if script.production_status is None:
        raise HTTPException(status_code=400, detail="Script is not in pipeline")

    script.due_date = body.due_date
    await db.commit()
    await db.refresh(script)

    return {
        "ok": True,
        "script_id": script.id,
        "due_date": script.due_date.isoformat() if script.due_date else None,
    }


# ── Files API ───────────────────────────────────────────────────

@router.post("/{script_id}/assets/presign", response_model=PresignResponse)
async def presign_asset_upload(
    script_id: str,
    body: PresignRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a presigned PUT URL for direct S3 upload."""
    script = await _get_user_script(db, script_id, user)
    if script.production_status is None:
        raise HTTPException(status_code=400, detail="Script is not in pipeline")

    if not settings.s3_bucket:
        raise HTTPException(status_code=501, detail="S3 storage is not configured")

    # Validate content type
    if body.file_type:
        if not body.file_type.startswith(ALLOWED_CONTENT_PREFIXES):
            raise HTTPException(status_code=400, detail="Unsupported file type")

    # Validate file size
    if body.file_size is not None and body.file_size > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 100MB)")

    # Sanitize file_name: take only the basename, strip path separators
    import os
    safe_name = os.path.basename(body.file_name).strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    # Validate file extension — block dangerous types
    _, ext = os.path.splitext(safe_name)
    if ext.lower() in BLOCKED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")

    file_key = f"pipeline/{user.id}/{script_id}/{uuid.uuid4()}_{safe_name}"

    from app.storage import storage
    upload_url = await storage.get_upload_url(file_key, expires=3600, content_type=body.file_type)

    return PresignResponse(upload_url=upload_url, file_key=file_key)


@router.post("/{script_id}/assets", response_model=AssetResponse)
async def confirm_asset_upload(
    script_id: str,
    body: AssetConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a completed upload — save asset metadata to DB."""
    script = await _get_user_script(db, script_id, user)
    if script.production_status is None:
        raise HTTPException(status_code=400, detail="Script is not in pipeline")

    # Validate file_key belongs to this user/script (prevent referencing other users' files)
    expected_prefix = f"pipeline/{user.id}/{script_id}/"
    if not body.file_key.startswith(expected_prefix):
        raise HTTPException(status_code=400, detail="Invalid file_key for this script")

    asset = ProductionAsset(
        id=str(uuid.uuid4()),
        script_id=script.id,
        stage=script.production_status,
        file_key=body.file_key,
        file_name=body.file_name,
        file_size=body.file_size,
        file_type=body.file_type,
        uploaded_by=user.id,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    return AssetResponse.model_validate(asset)


@router.get("/{script_id}/assets", response_model=list[AssetResponse])
async def list_assets(
    script_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all assets for a pipeline script."""
    await _get_user_script(db, script_id, user)

    result = await db.execute(
        select(ProductionAsset)
        .where(ProductionAsset.script_id == script_id)
        .order_by(ProductionAsset.created_at.desc())
    )
    return [AssetResponse.model_validate(a) for a in result.scalars().all()]


@router.get("/{script_id}/assets/{asset_id}/download")
async def download_asset(
    script_id: str,
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a presigned GET URL to download/view an asset."""
    await _get_user_script(db, script_id, user)

    result = await db.execute(
        select(ProductionAsset).where(
            ProductionAsset.id == asset_id,
            ProductionAsset.script_id == script_id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    from app.storage import storage
    download_url = await storage.get_url(asset.file_key, expires=3600)

    return {"download_url": download_url, "file_name": asset.file_name}


@router.delete("/{script_id}/assets/{asset_id}")
async def delete_asset(
    script_id: str,
    asset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an asset (S3 + DB)."""
    await _get_user_script(db, script_id, user)

    result = await db.execute(
        select(ProductionAsset).where(
            ProductionAsset.id == asset_id,
            ProductionAsset.script_id == script_id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Delete from S3
    if settings.s3_bucket:
        try:
            from app.storage import storage
            await storage.delete_file(asset.file_key)
        except Exception as e:
            logger.warning("Failed to delete asset from S3: %s", e)

    await db.delete(asset)
    await db.commit()

    return {"ok": True}


# ── Comments API ────────────────────────────────────────────────

@router.post("/{script_id}/comments", response_model=CommentResponse)
async def add_comment(
    script_id: str,
    body: CommentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment tied to the script's current production stage."""
    script = await _get_user_script(db, script_id, user)
    if script.production_status is None:
        raise HTTPException(status_code=400, detail="Script is not in pipeline")

    comment = ProductionComment(
        id=str(uuid.uuid4()),
        script_id=script.id,
        stage=script.production_status,
        author_id=user.id,
        text=body.text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return CommentResponse(
        id=comment.id,
        stage=comment.stage,
        author_id=comment.author_id,
        author_name=user.name,
        text=comment.text,
        created_at=comment.created_at,
    )


@router.get("/{script_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    script_id: str,
    stage: str | None = Query(None, description="Filter by stage"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List comments for a pipeline script, optionally filtered by stage."""
    await _get_user_script(db, script_id, user)

    query = (
        select(ProductionComment, User.name)
        .outerjoin(User, ProductionComment.author_id == User.id)
        .where(ProductionComment.script_id == script_id)
    )
    if stage:
        query = query.where(ProductionComment.stage == stage)
    query = query.order_by(ProductionComment.created_at.asc())

    result = await db.execute(query)
    return [
        CommentResponse(
            id=c.id,
            stage=c.stage,
            author_id=c.author_id,
            author_name=name,
            text=c.text,
            created_at=c.created_at,
        )
        for c, name in result.all()
    ]
