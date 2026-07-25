import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable

from app.storage import storage
from app.storage.local import get_frames_dir

logger = logging.getLogger(__name__)

_FFMPEG_TIMEOUT = 30  # seconds per frame extraction
_S3_UPLOAD_TIMEOUT = 60  # seconds per frame upload to S3


async def _run_ffmpeg(args: list[str], output: Path) -> bool:
    """Run ffmpeg with timeout. Returns True if output file is valid.

    Acquires a global ffmpeg slot to prevent resource exhaustion
    when multiple jobs run concurrently on the same worker.
    """
    from app.core.ffmpeg_limiter import ffmpeg_slot

    try:
        async with ffmpeg_slot():
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=_FFMPEG_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning("ffmpeg timeout after %ds: %s", _FFMPEG_TIMEOUT, " ".join(args[:6]))
                try:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
                return False

        if process.returncode != 0:
            logger.warning(
                "ffmpeg failed (rc=%d): %s",
                process.returncode, stderr.decode(errors="replace")[-500:],
            )
            return False

        # Check output exists and is non-empty
        if not output.exists() or output.stat().st_size == 0:
            logger.warning("ffmpeg produced empty/no output: %s", output.name)
            return False

        return True

    except Exception as e:
        logger.warning("ffmpeg subprocess error: %s", e)
        return False


async def _extract_single(video_path: Path, timestamp: float, output: Path) -> Path | None:
    """Extract one frame with 2-strategy fallback.

    Strategy 1: Fast seek (-ss before -i) — fastest, works for most codecs.
    Strategy 2: Accurate seek (-ss after -i) — slower but handles VP9/WebM.
    """
    # Strategy 1: fast seek
    ok = await _run_ffmpeg(
        ["ffmpeg", "-ss", str(timestamp), "-i", str(video_path),
         "-frames:v", "1", "-q:v", "2", "-y", str(output)],
        output,
    )
    if ok:
        return output

    # Clean up any partial output before retry
    output.unlink(missing_ok=True)

    # Strategy 2: accurate seek
    logger.info(
        "Fast seek failed for %s at %.2fs, trying accurate seek",
        video_path.name, timestamp,
    )
    ok = await _run_ffmpeg(
        ["ffmpeg", "-i", str(video_path), "-ss", str(timestamp),
         "-frames:v", "1", "-q:v", "2", "-y", str(output)],
        output,
    )
    if ok:
        return output

    output.unlink(missing_ok=True)
    logger.warning(
        "Frame extraction failed for %s at %.2fs (both strategies)",
        video_path.name, timestamp,
    )
    return None


async def extract_frames(
    video_path: Path,
    timestamps: list[float],
    job_id: str,
) -> list[Path]:
    """Extract frames at specific timestamps (sequential, legacy)."""
    frames_dir = get_frames_dir(job_id)
    paths = []

    for i, ts in enumerate(timestamps):
        output = frames_dir / f"frame_{i:04d}_{ts:.2f}s.jpg"
        path = await _extract_single(video_path, ts, output)
        if path:
            paths.append(path)

    return paths


async def extract_frames_pipelined(
    video_path: Path,
    timestamps: list[float],
    job_id: str,
    on_frame_ready: Callable[[int, Path, float], Awaitable[None]],
    max_concurrent: int = 8,
) -> list[Path]:
    """
    Extract all frames in parallel (up to max_concurrent ffmpeg processes).
    Calls on_frame_ready(frame_index, path, timestamp) immediately for each extracted frame.
    Returns sorted list of frame paths.
    """
    frames_dir = get_frames_dir(job_id)
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[Path] = []

    async def _one(i: int, ts: float) -> None:
        output = frames_dir / f"frame_{i:04d}_{ts:.2f}s.jpg"
        async with semaphore:
            path = await _extract_single(video_path, ts, output)
        if path:
            # Upload to remote storage (S3/R2) with timeout
            storage_key = f"frames/{job_id}/{path.name}"
            try:
                await asyncio.wait_for(
                    storage.write_from_path(storage_key, path),
                    timeout=_S3_UPLOAD_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "S3 upload timeout (%ds) for %s — frame skipped",
                    _S3_UPLOAD_TIMEOUT, storage_key,
                )
                return
            except Exception as exc:
                logger.warning(
                    "S3 upload failed for %s — frame skipped: %s",
                    storage_key, exc,
                )
                return
            results.append(path)
            await on_frame_ready(i, path, ts)

    await asyncio.gather(*[_one(i, ts) for i, ts in enumerate(timestamps)])

    extracted = len(results)
    total = len(timestamps)
    if extracted < total:
        logger.warning(
            "Frame extraction: %d/%d frames extracted for job %s",
            extracted, total, job_id,
        )

    return sorted(results, key=lambda p: p.name)
