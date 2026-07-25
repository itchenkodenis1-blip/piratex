"""Public niches API — returns niche tree for 2-step dropdown."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.niche_cache import niche_cache
from app.database import get_db
from app.models.trends import ProfileReel, TrackedProfile

router = APIRouter()

GROUP_LABELS = {
    "tech_ai": "Технологии и ИИ",
    "business_money": "Бизнес и деньги",
    "marketing_growth": "Маркетинг и рост",
    "creative": "Креатив",
    "education_career": "Образование и карьера",
    "health_wellness": "Здоровье",
    "lifestyle": "Лайфстайл",
    "entertainment": "Развлечения",
    "other": "Другое",
}

GROUP_LABELS_EN = {
    "tech_ai": "Tech & AI",
    "business_money": "Business & Money",
    "marketing_growth": "Marketing & Growth",
    "creative": "Creative",
    "education_career": "Education & Career",
    "health_wellness": "Health & Wellness",
    "lifestyle": "Lifestyle",
    "entertainment": "Entertainment",
    "other": "Other",
}


class NicheChild(BaseModel):
    slug: str
    display_name: str
    display_name_en: str | None = None
    keywords: list[str] = []
    trending_count: int = 0


class NicheGroup(BaseModel):
    key: str
    label: str
    label_en: str
    children: list[NicheChild]
    trending_count: int = 0  # sum of children


class NicheTreeResponse(BaseModel):
    groups: list[NicheGroup]


@router.get("/niches", response_model=NicheTreeResponse)
async def get_niche_tree(
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: niche tree for 2-step dropdown filter."""
    await niche_cache.ensure_fresh(db)

    # Trending reel counts per niche
    trending_q = (
        select(
            ProfileReel.niche,
            func.count(ProfileReel.id).label("cnt"),
        )
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(
            ProfileReel.is_trending == True,  # noqa: E712
            ProfileReel.is_hidden == False,  # noqa: E712
            TrackedProfile.is_blocked == False,  # noqa: E712
            ProfileReel.niche.isnot(None),
        )
        .group_by(ProfileReel.niche)
    )
    result = await db.execute(trending_q)
    trending_map: dict[str, int] = {row.niche: row.cnt for row in result.all()}

    # Build tree from cache
    groups_map = niche_cache.get_groups()
    group_order = niche_cache.get_all_group_keys()

    groups = []
    for gk in group_order:
        niches_in_group = groups_map.get(gk, [])
        children = [
            NicheChild(
                slug=n.slug,
                display_name=n.display_name,
                display_name_en=n.display_name_en,
                keywords=n.keywords or [],
                trending_count=trending_map.get(n.slug, 0),
            )
            for n in niches_in_group
        ]
        children.sort(key=lambda c: c.trending_count, reverse=True)
        groups.append(NicheGroup(
            key=gk,
            label=GROUP_LABELS.get(gk, gk),
            label_en=GROUP_LABELS_EN.get(gk, gk),
            children=children,
            trending_count=sum(c.trending_count for c in children),
        ))

    return NicheTreeResponse(groups=groups)
