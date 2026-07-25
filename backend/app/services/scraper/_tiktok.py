import logging

from app.config import settings
from app.core.exceptions import DownloadError
from app.services.scraper._apify_client import _safe_domain, _summarise_item, run_actor
from app.services.scraper._base import PlatformScraper, ScrapeResult, _first

logger = logging.getLogger(__name__)


def _parse_apidojo(item: dict, url: str) -> ScrapeResult:
    """Parse apidojo/tiktok-scraper response into ScrapeResult."""
    video = item.get("video") or {}
    channel = item.get("channel") or {}

    video_url = video.get("url")
    logger.info(
        "[tiktok:apidojo] raw item url=%s video_url_domain=%s "
        "video_keys=%s channel_keys=%s item_keys=%s",
        url, _safe_domain(video_url),
        list(video.keys())[:10], list(channel.keys())[:10], list(item.keys()),
    )
    if not video_url:
        logger.error(
            "[tiktok:apidojo] NO VIDEO URL url=%s item_summary=%s",
            url, _summarise_item(item),
        )
        raise DownloadError(
            "TikTok: актор не вернул video URL. "
            "Возможно, это фото-слайдшоу — поддерживаются только видео."
        )

    return ScrapeResult(
        video_url=video_url,
        title=item.get("title"),
        duration=video.get("duration"),
        platform="tiktok",
        uploader=channel.get("username") or channel.get("name"),
        description=item.get("title"),
        view_count=item.get("views"),
        like_count=item.get("likes"),
        comment_count=item.get("comments"),
        thumbnail=video.get("cover") or video.get("thumbnail"),
    )


def _parse_clockworks(item: dict, url: str) -> ScrapeResult:
    """Parse clockworks/tiktok-scraper response into ScrapeResult.

    NOTE: clockworks does NOT return a video download URL.
    The videoMeta only has coverUrl, not a playable video link.
    We still extract metadata — the caller must handle missing video_url.
    """
    if item.get("error"):
        logger.error(
            "[tiktok:clockworks] ACTOR ERROR url=%s error=%s keys=%s",
            url, item["error"], list(item.keys()),
        )
        raise DownloadError(f"TikTok: {item['error']}")

    if item.get("isSlideshow"):
        logger.warning("[tiktok:clockworks] SLIDESHOW url=%s keys=%s", url, list(item.keys()))
        raise DownloadError(
            "Фото-слайдшоу TikTok пока не поддерживаются. "
            "Отправьте ссылку на видео."
        )

    video_meta = item.get("videoMeta") or {}

    logger.info(
        "[tiktok:clockworks] raw item url=%s keys=%s videoMeta_keys=%s",
        url, list(item.keys()),
        list(video_meta.keys()) if isinstance(video_meta, dict) else type(video_meta).__name__,
    )

    return ScrapeResult(
        video_url="",  # clockworks doesn't provide video download URL
        title=item.get("text"),
        duration=video_meta.get("duration") if isinstance(video_meta, dict) else None,
        platform="tiktok",
        uploader=(
            item.get("authorMeta", {}).get("name")
            if isinstance(item.get("authorMeta"), dict)
            else None
        ),
        description=item.get("text"),
        view_count=item.get("playCount"),
        like_count=item.get("diggCount"),
        comment_count=item.get("commentCount"),
        thumbnail=video_meta.get("coverUrl") if isinstance(video_meta, dict) else None,
    )


class TikTokScraper(PlatformScraper):
    """TikTok video scraper via Apify.

    Primary:  apidojo/tiktok-scraper  — returns video URL + metadata
    Fallback: clockworks/tiktok-scraper — metadata only (no video URL)
    """

    async def scrape(self, url: str) -> ScrapeResult:
        # --- Primary: apidojo/tiktok-scraper ---
        try:
            items = await run_actor(
                actor_id=settings.apify_tiktok_actor,
                input_data={"startUrls": [url]},
            )
            item = items[0]
            result = _parse_apidojo(item, url)
            logger.info("[tiktok] apidojo OK for %s", url)
            return result

        except DownloadError:
            raise
        except Exception as primary_err:
            logger.warning(
                "[tiktok] apidojo failed for %s: %s — trying clockworks fallback",
                url, primary_err,
            )

        # --- Fallback: clockworks/tiktok-scraper (metadata only) ---
        try:
            items = await run_actor(
                actor_id=settings.apify_tiktok_fallback_actor,
                input_data={"postURLs": [url], "maxItems": 1},
            )
            item = items[0]
            result = _parse_clockworks(item, url)

            if not result.video_url:
                raise DownloadError(
                    "TikTok: не удалось получить ссылку на видео. "
                    "Возможно, видео приватное или удалено."
                )

            return result

        except DownloadError:
            raise
        except Exception as fallback_err:
            logger.error(
                "[tiktok] Both apidojo and clockworks failed for %s: %s",
                url, fallback_err,
            )
            raise DownloadError(
                "TikTok: не удалось получить данные о видео. "
                "Проверьте ссылку или попробуйте позже."
            ) from fallback_err

    async def scrape_comments(self, url: str, max_comments: int = 50) -> list[dict]:
        """Comments not needed for TikTok MVP."""
        return []
