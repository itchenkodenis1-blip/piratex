from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anonymous import ensure_user
from app.database import get_db
from app.models.library import UserReelLike
from app.models.user import User
from app.schemas.likes import LikeRequest, LikedUrlsResponse

likes_router = APIRouter()


@likes_router.get("", response_model=LikedUrlsResponse)
async def get_liked_urls(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ensure_user),
):
    """Return all URLs liked by the current user."""
    result = await db.execute(
        select(UserReelLike.url)
        .where(UserReelLike.user_id == user.id)
        .order_by(UserReelLike.created_at.desc())
    )
    urls = [row[0] for row in result.all()]
    return LikedUrlsResponse(urls=urls)


@likes_router.post("", status_code=status.HTTP_201_CREATED)
async def like_reel(
    body: LikeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ensure_user),
):
    """Like a reel by URL. Idempotent."""
    existing = await db.execute(
        select(UserReelLike).where(
            UserReelLike.user_id == user.id,
            UserReelLike.url == body.url,
        )
    )
    if existing.scalar_one_or_none():
        return {"ok": True}

    like = UserReelLike(user_id=user.id, url=body.url)
    db.add(like)

    # Record interest signals from the liked reel's author
    from app.models.trends import ProfileReel, TrackedProfile
    from app.services.interest_signals import record_signals

    pr_result = await db.execute(
        select(ProfileReel.profile_id).where(ProfileReel.url == body.url)
    )
    profile_id = pr_result.scalar_one_or_none()
    if profile_id:
        tp_result = await db.execute(
            select(TrackedProfile).where(TrackedProfile.id == profile_id)
        )
        profile = tp_result.scalar_one_or_none()
        if profile:
            topics = list(set(
                (profile.topics or []) + ([profile.niche] if profile.niche else [])
            ))
            if topics:
                await record_signals(
                    db, user_id=user.id, topics=topics,
                    source="like", weight=0.5, source_id=str(profile_id),
                )

    await db.commit()
    return {"ok": True}


@likes_router.delete("")
async def unlike_reel(
    body: LikeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ensure_user),
):
    """Remove like from a reel by URL."""
    await db.execute(
        delete(UserReelLike).where(
            UserReelLike.user_id == user.id,
            UserReelLike.url == body.url,
        )
    )
    await db.commit()
    return {"ok": True}
