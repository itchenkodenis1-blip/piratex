"""Global ffmpeg process limiter.

Limits the number of concurrent ffmpeg subprocesses across all jobs
in a single worker process. Prevents resource exhaustion (CPU/RAM)
when multiple jobs extract frames/audio simultaneously on Railway.

The semaphore is created lazily on first use (must happen inside
a running event loop). asyncio is single-threaded so the lazy init
is safe — no two coroutines execute the check simultaneously.
"""

import asyncio

from app.config import settings

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    """Return (or create) the process-wide ffmpeg semaphore.

    Safe in asyncio: only one coroutine runs at a time within a single
    event loop, so the None-check-then-assign cannot race.
    """
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent_ffmpeg)
    return _semaphore


class ffmpeg_slot:
    """Async context manager for acquiring an ffmpeg execution slot."""

    async def __aenter__(self):
        self._sem = _get_semaphore()
        await self._sem.acquire()
        return self

    async def __aexit__(self, *exc):
        self._sem.release()
