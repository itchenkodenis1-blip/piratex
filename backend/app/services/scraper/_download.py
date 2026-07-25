import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from app.core.exceptions import DownloadError
from app.services.scraper._apify_client import _safe_domain
from app.storage import storage
from app.storage.local import get_videos_dir

logger = logging.getLogger(__name__)

_FFPROBE_TIMEOUT = 15  # seconds


async def _validate_video(path: Path) -> bool:
    """Validate video file with ffprobe. Returns True if valid, False otherwise."""
    try:
        process = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,width,height",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=_FFPROBE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("ffprobe timeout validating %s", path.name)
        try:
            process.kill()
        except ProcessLookupError:
            pass
        return False
    except Exception as e:
        logger.warning("ffprobe failed for %s: %s", path.name, e)
        return False

    if process.returncode != 0:
        logger.warning(
            "ffprobe validation failed for %s (rc=%d): %s",
            path.name, process.returncode, stderr.decode(errors="replace")[:200],
        )
        return False

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        logger.warning("ffprobe returned invalid JSON for %s", path.name)
        return False

    # Must have at least one video stream
    streams = data.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    if not has_video:
        logger.warning("No video stream in %s", path.name)
        return False

    # Duration must be > 0
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    if duration <= 0:
        logger.warning("Video %s has duration=%.1f", path.name, duration)
        return False

    return True


async def _download_file(url: str, output_path: Path) -> None:
    """Download a file from URL to disk."""
    domain = _safe_domain(url)
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                content_length = resp.headers.get("content-length", "unknown")
                content_type = resp.headers.get("content-type", "unknown")
                logger.info(
                    "[download] START domain=%s status=%d content_length=%s "
                    "content_type=%s → %s",
                    domain, resp.status_code, content_length,
                    content_type, output_path.name,
                )
                with open(output_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
    except httpx.HTTPError as e:
        elapsed = time.monotonic() - t0
        logger.error(
            "[download] HTTP ERROR domain=%s elapsed=%.1fs error=%s → %s",
            domain, elapsed, e, output_path.name,
        )
        output_path.unlink(missing_ok=True)
        raise DownloadError(f"Failed to download from CDN: {e}") from e

    elapsed = time.monotonic() - t0
    file_size = output_path.stat().st_size if output_path.exists() else 0
    if not output_path.exists() or file_size == 0:
        logger.error(
            "[download] EMPTY FILE domain=%s elapsed=%.1fs → %s",
            domain, elapsed, output_path.name,
        )
        output_path.unlink(missing_ok=True)
        raise DownloadError("Downloaded file is empty")

    # Guard: if CDN returned HTML (expired/error page) instead of video
    if content_type.startswith("text/"):
        logger.error(
            "[download] GOT TEXT content_type=%s size=%d domain=%s → %s "
            "(likely expired or error page)",
            content_type, file_size, domain, output_path.name,
        )
        output_path.unlink(missing_ok=True)
        raise DownloadError(
            f"CDN returned {content_type} instead of video "
            f"(expired URL or error page, {file_size} bytes)"
        )

    # Guard: video files should be at least 50KB (HTML error pages are smaller)
    _MIN_VIDEO_SIZE = 50_000
    if file_size < _MIN_VIDEO_SIZE:
        logger.error(
            "[download] SUSPICIOUSLY SMALL size=%d domain=%s → %s "
            "(min expected %d bytes)",
            file_size, domain, output_path.name, _MIN_VIDEO_SIZE,
        )
        output_path.unlink(missing_ok=True)
        raise DownloadError(
            f"Downloaded file too small ({file_size} bytes), "
            "likely not a valid video"
        )

    logger.info(
        "[download] OK domain=%s size=%d bytes elapsed=%.1fs → %s",
        domain, file_size, elapsed, output_path.name,
    )


_MERGE_TIMEOUT = 90  # seconds


async def _merge_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Merge separate video and audio streams using ffmpeg."""
    from app.core.ffmpeg_limiter import ffmpeg_slot

    async with ffmpeg_slot():
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c", "copy",
            "-y",
            str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=_MERGE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            raise DownloadError(f"ffmpeg merge timed out after {_MERGE_TIMEOUT}s")

    if process.returncode != 0:
        raise DownloadError(f"ffmpeg merge failed: {stderr.decode()}")

    # Clean up separate files
    video_path.unlink(missing_ok=True)
    audio_path.unlink(missing_ok=True)


async def download_video_to_local(
    video_url: str,
    audio_url: str | None = None,
    filename: str | None = None,
    job_id: str | None = None,
) -> Path:
    """Download video from a direct URL to local storage.

    If audio_url is provided (Instagram DASH), downloads both streams
    and merges them with ffmpeg.

    Each job gets its own file (job_id in filename) to prevent race conditions
    when concurrent jobs share the same URL — cleanup of one job must never
    delete another job's video file.
    """
    if not filename:
        url_hash = hashlib.md5(video_url.encode()).hexdigest()[:12]
        suffix = f"_{job_id[:8]}" if job_id else ""
        filename = f"{url_hash}{suffix}.mp4"

    output_dir = get_videos_dir()
    output_path = output_dir / filename

    if audio_url:
        # Separate streams — download both and merge
        video_only = output_dir / f"{output_path.stem}_video.mp4"
        audio_only = output_dir / f"{output_path.stem}_audio.m4a"

        logger.info(
            "[download] MERGE mode: video_domain=%s audio_domain=%s job_id=%s",
            _safe_domain(video_url), _safe_domain(audio_url), job_id,
        )
        try:
            await asyncio.gather(
                _download_file(video_url, video_only),
                _download_file(audio_url, audio_only),
            )
            await _merge_video_audio(video_only, audio_only, output_path)
        except Exception:
            video_only.unlink(missing_ok=True)
            audio_only.unlink(missing_ok=True)
            raise
        logger.info("Merged video+audio: %s (%d bytes)", output_path, output_path.stat().st_size)
    else:
        # Single stream — download directly
        await _download_file(video_url, output_path)
        logger.info("Video downloaded: %s (%d bytes)", output_path, output_path.stat().st_size)

    # Validate downloaded video
    if not await _validate_video(output_path):
        output_path.unlink(missing_ok=True)
        raise DownloadError(
            "Video file is corrupt or has no video stream. "
            "ffprobe validation failed after download."
        )

    # Upload to remote storage (S3/R2) if configured
    storage_key = f"videos/{filename}"
    await storage.write_from_path(storage_key, output_path)

    return output_path


async def ensure_video_local(video_path: Path) -> Path:
    """Ensure video exists on local disk. Download from S3 if missing.

    When multiple workers run in parallel, Task 1 may finish on Worker A
    and Task 2 may land on Worker B where the file doesn't exist.
    Task 1 already uploaded the video to S3, so we can fetch it.

    Uses streaming download (download_to_path) to avoid loading
    the entire video into memory — critical for 50MB+ files.
    """
    if video_path.exists() and video_path.stat().st_size > 0:
        return video_path  # Already local — fast path

    s3_key = f"videos/{video_path.name}"

    if not await storage.file_exists(s3_key):
        raise DownloadError(
            f"Video not found locally or in storage: {video_path.name}"
        )

    logger.info("Video not local, downloading from S3: %s", s3_key)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    await storage.download_to_path(s3_key, video_path)

    if not await _validate_video(video_path):
        video_path.unlink(missing_ok=True)
        raise DownloadError("Video from S3 failed validation")

    return video_path
