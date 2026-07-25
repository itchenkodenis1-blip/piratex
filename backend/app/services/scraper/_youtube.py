import asyncio
import json
import logging

import httpx

from app.config import settings
from app.core.exceptions import DownloadError, NotYouTubeShortsError
from app.services.scraper._apify_client import _safe_domain, _summarise_item, run_actor
from app.services.scraper._base import PlatformScraper, ScrapeResult, _first
from app.services.scraper._platform import extract_youtube_video_id

logger = logging.getLogger(__name__)

# Maximum duration for YouTube Shorts (seconds).
# YouTube allows Shorts up to 3 minutes (180s); we add a safety margin.
_MAX_SHORTS_DURATION = 190

# Primary actor retry settings
_PRIMARY_MAX_ATTEMPTS = 2
_PRIMARY_RETRY_DELAY = 5  # seconds


def _parse_duration_str(value) -> float | None:
    """Parse duration: float/int seconds, or string like '3:33' / '0:36'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(value)
    except (ValueError, IndexError):
        return None


async def _is_youtube_short(video_id: str) -> bool:
    """Check if a YouTube video is a Short via HEAD request.

    HEAD https://www.youtube.com/shorts/{id}
    → 200 = Short
    → 303/redirect = NOT a Short

    On network error, returns True (fail-open — duration check is the safety net).
    """
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            resp = await client.head(f"https://www.youtube.com/shorts/{video_id}")
            is_short = resp.status_code == 200
            logger.info(
                "[youtube:shorts-gate] video_id=%s status=%d is_short=%s",
                video_id, resp.status_code, is_short,
            )
            return is_short
    except Exception as e:
        logger.warning(
            "[youtube:shorts-gate] HEAD check failed video_id=%s error=%s, allowing through",
            video_id, e,
        )
        return True


def _parse_dc_solutions(item: dict, url: str) -> ScrapeResult:
    """Parse response from dc_solutions~youtube-downloader-pro."""
    video_url = item.get("downloadUrl")
    logger.info(
        "[youtube:dc_solutions] raw item url=%s success=%s "
        "downloadUrl_domain=%s duration=%s keys=%s",
        url, item.get("success"), _safe_domain(video_url),
        item.get("duration"), list(item.keys()),
    )
    if not item.get("success"):
        logger.error(
            "[youtube:dc_solutions] FAILED url=%s error=%s item_summary=%s",
            url, item.get("error"), _summarise_item(item),
        )
        raise DownloadError(
            f"YouTube actor failed for {url}: {item.get('error', 'unknown error')}"
        )

    if not video_url:
        logger.error(
            "[youtube:dc_solutions] NO DOWNLOAD URL url=%s item_summary=%s",
            url, _summarise_item(item),
        )
        raise DownloadError(f"YouTube actor returned no download URL for {url}")

    duration = _parse_duration_str(item.get("duration"))

    return ScrapeResult(
        video_url=video_url,
        title=item.get("title"),
        duration=duration,
        platform="youtube",
        uploader=item.get("author"),
        description=None,
        view_count=None,
        like_count=None,
        comment_count=None,
        thumbnail=item.get("thumbnail"),
    )


def _parse_marielise(item: dict, url: str) -> ScrapeResult:
    """Parse response from marielise.dev~youtube-video-downloader."""
    video_url = item.get("downloadUrl")
    logger.info(
        "[youtube:marielise] raw item url=%s status=%s "
        "downloadUrl_domain=%s duration=%s keys=%s",
        url, item.get("status"), _safe_domain(video_url),
        item.get("duration"), list(item.keys()),
    )
    if item.get("status") != "success":
        logger.error(
            "[youtube:marielise] FAILED url=%s error=%s item_summary=%s",
            url, item.get("error"), _summarise_item(item),
        )
        raise DownloadError(
            f"YouTube actor failed for {url}: {item.get('error', 'unknown error')}"
        )

    if not video_url:
        logger.error(
            "[youtube:marielise] NO DOWNLOAD URL url=%s item_summary=%s",
            url, _summarise_item(item),
        )
        raise DownloadError(f"YouTube actor returned no download URL for {url}")

    duration = _parse_duration_str(item.get("duration"))

    return ScrapeResult(
        video_url=video_url,
        title=item.get("title"),
        duration=duration,
        platform="youtube",
        uploader=item.get("uploader"),
        description=item.get("description"),
        view_count=_first(item.get("viewCount"), item.get("view_count")),
        like_count=_first(item.get("likeCount"), item.get("like_count")),
        comment_count=_first(item.get("commentCount"), item.get("comment_count")),
        thumbnail=item.get("thumbnailUrl") or item.get("thumbnail"),
    )


def _check_duration_gate(result: ScrapeResult) -> ScrapeResult:
    """Reject long videos even if HEAD check passed."""
    if result.duration and result.duration > _MAX_SHORTS_DURATION:
        raise NotYouTubeShortsError(
            "Поддерживаются только YouTube Shorts (до 3 мин). "
            f"Это видео длится {int(result.duration)} сек."
        )
    return result


async def _ytdlp_fallback(video_id: str) -> ScrapeResult:
    """Third fallback: local yt-dlp, no Apify involved.

    Uses Railway's own IP — a fundamentally different channel from Apify proxies.
    Only extracts metadata + direct URL (--dump-json), does NOT download the file.
    """
    url = f"https://www.youtube.com/shorts/{video_id}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp",
            "--dump-json",
            "--no-playlist",
            "--no-warnings",
            "--format", "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        raise DownloadError("yt-dlp timed out after 30s")

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace")[:300]
        logger.error(
            "[youtube:yt-dlp] FAILED video_id=%s rc=%d stderr=%s",
            video_id, proc.returncode, err_msg,
        )
        raise DownloadError(f"yt-dlp failed (rc={proc.returncode}): {err_msg}")

    info = json.loads(stdout.decode())
    logger.info(
        "[youtube:yt-dlp] raw info video_id=%s title=%s duration=%s "
        "url_domain=%s formats_count=%d keys=%s",
        video_id, (info.get("title") or "")[:60], info.get("duration"),
        _safe_domain(info.get("url")),
        len(info.get("formats") or []),
        [k for k in info.keys() if k != "formats"][:20],
    )

    # When yt-dlp selects bestvideo+bestaudio, it returns requested_formats
    # with separate video and audio URLs (DASH). Handle both cases.
    video_url = info.get("url")
    audio_url = None

    requested_formats = info.get("requested_formats") or []
    if not video_url and requested_formats:
        # DASH: separate video + audio streams
        for fmt in requested_formats:
            if fmt.get("vcodec", "none") != "none" and fmt.get("url"):
                video_url = fmt["url"]
            if fmt.get("acodec", "none") != "none" and fmt.get("vcodec", "none") == "none" and fmt.get("url"):
                audio_url = fmt["url"]
        if video_url:
            logger.info(
                "[youtube:yt-dlp] DASH mode video_id=%s video_domain=%s "
                "audio_domain=%s",
                video_id, _safe_domain(video_url), _safe_domain(audio_url),
            )

    if not video_url:
        # Fallback: find any format with a video codec
        formats = info.get("formats") or []
        for fmt in reversed(formats):
            if fmt.get("url") and fmt.get("vcodec", "none") != "none":
                video_url = fmt["url"]
                logger.info(
                    "[youtube:yt-dlp] using format fallback video_id=%s "
                    "format_id=%s vcodec=%s",
                    video_id, fmt.get("format_id"), fmt.get("vcodec"),
                )
                break
    if not video_url:
        logger.error(
            "[youtube:yt-dlp] NO PLAYABLE URL video_id=%s "
            "formats_count=%d requested_formats=%d",
            video_id, len(info.get("formats") or []),
            len(requested_formats),
        )
        raise DownloadError("yt-dlp returned no playable URL")

    return ScrapeResult(
        video_url=video_url,
        audio_url=audio_url,
        title=info.get("title"),
        duration=info.get("duration"),
        platform="youtube",
        uploader=info.get("uploader") or info.get("channel"),
        description=info.get("description"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        comment_count=info.get("comment_count"),
        thumbnail=info.get("thumbnail"),
    )


class YouTubeScraper(PlatformScraper):
    """YouTube Shorts scraper with three-tier fallback.

    1. Primary: dc_solutions~youtube-downloader-pro (2 attempts with retry)
    2. Fallback: marielise.dev~youtube-video-downloader (canonical /watch?v= URL)
    3. Local: yt-dlp via subprocess (Railway IP, no Apify)

    Only YouTube Shorts are supported. Regular YouTube videos are rejected
    before calling Apify to avoid unnecessary costs.
    """

    async def scrape(self, url: str) -> ScrapeResult:
        # --- Shorts gate: reject non-Shorts BEFORE calling Apify ---
        video_id = extract_youtube_video_id(url)
        if not video_id:
            raise NotYouTubeShortsError(
                "Не удалось распознать YouTube видео. Проверьте ссылку."
            )
        is_short = await _is_youtube_short(video_id)
        if not is_short:
            raise NotYouTubeShortsError(
                "Поддерживаются только YouTube Shorts (до 3 мин). "
                "Это обычное видео YouTube — попробуйте ссылку на Short."
            )

        # --- Primary actor: dc_solutions (with retry) ---
        primary_err: Exception | None = None
        for attempt in range(_PRIMARY_MAX_ATTEMPTS):
            try:
                if attempt > 0:
                    logger.info(
                        "[youtube] Primary actor retry #%d for %s after %ds",
                        attempt, url, _PRIMARY_RETRY_DELAY,
                    )
                    await asyncio.sleep(_PRIMARY_RETRY_DELAY)
                items = await run_actor(
                    actor_id=settings.apify_youtube_actor,
                    input_data={"url": url},
                    timeout=120,
                )
                if not items:
                    raise DownloadError(f"YouTube actor returned no results for {url}")
                result = _parse_dc_solutions(items[0], url)
                return _check_duration_gate(result)
            except NotYouTubeShortsError:
                raise
            except Exception as exc:
                primary_err = exc
                logger.warning(
                    "[youtube] Primary actor (%s) attempt %d/%d failed for %s: %s",
                    settings.apify_youtube_actor, attempt + 1,
                    _PRIMARY_MAX_ATTEMPTS, url, exc,
                )

        # --- Fallback actor: marielise.dev (with canonical URL) ---
        # Use /watch?v= format — some actors handle it better than /shorts/
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        fallback_err: Exception | None = None
        try:
            items = await run_actor(
                actor_id=settings.apify_youtube_fallback_actor,
                input_data={
                    "urls": [{"url": watch_url}],
                    "quality": "360",
                    "format": "default",
                    "useResidentialProxy": True,
                },
                timeout=600,
            )
            if not items:
                raise DownloadError(f"YouTube fallback actor returned no results for {url}")
            result = _parse_marielise(items[0], url)
            return _check_duration_gate(result)
        except NotYouTubeShortsError:
            raise
        except Exception as exc:
            fallback_err = exc
            logger.warning(
                "[youtube] Fallback actor failed for %s: %s, trying yt-dlp...",
                url, exc,
            )

        # --- Third fallback: local yt-dlp ---
        try:
            result = await _ytdlp_fallback(video_id)
            logger.info("[youtube] yt-dlp fallback succeeded for %s", url)
            return _check_duration_gate(result)
        except NotYouTubeShortsError:
            raise
        except Exception as ytdlp_err:
            logger.error(
                "[youtube] All 3 fallbacks failed for %s. "
                "Primary: %s, Fallback: %s, yt-dlp: %s",
                url, primary_err, fallback_err, ytdlp_err,
            )
            raise DownloadError(
                f"Не удалось скачать YouTube видео {url}. "
                "Попробуйте позже или используйте другую ссылку."
            )

    async def scrape_comments(self, url: str, max_comments: int = 50) -> list[dict]:
        """Disabled — comment count already comes from the main video actor.

        Saves ~$0.002/analysis by not calling the separate Apify comments actor
        (streamers~youtube-comments-scraper).
        """
        return []
