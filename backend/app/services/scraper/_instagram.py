import asyncio
import base64
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from app.config import settings
from app.services.scraper._apify_client import _safe_domain, _summarise_item, run_actor
from app.services.scraper._base import PlatformScraper, ScrapeResult

logger = logging.getLogger(__name__)

# ── Module-level cache ────────────────────────────────────────────
_CACHE: dict[str, asyncio.Future[dict]] = {}
_CACHE_TTL = timedelta(minutes=5)
_CACHE_TIMES: dict[str, datetime] = {}


def _instagram_cookies_file() -> Path | None:
    """Write IG cookies to a temp file for yt-dlp.

    Accepts either raw Netscape-format text or a single-line base64 blob
    (base64 is easier to paste into a one-line Railway env var).
    """
    raw = settings.instagram_cookies_netscape
    if not raw:
        return None
    netscape = raw
    if "instagram.com" not in raw and "# Netscape" not in raw:
        try:
            decoded = base64.b64decode(raw, validate=True).decode("utf-8")
            if "# Netscape" in decoded or "instagram.com" in decoded:
                netscape = decoded
        except Exception as e:
            logger.warning("IG cookies not Netscape and not base64: %s", e)
    try:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="ig_cookies_", delete=False
        )
        tmp.write(netscape)
        tmp.close()
        return Path(tmp.name)
    except Exception as e:
        logger.warning("Failed to write IG cookies file: %s", e)
        return None


async def _ytdlp_instagram_metadata(url: str) -> dict:
    """Fetch reel metadata + direct video URL via yt-dlp with IG cookies.

    Used as fallback when the Apify actor returns restricted_page without a
    videoUrl (Instagram blocks anonymous scraping in 2026+).
    """
    import yt_dlp

    cookies_file = _instagram_cookies_file()
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 60,
        "noplaylist": True,
    }
    if cookies_file:
        opts["cookiefile"] = str(cookies_file)

    loop = asyncio.get_running_loop()

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            # Pick best mp4 format that has video (merge audio-only is done later
            # by download_video_to_local when audio_url is present).
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
                    # self-contained mp4 with audio — prefer it
                    if video_url != "" and not best_video:
                        best_video = f
                    if not video_url:
                        video_url = f_url
                elif vcodec != "none" and not best_video:
                    best_video = f
                elif acodec != "none" and not best_audio:
                    best_audio = f
            if not video_url and best_video:
                video_url = best_video["url"]
            if best_audio:
                audio_url = best_audio["url"]
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

    try:
        return await loop.run_in_executor(None, _run)
    finally:
        if cookies_file:
            cookies_file.unlink(missing_ok=True)



async def _fetch_instagram(url: str) -> dict:
    """Fetch reel data from Apify, deduplicating concurrent requests."""
    now = datetime.utcnow()

    if url in _CACHE:
        ts = _CACHE_TIMES.get(url, now)
        if now - ts < _CACHE_TTL:
            return await _CACHE[url]
        else:
            del _CACHE[url]
            del _CACHE_TIMES[url]

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[dict] = loop.create_future()
    _CACHE[url] = fut
    _CACHE_TIMES[url] = now

    try:
        items = await run_actor(
            actor_id=settings.apify_instagram_actor,
            input_data={"username": [url], "resultsLimit": 1},
        )
        item = items[0]
        fut.set_result(item)
    except Exception as e:
        fut.set_exception(e)
        _CACHE.pop(url, None)
        _CACHE_TIMES.pop(url, None)
        raise

    stale = [k for k, ts in _CACHE_TIMES.items() if now - ts > _CACHE_TTL]
    for k in stale:
        _CACHE.pop(k, None)
        _CACHE_TIMES.pop(k, None)

    return item


def _parse_metric(value) -> int | None:
    """Parse metric value that may be a string like '56.4k' or '1.2m'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None

    value = value.strip().lower().replace(",", "")
    multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}

    for suffix, mult in multipliers.items():
        if value.endswith(suffix):
            try:
                return int(float(value[:-1]) * mult)
            except ValueError:
                return None

    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_duration(value) -> float | None:
    """Parse duration: float seconds, int seconds, or string 'mm:ss'/'hh:mm:ss'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(value)
    except (ValueError, IndexError):
        return None


class InstagramScraper(PlatformScraper):
    """Instagram Reels scraper via Apify (apify/instagram-reel-scraper)."""

    async def scrape(self, url: str) -> ScrapeResult:
        item = await _fetch_instagram(url)

        # ── Diagnostic: log raw item so we can diagnose failures ──
        video_url = item.get("videoUrl")
        logger.info(
            "[instagram] raw item url=%s videoUrl_domain=%s type=%s "
            "ownerUsername=%s caption_len=%d keys=%s",
            url,
            _safe_domain(video_url),
            item.get("type", "<no-type>"),
            item.get("ownerUsername", "<none>"),
            len(str(item.get("caption") or "")),
            list(item.keys()),
        )
        if not video_url:
            logger.error(
                "[instagram] NO VIDEO URL url=%s item_summary=%s",
                url, _summarise_item(item),
            )
            # Fallback: Apify got restricted_page (no videoUrl). Try yt-dlp with
            # IG cookies, which can still fetch the direct MP4.
            logger.info("[instagram] yt-dlp fallback url=%s", url)
            ytdlp = await _ytdlp_instagram_metadata(url)
            if ytdlp and ytdlp.get("video_url"):
                logger.info("[instagram] yt-dlp fallback OK url=%s", url)
                result = ScrapeResult(
                    video_url=ytdlp["video_url"],
                    audio_url=ytdlp.get("audio_url"),
                    title=ytdlp.get("title"),
                    duration=ytdlp.get("duration"),
                    platform="instagram",
                    uploader=ytdlp.get("uploader"),
                    description=ytdlp.get("description"),
                    view_count=ytdlp.get("view_count"),
                    like_count=ytdlp.get("like_count"),
                    comment_count=ytdlp.get("comment_count"),
                    thumbnail=ytdlp.get("thumbnail"),
                )
                logger.info(
                    "[instagram] parsed (ytdlp) url=%s uploader=%s duration=%s "
                    "views=%s likes=%s video_domain=%s",
                    url, result.uploader, result.duration,
                    result.view_count, result.like_count,
                    _safe_domain(result.video_url),
                )
                return result
            from app.core.exceptions import DownloadError
            raise DownloadError(f"Instagram actor returned no video URL for {url}")

        # Duration: videoDuration (float seconds) or duration (string "0:33")
        duration = _parse_duration(
            item.get("videoDuration") or item.get("duration")
        )

        result = ScrapeResult(
            video_url=video_url,
            title=item.get("caption"),
            duration=duration,
            platform="instagram",
            uploader=item.get("ownerUsername") or item.get("ownerFullName"),
            description=item.get("caption"),
            view_count=_parse_metric(
                item.get("videoViewCount") or item.get("videoPlayCount")
            ),
            like_count=_parse_metric(item.get("likesCount")),
            comment_count=_parse_metric(item.get("commentsCount")),
            thumbnail=item.get("displayUrl"),
        )
        logger.info(
            "[instagram] parsed url=%s uploader=%s duration=%s "
            "views=%s likes=%s video_domain=%s",
            url, result.uploader, result.duration,
            result.view_count, result.like_count,
            _safe_domain(result.video_url),
        )
        return result

    async def scrape_comments(self, url: str, max_comments: int = 50) -> list[dict]:
        """This actor doesn't return comments — return empty list."""
        return []
