import logging
from pathlib import Path

from app.core.exceptions import DownloadError
from app.services.scraper._apify_client import _safe_domain
from app.services.scraper._base import PlatformScraper
from app.services.scraper._download import download_video_to_local
from app.services.scraper._platform import Platform, detect_platform, normalize_url

logger = logging.getLogger(__name__)

_DOWNLOAD_MAX_ATTEMPTS = 2


def _get_scraper(platform: Platform) -> PlatformScraper:
    """Return the appropriate scraper for the platform."""
    if platform == Platform.INSTAGRAM:
        from app.services.scraper._instagram import InstagramScraper
        return InstagramScraper()
    elif platform == Platform.YOUTUBE:
        from app.services.scraper._youtube import YouTubeScraper
        return YouTubeScraper()
    elif platform == Platform.TIKTOK:
        from app.services.scraper._tiktok import TikTokScraper
        return TikTokScraper()
    else:
        from app.core.exceptions import DownloadError
        raise DownloadError(f"No scraper for platform: {platform}")


async def scrape_video(url: str, job_id: str | None = None) -> tuple[Path, dict]:
    """Scrape video + metadata via Apify, download video to local storage.

    Returns: (video_path, metadata) — same contract as the old downloader.download().
    metadata keys: title, duration, platform, uploader, description,
                   view_count, like_count, comment_count, thumbnail
    """
    url = normalize_url(url)
    platform = detect_platform(url)
    scraper = _get_scraper(platform)

    logger.info("[scrape] START platform=%s url=%s job_id=%s", platform.value, url, job_id)

    # Scrape + download with retry: if download fails (expired URL, corrupted file),
    # re-scrape to get a fresh URL and try once more.
    last_err: Exception | None = None
    result = None
    for attempt in range(_DOWNLOAD_MAX_ATTEMPTS):
        if attempt > 0:
            logger.warning(
                "[scrape] RETRY attempt=%d/%d after download failure: %s "
                "platform=%s url=%s job_id=%s",
                attempt + 1, _DOWNLOAD_MAX_ATTEMPTS, last_err,
                platform.value, url, job_id,
            )

        result = await scraper.scrape(url)

        logger.info(
            "[scrape] RESULT platform=%s url=%s video_domain=%s "
            "audio=%s duration=%s uploader=%s views=%s likes=%s job_id=%s",
            result.platform, url, _safe_domain(result.video_url),
            bool(result.audio_url), result.duration,
            result.uploader, result.view_count, result.like_count,
            job_id,
        )

        logger.info(
            "[scrape] DOWNLOAD START video_domain=%s job_id=%s attempt=%d",
            _safe_domain(result.video_url), job_id, attempt + 1,
        )
        try:
            video_path = await download_video_to_local(
                result.video_url, audio_url=result.audio_url, job_id=job_id,
                http_headers=result.http_headers,
            )
            break  # Download succeeded
        except DownloadError as e:
            last_err = e
            logger.warning(
                "[scrape] DOWNLOAD FAILED attempt=%d/%d error=%s "
                "platform=%s url=%s job_id=%s",
                attempt + 1, _DOWNLOAD_MAX_ATTEMPTS, e,
                platform.value, url, job_id,
            )
            if attempt + 1 >= _DOWNLOAD_MAX_ATTEMPTS:
                raise
            # Will retry with fresh URL from re-scrape

    metadata = {
        "title": result.title,
        "duration": result.duration,
        "platform": result.platform,
        "uploader": result.uploader,
        "description": result.description,
        "view_count": result.view_count,
        "like_count": result.like_count,
        "comment_count": result.comment_count,
        "thumbnail": result.thumbnail,
    }

    logger.info(
        "[scrape] DONE platform=%s url=%s video_path=%s size=%d job_id=%s",
        result.platform, url, video_path.name,
        video_path.stat().st_size,
        job_id,
    )

    return video_path, metadata


async def scrape_comments(url: str, max_comments: int = 50) -> list[dict]:
    """Extract comments via Apify.

    Returns: [{"text": str, "likes": int, "author": str}]
    Returns empty list if comments are not available.
    """
    try:
        url = normalize_url(url)
        platform = detect_platform(url)
        scraper = _get_scraper(platform)
        return await scraper.scrape_comments(url, max_comments)
    except Exception as e:
        logger.warning("Comment extraction failed for %s: %s", url, e)
        return []
