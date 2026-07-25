from abc import ABC, abstractmethod
from dataclasses import dataclass


def _first(*values):
    """Return first non-None value. Use instead of `a or b` for numeric fields
    where 0 is a valid value (the `or` operator treats 0 as falsy)."""
    for v in values:
        if v is not None:
            return v
    return None


@dataclass
class ScrapeResult:
    """Unified result from any platform scraper."""

    video_url: str  # Direct CDN link to download the video
    audio_url: str | None = None  # Separate audio stream (Instagram DASH)
    title: str | None = None
    duration: float | None = None
    platform: str = "unknown"
    uploader: str | None = None
    description: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    thumbnail: str | None = None


class PlatformScraper(ABC):
    """Base class for platform-specific Apify scrapers."""

    @abstractmethod
    async def scrape(self, url: str) -> ScrapeResult:
        """Run Apify actor and return unified result with video URL + metadata."""
        ...

    async def scrape_comments(self, url: str, max_comments: int = 50) -> list[dict]:
        """Extract comments via Apify. Override in subclasses that support it."""
        return []
