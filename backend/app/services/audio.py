import asyncio
import logging
from pathlib import Path

from app.storage import storage
from app.storage.local import get_audio_dir

logger = logging.getLogger(__name__)


async def _has_audio_stream(video_path: Path) -> bool:
    """Check if video file contains an audio stream using ffprobe."""
    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "quiet",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(video_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    return bool(stdout.strip())


async def extract_audio(video_path: Path) -> Path | None:
    """Extract audio from video using ffmpeg. Returns None if video has no audio stream."""
    if not await _has_audio_stream(video_path):
        logger.info("Video %s has no audio stream, skipping extraction", video_path.name)
        return None

    audio_path = get_audio_dir() / f"{video_path.stem}.mp3"

    from app.core.ffmpeg_limiter import ffmpeg_slot

    _AUDIO_TIMEOUT = 120  # seconds — audio extraction can be slow for long videos

    async with ffmpeg_slot():
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", str(video_path),
            "-vn",
            "-acodec", "libmp3lame",
            "-q:a", "4",
            "-y",
            str(audio_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                process.communicate(), timeout=_AUDIO_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("ffmpeg audio extraction timed out after %ds: %s", _AUDIO_TIMEOUT, video_path.name)
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
            raise RuntimeError(f"ffmpeg audio extraction timed out after {_AUDIO_TIMEOUT}s")

    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {stderr.decode()}")

    # Upload to remote storage (S3/R2) if configured
    storage_key = f"audio/{audio_path.name}"
    await storage.write_from_path(storage_key, audio_path)

    return audio_path
