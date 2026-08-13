import asyncio
import logging

from app.config import settings
from app.core.exceptions import DownloadError
from app.services.scraper._apify_client import _safe_domain, _summarise_item, run_actor
from app.services.scraper._base import PlatformScraper, ScrapeResult, _first

logger = logging.getLogger(__name__)


def _parse_apidojo(item: dict, url: str) -> ScrapeResult | None:
    """Parse apidojo/tiktok-scraper response into ScrapeResult.

    Returns None when the actor reports no results (couldn't resolve the post)
    instead of raising — the caller falls through to yt-dlp / clockworks.
    """
    if "noResults" in item:
        logger.warning("[tiktok:apidojo] noResults url=%s", url)
        return None

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
        return None

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


async def _ytdlp_tiktok_metadata(url: str) -> dict | None:
    """Fetch TikTok metadata + direct video URL via yt-dlp.

    Used as fallback when the apidojo actor returns noResults (it has been
    broken on all posts since ~Aug 2026) — yt-dlp resolves TikTok reliably.
    """
    import yt_dlp

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 60,
        "noplaylist": True,
    }

    loop = asyncio.get_running_loop()

    def _run():
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as e:
                last_err = e
                if attempt < 2:
                    import time
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.warning("[tiktok] yt-dlp attempt %d/3 failed url=%s err=%s", attempt + 1, url, type(e).__name__)
                continue
            if not info:
                if attempt < 2:
                    continue
                return None
            video_url = info.get("url") or ""
            audio_url = None
            formats = info.get("formats") or []
            best_video = None
            best_audio = None
            for f in formats:
                if f.get("protocol") in ("m3u8_native", "m3u8"):
                    continue
                vcodec = f.get("vcodec") or ""
                acodec = f.get("acodec") or ""
                f_url = f.get("url") or ""
                if not f_url:
                    continue
                if vcodec != "none" and acodec not in ("none", None):
                    if not video_url:
                        video_url = f_url
                    if not best_video:
                        best_video = f
                elif vcodec != "none" and not best_video:
                    best_video = f
                elif acodec != "none" and not best_audio:
                    best_audio = f
            if not video_url and best_video:
                video_url = best_video["url"]
            if best_audio:
                audio_url = best_audio["url"]
            if not video_url:
                if attempt < 2:
                    continue
                return None
            return {
                "video_url": video_url,
                "audio_url": audio_url,
                "title": info.get("title"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader") or info.get("channel"),
                "description": info.get("description"),
                "view_count": info.get("view_count"),
                "like_count": info.get("like_count"),
                "comment_count": info.get("comment_count"),
                "thumbnail": info.get("thumbnail"),
            }
        logger.warning("[tiktok] yt-dlp exhausted retries url=%s err=%s", url, last_err)
        return None

    try:
        return await loop.run_in_executor(None, _run)
    except Exception as e:
        logger.warning("[tiktok] yt-dlp fallback failed url=%s err=%s", url, type(e).__name__)
        return None


class TikTokScraper(PlatformScraper):
    """TikTok video scraper.

    Primary:  apidojo/tiktok-scraper — returns video URL + metadata
    Fallback: yt-dlp — reliable direct video URL + metadata
    Last:     clockworks/tiktok-scraper — metadata only (no video URL)
    """

    async def scrape(self, url: str) -> ScrapeResult:
        # --- Primary: apidojo/tiktok-scraper ---
        try:
            items = await run_actor(
                actor_id=settings.apify_tiktok_actor,
                input_data={"startUrls": [{"url": url}]},
            )
            result = _parse_apidojo(items[0], url) if items else None
            if result:
                logger.info("[tiktok] apidojo OK for %s", url)
                return result
            logger.info("[tiktok] apidojo no usable result for %s — trying yt-dlp", url)
        except Exception as primary_err:
            logger.warning(
                "[tiktok] apidojo failed for %s: %s — trying yt-dlp",
                url, primary_err,
            )

        # --- Fallback: yt-dlp (reliable direct video URL) ---
        try:
            yt = await _ytdlp_tiktok_metadata(url)
            if yt and yt.get("video_url"):
                logger.info("[tiktok] yt-dlp OK for %s", url)
                return ScrapeResult(
                    video_url=yt["video_url"],
                    audio_url=yt.get("audio_url"),
                    title=yt.get("title"),
                    duration=yt.get("duration"),
                    platform="tiktok",
                    uploader=yt.get("uploader"),
                    description=yt.get("description"),
                    view_count=yt.get("view_count"),
                    like_count=yt.get("like_count"),
                    comment_count=yt.get("comment_count"),
                    thumbnail=yt.get("thumbnail"),
                )
        except Exception as yt_err:
            logger.warning("[tiktok] yt-dlp fallback failed for %s: %s", url, yt_err)

        # --- Last: clockworks/tiktok-scraper (metadata only) ---
        try:
            items = await run_actor(
                actor_id=settings.apify_tiktok_fallback_actor,
                input_data={"postURLs": [url], "maxItems": 1},
            )
            result = _parse_clockworks(items[0], url) if items else None

            if result and result.video_url:
                return result

            if result:
                raise DownloadError(
                    "TikTok: не удалось получить ссылку на видео. "
                    "Возможно, видео приватное или удалено."
                )
            raise DownloadError("TikTok: акторы не вернули данных о видео.")

        except DownloadError:
            raise
        except Exception as fallback_err:
            logger.error(
                "[tiktok] apidojo, yt-dlp and clockworks all failed for %s: %s",
                url, fallback_err,
            )
            raise DownloadError(
                "TikTok: не удалось получить данные о видео. "
                "Проверьте ссылку или попробуйте позже."
            ) from fallback_err

    async def scrape_comments(self, url: str, max_comments: int = 50) -> list[dict]:
        """Comments not needed for TikTok MVP."""
        return []
