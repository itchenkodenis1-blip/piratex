"""Infer user niches and interests from their parsed reels' tags."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import LibraryReel, Tag, library_reel_tags
from app.core.niches import VALID_NICHES


async def infer_user_niches(db: AsyncSession, user_id: str, top_n: int = 3) -> list[str]:
    """Return the user's top niches based on frequency of niche tags in their parsed reels."""
    query = (
        select(Tag.name, func.count(Tag.name).label("cnt"))
        .select_from(LibraryReel)
        .join(library_reel_tags, library_reel_tags.c.library_reel_id == LibraryReel.id)
        .join(Tag, Tag.id == library_reel_tags.c.tag_id)
        .where(
            LibraryReel.submitted_by == user_id,
            Tag.name.in_(VALID_NICHES),
        )
        .group_by(Tag.name)
        .order_by(func.count(Tag.name).desc())
        .limit(top_n)
    )
    result = await db.execute(query)
    return [row[0] for row in result.all() if row[1] > 0]


async def infer_user_interests(
    db: AsyncSession, user_id: str, top_n: int = 15
) -> list[dict]:
    """Return the user's top interests (topics) from ALL tags in their parsed reels.

    Unlike infer_user_niches which only counts the broad valid niches,
    this returns granular topics like 'ai-tools', 'chatgpt', 'no-code', etc.

    Returns: [{"topic": "ai-tools", "display_name": "Ai Tools", "count": 5}, ...]
    """
    query = (
        select(Tag.name, Tag.display_name, func.count(Tag.name).label("cnt"))
        .select_from(LibraryReel)
        .join(library_reel_tags, library_reel_tags.c.library_reel_id == LibraryReel.id)
        .join(Tag, Tag.id == library_reel_tags.c.tag_id)
        .where(
            LibraryReel.submitted_by == user_id,
            # Exclude broad niche tags — they're too coarse for interests
            ~Tag.name.in_(VALID_NICHES),
        )
        .group_by(Tag.name, Tag.display_name)
        .order_by(func.count(Tag.name).desc())
        .limit(top_n)
    )
    result = await db.execute(query)
    return [
        {"topic": row[0], "display_name": row[1], "count": int(row[2])}
        for row in result.all()
        if row[2] > 0
    ]
