"""In-memory niche cache — avoids DB hits on every LLM classification call.

TTL-based: refreshes from DB every 5 minutes so admin changes propagate
across all app replicas without restart.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes


@dataclass
class CachedNiche:
    slug: str
    display_name: str
    display_name_en: str | None
    description: str | None
    keywords: list[str]
    group_key: str
    sort_order: int
    is_active: bool


class NicheCache:
    """Singleton cache for niche definitions loaded from DB."""

    def __init__(self) -> None:
        self._niches: dict[str, CachedNiche] = {}
        self._lock = asyncio.Lock()
        self._last_refresh: float = 0

    async def refresh(self, db: AsyncSession) -> None:
        from app.models.niches import Niche

        result = await db.execute(select(Niche).order_by(Niche.sort_order))
        rows = result.scalars().all()
        async with self._lock:
            self._niches = {
                r.slug: CachedNiche(
                    slug=r.slug,
                    display_name=r.display_name,
                    display_name_en=r.display_name_en,
                    description=r.description,
                    keywords=r.keywords or [],
                    group_key=r.group_key,
                    sort_order=r.sort_order,
                    is_active=r.is_active,
                )
                for r in rows
            }
            self._last_refresh = time.monotonic()

    async def ensure_fresh(self, db: AsyncSession) -> None:
        """Refresh if TTL expired. Safe to call on every request."""
        if time.monotonic() - self._last_refresh > CACHE_TTL_SECONDS:
            await self.refresh(db)

    def get_all(self) -> list[CachedNiche]:
        return list(self._niches.values())

    def get_active(self) -> list[CachedNiche]:
        return [n for n in self._niches.values() if n.is_active]

    def get_active_slugs(self) -> set[str]:
        return {n.slug for n in self._niches.values() if n.is_active}

    def is_valid(self, slug: str) -> bool:
        n = self._niches.get(slug)
        return n is not None and n.is_active

    # ── Group helpers (for 2-step dropdown) ──────────────────────────

    def get_groups(self) -> dict[str, list[CachedNiche]]:
        """Return active niches grouped by group_key."""
        groups: dict[str, list[CachedNiche]] = {}
        for n in self._niches.values():
            if not n.is_active:
                continue
            groups.setdefault(n.group_key, []).append(n)
        return groups

    def get_group_slugs(self, group_key: str) -> set[str]:
        """All active niche slugs in a group. For trend filtering by group."""
        return {n.slug for n in self._niches.values() if n.is_active and n.group_key == group_key}

    def get_all_group_keys(self) -> list[str]:
        """Ordered list of unique group keys from active niches."""
        seen: dict[str, int] = {}
        for n in self._niches.values():
            if n.is_active and n.group_key not in seen:
                seen[n.group_key] = n.sort_order
        return sorted(seen.keys(), key=lambda k: seen[k])

    def is_group(self, slug: str) -> bool:
        """Check if slug matches a group_key (not a niche slug)."""
        return any(n.group_key == slug for n in self._niches.values())

    def resolve_filter_slugs(self, niche_param: str) -> set[str]:
        """Resolve a niche filter param to set of slugs.

        If param is a group_key → all child slugs in that group.
        If param is a niche slug → just that slug.
        """
        # Check if it's a group key first
        group_slugs = self.get_group_slugs(niche_param)
        if group_slugs:
            return group_slugs
        # Otherwise treat as individual niche
        if self.is_valid(niche_param):
            return {niche_param}
        return set()

    def resolve_multi_filter_slugs(self, niche_csv: str) -> set[str]:
        """Parse comma-separated niche params, resolve each, union all."""
        result: set[str] = set()
        for part in niche_csv.split(",")[:20]:
            part = part.strip()
            if part:
                result |= self.resolve_filter_slugs(part)
        return result

    # ── LLM prompt helpers ───────────────────────────────────────────

    def prompt_compact(self) -> str:
        """For Haiku / lightweight classification: 'slug: description' per line."""
        return "\n".join(
            f"- {n.slug}: {n.description}"
            for n in self._niches.values()
            if n.is_active and n.description
        )

    def prompt_detailed(self) -> str:
        """For GPT-4o / full classification: includes signal keywords."""
        lines = []
        for n in self._niches.values():
            if not n.is_active:
                continue
            if n.keywords:
                lines.append(f"- {n.slug}: {n.description} (signals: {', '.join(n.keywords[:5])})")
            else:
                lines.append(f"- {n.slug}: {n.description}")
        return "\n".join(lines)

    def slugs_csv(self) -> str:
        return ", ".join(n.slug for n in self._niches.values() if n.is_active)

    @property
    def is_loaded(self) -> bool:
        return len(self._niches) > 0


# Singleton
niche_cache = NicheCache()
