"""Production Pipeline state machine and business logic."""

import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.progress import progress_tracker
from app.models.library import LibraryReel, UserScript
from app.models.production import ProductionAsset, ProductionComment, ProductionHistory
from app.models.user import User
from app.schemas.pipeline import (
    AssetResponse,
    CommentResponse,
    HistoryEntry,
    PipelineItem,
)

logger = logging.getLogger(__name__)

# ── State machine ────────────────────────────────────────────────

VALID_TRANSITIONS: dict[str | None, list[str]] = {
    None: ["script_ready"],
    "script_ready": ["filming"],
    "filming": ["editing"],
    "editing": ["review"],
    "review": ["scheduled", "rejected"],
    "rejected": ["filming", "editing"],
    "scheduled": ["published"],
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {"script_ready", "filming", "editing", "review", "rejected", "scheduled", "published"},
    "editor": {"script_ready", "filming", "editing"},
    "viewer": set(),
}


def validate_transition(
    from_status: str | None,
    to_status: str,
    user_role: str,
    has_asset: bool = False,
    comment: str | None = None,
) -> None:
    """Validate a status transition. Raises HTTPException on failure."""
    # Check role permissions
    allowed_statuses = ROLE_PERMISSIONS.get(user_role, set())
    if to_status not in allowed_statuses:
        raise HTTPException(status_code=403, detail=f"Role '{user_role}' cannot set status '{to_status}'")

    # Check valid transition
    valid_targets = VALID_TRANSITIONS.get(from_status, [])
    if to_status not in valid_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{from_status}' to '{to_status}'",
        )

    # editing → review requires at least one asset
    if from_status == "editing" and to_status == "review" and not has_asset:
        raise HTTPException(
            status_code=400,
            detail="Cannot move to review without at least one uploaded asset",
        )

    # review → rejected requires a comment
    if to_status == "rejected" and not comment:
        raise HTTPException(
            status_code=400,
            detail="Comment is required when rejecting",
        )


# ── Core operations ──────────────────────────────────────────────

async def transition_status(
    db: AsyncSession,
    script: UserScript,
    new_status: str,
    user: User,
    comment: str | None = None,
) -> UserScript:
    """Change production_status, record in history, return updated script."""
    old_status = script.production_status

    # Check for assets if moving to review
    has_asset = False
    if old_status == "editing" and new_status == "review":
        result = await db.execute(
            select(ProductionAsset.id)
            .where(ProductionAsset.script_id == script.id)
            .limit(1)
        )
        has_asset = result.scalar_one_or_none() is not None

    validate_transition(old_status, new_status, user.team_role or "owner", has_asset, comment)

    # Update script
    script.production_status = new_status
    if new_status == "published":
        script.published_at = datetime.utcnow()

    # Record history
    entry = ProductionHistory(
        script_id=script.id,
        from_status=old_status,
        to_status=new_status,
        triggered_by=user.id,
        comment=comment,
    )
    db.add(entry)

    await db.commit()
    await db.refresh(script)

    # Broadcast status change via WebSocket
    try:
        await progress_tracker.broadcast(f"pipeline:{script.user_id}", {
            "type": "status_changed",
            "script_id": script.id,
            "from_status": old_status,
            "to_status": new_status,
            "triggered_by": user.name or user.email or "Unknown",
        })
    except Exception as e:
        logger.warning("Failed to broadcast pipeline status change: %s", e)

    return script


async def get_pipeline_items(
    db: AsyncSession,
    user_id: str,
    status_filter: str | None = None,
    assignee_filter: str | None = None,
) -> list[PipelineItem]:
    """Return all scripts in the pipeline for a user, with optional filters."""
    query = (
        select(UserScript, LibraryReel)
        .outerjoin(LibraryReel, UserScript.library_reel_id == LibraryReel.id)
        .where(
            UserScript.user_id == user_id,
            UserScript.production_status.isnot(None),
        )
    )

    if status_filter:
        query = query.where(UserScript.production_status == status_filter)
    if assignee_filter:
        query = query.where(UserScript.assignee_id == assignee_filter)

    query = query.order_by(UserScript.updated_at.desc())
    result = await db.execute(query)
    rows = result.all()

    items: list[PipelineItem] = []
    for us, lr in rows:
        items.append(PipelineItem(
            script_id=us.id,
            production_status=us.production_status,
            assignee_id=us.assignee_id,
            due_date=us.due_date,
            scheduled_publish_at=us.scheduled_publish_at,
            published_at=us.published_at,
            script=us.script,
            description=us.description,
            editor_instructions=us.editor_instructions,
            library_reel_id=us.library_reel_id,
            job_id=lr.job_id if lr else None,
            url=lr.url if lr else None,
            video_title=lr.video_title if lr else None,
            video_author=lr.video_author if lr else None,
        ))

    return items


async def get_pipeline_detail(
    db: AsyncSession,
    script: UserScript,
) -> dict:
    """Return full detail for a single pipeline item: item + assets + comments + history."""
    # LibraryReel
    lr = None
    if script.library_reel_id:
        result = await db.execute(
            select(LibraryReel).where(LibraryReel.id == script.library_reel_id)
        )
        lr = result.scalar_one_or_none()

    item = PipelineItem(
        script_id=script.id,
        production_status=script.production_status,
        assignee_id=script.assignee_id,
        due_date=script.due_date,
        scheduled_publish_at=script.scheduled_publish_at,
        published_at=script.published_at,
        script=script.script,
        description=script.description,
        editor_instructions=script.editor_instructions,
        library_reel_id=script.library_reel_id,
        job_id=lr.job_id if lr else None,
        url=lr.url if lr else None,
        video_title=lr.video_title if lr else None,
        video_author=lr.video_author if lr else None,
    )

    # Assets
    assets_result = await db.execute(
        select(ProductionAsset)
        .where(ProductionAsset.script_id == script.id)
        .order_by(ProductionAsset.created_at.desc())
    )
    assets = [AssetResponse.model_validate(a) for a in assets_result.scalars().all()]

    # Comments (with author names)
    comments_result = await db.execute(
        select(ProductionComment, User.name)
        .outerjoin(User, ProductionComment.author_id == User.id)
        .where(ProductionComment.script_id == script.id)
        .order_by(ProductionComment.created_at.asc())
    )
    comments = [
        CommentResponse(
            id=c.id,
            stage=c.stage,
            author_id=c.author_id,
            author_name=name,
            text=c.text,
            created_at=c.created_at,
        )
        for c, name in comments_result.all()
    ]

    # History (with triggerer names)
    history_result = await db.execute(
        select(ProductionHistory, User.name)
        .outerjoin(User, ProductionHistory.triggered_by == User.id)
        .where(ProductionHistory.script_id == script.id)
        .order_by(ProductionHistory.created_at.desc())
    )
    history = [
        HistoryEntry(
            from_status=h.from_status,
            to_status=h.to_status,
            triggered_by=h.triggered_by,
            triggered_by_name=name,
            comment=h.comment,
            created_at=h.created_at,
        )
        for h, name in history_result.all()
    ]

    return {
        "item": item,
        "assets": assets,
        "comments": comments,
        "history": history,
    }
