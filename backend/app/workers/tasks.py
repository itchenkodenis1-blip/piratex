"""arq task definitions — decomposed from orchestrator.process_job.

Three tasks form a chain (fresh analysis):
  task_scrape_and_download → task_extract_and_analyze → task_generate_content

Cached replay (video already in library):
  task_cached_replay → task_generate_content

Each task publishes progress via Redis Pub/Sub (consumed by the web
process and forwarded to WebSocket clients).
"""

import asyncio
import logging
from datetime import datetime

from arq import ArqRedis
from arq.connections import RedisSettings
from sqlalchemy import select

from app.config import settings
from app.core.exceptions import NotYouTubeShortsError, VideoTooLongError
from app.core.progress import progress_tracker
from app.database import get_db_session
from app.models.job import Job, JobStatus
from app.models.library import LibraryReel, Tag, UserScript, library_reel_tags
from app.services import audio, frame_extractor, summarizer
from app.services.language_detect import detect_same_language
from app.core.error_classifier import get_user_friendly_error, is_transient_error
from app.core.cost_tracker import get_cost_tracker, init_cost_tracker
from app.services.scraper import scrape_comments, scrape_video
from app.services.strategist import generate_strategy
from app.services.telegram import edit_telegram_message, format_result_card, format_result_keyboard, notify_admin_job_failure
from app.services.vision_analyzer import _analyze_single_frame

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cancellation guard — catches arq timeout (CancelledError) and marks FAILED
# ---------------------------------------------------------------------------

async def _fail_job_on_cancel(job_id: str, stage: str):
    """Mark job as FAILED using a fresh DB session after CancelledError.

    When arq kills a task via job_timeout, CancelledError (BaseException)
    bypasses `except Exception` blocks. This helper uses a fresh session
    since the original one may be rolled back / broken.
    """
    try:
        async with get_db_session() as db:
            job = await db.get(Job, job_id)
            if job and job.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
                job.status = JobStatus.FAILED
                job.error = f"Превышено время обработки (этап: {stage})"
                await db.commit()
                await progress_tracker.broadcast(job.id, {
                    "type": "progress",
                    "status": "failed",
                    "progress": job.progress or 0,
                    "message": "Превышено время обработки. Попробуйте ещё раз.",
                    "error": True,
                })
                # Showcase: notify admin dashboard
                try:
                    from app.core.showcase_tracker import emit_showcase_event
                    await emit_showcase_event("job_status",
                        job_id=str(job.id),
                        old_status="running",
                        new_status="failed",
                        progress=str(job.progress or 0),
                        video_platform=job.video_platform or "",
                        video_author=job.video_author or "",
                        error=f"Timeout at {stage}",
                    )
                except Exception:
                    pass
                logger.info("Job %s marked FAILED after cancellation at %s", job_id, stage)
    except Exception:
        logger.exception("Failed to mark cancelled job %s as FAILED", job_id)


# ---------------------------------------------------------------------------
# Telegram status messages (only sent on status transitions)
# ---------------------------------------------------------------------------

_TG_STATUS_MESSAGES: dict[JobStatus, str] = {
    JobStatus.DOWNLOADING: "\u23f3 Скачиваю видео...",
    JobStatus.EXTRACTING_AUDIO: "\u23f3 Извлекаю аудио...",
    JobStatus.TRANSCRIBING: "\u23f3 Транскрибирую...",
    JobStatus.EXTRACTING_FRAMES: "\u23f3 Анализирую кадры...",
    JobStatus.ANALYZING_FRAMES: "\u23f3 Анализирую кадры...",
    JobStatus.GENERATING_SUMMARY: "\u23f3 Генерирую сценарий...",
}


# ---------------------------------------------------------------------------
# Heartbeat — periodically touch updated_at so watchdog won't kill live jobs
# ---------------------------------------------------------------------------

_HEARTBEAT_INTERVAL = 60  # seconds


class _Heartbeat:
    """Background task that touches job.updated_at every N seconds.

    Keeps the watchdog from marking a legitimately-running job as stuck
    during long stages (frame analysis, content generation).
    """

    def __init__(self, job_id: str, interval: int = _HEARTBEAT_INTERVAL):
        self._job_id = job_id
        self._interval = interval
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                async with get_db_session() as db:
                    from sqlalchemy import text
                    await db.execute(
                        text("UPDATE jobs SET updated_at = NOW() WHERE id = :id"),
                        {"id": self._job_id},
                    )
                    await db.commit()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Heartbeat write failed for job %s", self._job_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _update_job(db, job: Job, status: JobStatus, progress: float, message: str):
    """Update job status in DB and broadcast via Redis Pub/Sub."""
    old_status = job.status
    job.status = status
    job.progress = progress
    job.progress_message = message
    await db.commit()
    await progress_tracker.broadcast(
        job.id,
        {
            "type": "progress",
            "status": status.value,
            "progress": progress,
            "message": message,
        },
    )

    # Showcase: broadcast job status transitions to admin dashboard
    if status != old_status:
        try:
            from app.core.showcase_tracker import emit_showcase_event
            from app.models.user import User as _User
            extra = {
                "job_id": str(job.id),
                "old_status": old_status.value if old_status else "",
                "new_status": status.value,
                "progress": str(progress),
            }
            if job.video_platform:
                extra["video_platform"] = job.video_platform
            if job.video_author:
                extra["video_author"] = job.video_author
            if job.video_title:
                extra["video_title"] = job.video_title[:80]
            if job.source:
                extra["source"] = job.source
            if status == JobStatus.FAILED and job.error:
                extra["error"] = job.error[:120]
            # Mask user email for showcase display
            user_email = (await db.execute(
                select(_User.email).where(_User.id == job.user_id)
            )).scalar()
            if user_email:
                local, _, domain = user_email.partition("@")
                if domain:
                    if len(local) <= 2:
                        extra["masked_email"] = f"{local[0]}***@{domain}" if local else f"***@{domain}"
                    else:
                        extra["masked_email"] = f"{local[:3]}***@{domain}"
            await emit_showcase_event("job_status", **extra)
        except Exception:
            pass  # best-effort, never block job processing

    # Telegram progress: only on status transitions (throttle)
    if (
        job.telegram_chat_id
        and job.telegram_message_id
        and status != old_status
        and status in _TG_STATUS_MESSAGES
    ):
        try:
            await edit_telegram_message(
                job.telegram_chat_id,
                job.telegram_message_id,
                settings.telegram_bot_token,
                _TG_STATUS_MESSAGES[status],
            )
        except Exception:
            logger.warning("Failed to edit Telegram progress for job %s", job.id)


async def _notify_telegram_completion(job: Job):
    """Send final result card to Telegram when job completes."""
    if not job.telegram_chat_id or not job.telegram_message_id:
        return

    try:
        text = format_result_card(job)
        reply_markup = format_result_keyboard(job, settings.app_url)

        await edit_telegram_message(
            job.telegram_chat_id,
            job.telegram_message_id,
            settings.telegram_bot_token,
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception:
        logger.warning("Failed to send Telegram completion for job %s", job.id)


async def _notify_telegram_failure(job: Job, user_message: str | None = None):
    """Notify Telegram user that job failed."""
    if not job.telegram_chat_id or not job.telegram_message_id:
        return

    text = f"\u274c {user_message}" if user_message else "\u274c Не удалось проанализировать. Попробуйте другую ссылку."
    try:
        await edit_telegram_message(
            job.telegram_chat_id,
            job.telegram_message_id,
            settings.telegram_bot_token,
            text,
        )
    except Exception:
        logger.debug("Failed to edit Telegram failure for job %s", job.id)


_MAX_TRANSIENT_RETRIES = 2


async def _fail_job(db, job: Job, raw_error: str, *, is_user_error: bool = False):
    """Unified job failure handler.

    - For transient errors (529, timeout, connection): auto-requeue up to 2 times
    - Stores raw error in DB for debugging
    - Sends user-friendly message to frontend via WebSocket
    - Notifies user in Telegram with friendly message
    - Notifies admin in Telegram with raw error (system errors only)
    """
    # AI content policy refusal → treat as user error (no retry, no admin alert)
    if "AI отказал" in raw_error:
        is_user_error = True

    # Auto-requeue transient errors instead of failing
    retry_count = job.retry_count or 0
    if not is_user_error and is_transient_error(raw_error) and retry_count < _MAX_TRANSIENT_RETRIES:
        job.status = JobStatus.PENDING
        job.retry_count = retry_count + 1
        job.progress = 0.0
        job.progress_message = None
        job.error = None
        await db.commit()
        logger.info(
            "Job %s hit transient error, auto-requeuing (attempt %d/%d): %s",
            job.id, retry_count + 2, _MAX_TRANSIENT_RETRIES + 1, raw_error[:120],
        )
        # Re-enqueue via arq with 30s delay
        try:
            from arq.connections import RedisSettings as _RS, create_pool as _create_pool
            from app.database import async_session
            from app.models.user import UserSettings
            async with async_session() as settings_db:
                us = (await settings_db.execute(
                    select(UserSettings).where(UserSettings.user_id == job.user_id)
                )).scalar_one_or_none()
                language = (us.language if us and us.language else "ru")
                custom_content = us.custom_content_prompt if us else None
                custom_strategy = us.custom_strategy_prompt if us else None
                profile_json = us.profile_json if us else None

            pool = await _create_pool(_RS.from_dsn(settings.redis_url))
            if job.transcript and job.frames:
                await pool.enqueue_job(
                    "task_generate_content",
                    job.id, language, custom_content, custom_strategy, profile_json, [],
                    _defer_by=30,
                )
            else:
                await pool.enqueue_job(
                    "task_scrape_and_download",
                    job.id, job.url, language, custom_content, custom_strategy, profile_json,
                    _defer_by=30,
                )
            await pool.close()
        except Exception as requeue_err:
            logger.error("Failed to requeue job %s: %s", job.id, requeue_err)
        return

    friendly = get_user_friendly_error(raw_error)

    job.status = JobStatus.FAILED
    job.error = raw_error
    await db.commit()

    await progress_tracker.broadcast(
        job.id,
        {
            "type": "progress",
            "status": "failed",
            "progress": job.progress,
            "message": friendly,
            "error": True,
        },
    )

    # Showcase: notify admin dashboard about failure
    try:
        from app.core.showcase_tracker import emit_showcase_event
        from app.models.user import User as _User
        extra: dict[str, str] = {
            "job_id": str(job.id),
            "old_status": "running",
            "new_status": "failed",
            "progress": str(job.progress or 0),
        }
        if job.video_platform:
            extra["video_platform"] = job.video_platform
        if job.video_author:
            extra["video_author"] = job.video_author
        if job.video_title:
            extra["video_title"] = job.video_title[:80]
        if job.source:
            extra["source"] = job.source
        if raw_error:
            extra["error"] = raw_error[:120]
        user_email_for_showcase = (await db.execute(
            select(_User.email).where(_User.id == job.user_id)
        )).scalar()
        if user_email_for_showcase:
            local, _, domain = user_email_for_showcase.partition("@")
            if domain:
                if len(local) <= 2:
                    extra["masked_email"] = f"{local[0]}***@{domain}" if local else f"***@{domain}"
                else:
                    extra["masked_email"] = f"{local[:3]}***@{domain}"
        await emit_showcase_event("job_status", **extra)
    except Exception:
        pass  # best-effort

    await _notify_telegram_failure(job, friendly)

    # Admin alert for system errors (not user-input validation)
    if not is_user_error:
        # Fetch user email for admin context
        from sqlalchemy import select as sa_select
        from app.models.user import User as _User
        user_email = (await db.execute(
            sa_select(_User.email).where(_User.id == job.user_id)
        )).scalar()
        await notify_admin_job_failure(job, raw_error, user_email=user_email)


async def _broadcast_data(job_id: str, msg_type: str, data: dict):
    """Broadcast incremental data to the frontend via Redis Pub/Sub."""
    await progress_tracker.broadcast(job_id, {"type": msg_type, **data})


# ---------------------------------------------------------------------------
# Task 1: Scrape + Download
# ---------------------------------------------------------------------------

async def task_scrape_and_download(
    ctx: dict,
    job_id: str,
    url: str,
    language: str = "ru",
    custom_content_prompt: str | None = None,
    custom_strategy_prompt: str | None = None,
    profile_json: dict | None = None,
):
    """Scrape video metadata via Apify, download MP4, save metadata to DB."""
    redis: ArqRedis = ctx["redis"]
    tracker = init_cost_tracker()
    heartbeat = _Heartbeat(job_id)

    async with get_db_session() as db:
        job = await db.get(Job, job_id)
        if not job:
            logger.error("Job %s not found", job_id)
            return

        comments_task: asyncio.Task | None = None
        heartbeat.start()

        try:
            await _update_job(db, job, JobStatus.DOWNLOADING, 0.05, "Скачиваем видео...")

            # Start comment extraction in background
            comments_task = asyncio.create_task(scrape_comments(url))

            video_path, metadata = await scrape_video(url, job_id=job_id)

            # Check duration limit
            duration = metadata.get("duration", 0) or 0
            if duration > settings.max_video_duration_seconds:
                raise VideoTooLongError(
                    f"Video is {duration}s, max allowed is {settings.max_video_duration_seconds}s"
                )

            # Save metadata to job
            job.video_title = metadata.get("title")
            job.video_duration = metadata.get("duration")
            job.video_platform = metadata.get("platform")
            job.video_author = metadata.get("uploader")
            job.video_description = metadata.get("description")
            job.video_views = metadata.get("view_count")
            job.video_likes = metadata.get("like_count")
            job.video_comments = metadata.get("comment_count")
            job.thumbnail_url = metadata.get("thumbnail")
            await db.commit()

            # Broadcast metadata to frontend
            await _broadcast_data(job_id, "metadata", {
                "title": job.video_title,
                "duration": job.video_duration,
                "platform": job.video_platform,
                "author": job.video_author,
                "views": job.video_views,
                "likes": job.video_likes,
                "comments": job.video_comments,
                "thumbnail": metadata.get("thumbnail"),
            })

            # Collect comments (graceful — empty list if not available)
            try:
                comments = await comments_task
            except Exception:
                comments = []

            # Save partial costs (apify) to DB
            job.cost_breakdown = tracker.to_dict()
            await db.commit()

            # Enqueue next task
            await redis.enqueue_job(
                "task_extract_and_analyze",
                job_id,
                str(video_path),
                language,
                custom_content_prompt,
                custom_strategy_prompt,
                profile_json,
                comments,
            )

        except asyncio.CancelledError:
            await heartbeat.stop()
            if comments_task:
                comments_task.cancel()
            logger.warning("Job %s cancelled (timeout) at scrape stage", job_id)
            await asyncio.shield(_fail_job_on_cancel(job_id, "scrape"))
            raise

        except (NotYouTubeShortsError, VideoTooLongError) as e:
            await heartbeat.stop()
            if comments_task:
                comments_task.cancel()
            logger.warning("Job %s rejected: %s", job_id, e)
            await _fail_job(db, job, str(e), is_user_error=True)

        except Exception as e:
            await heartbeat.stop()
            comments_task.cancel()
            logger.exception("Job %s failed at scrape stage: %s", job_id, e)
            await _fail_job(db, job, str(e))

        else:
            await heartbeat.stop()


# ---------------------------------------------------------------------------
# Task 2: Extract frames + audio, transcribe, analyze frames
# ---------------------------------------------------------------------------

async def task_extract_and_analyze(
    ctx: dict,
    job_id: str,
    video_path_str: str,
    language: str,
    custom_content_prompt: str | None,
    custom_strategy_prompt: str | None,
    profile_json: dict | None,
    comments: list[dict],
):
    """Extract frames + audio in parallel, transcribe, analyze each frame with vision."""
    from pathlib import Path

    from app.services.scraper._download import ensure_video_local
    from app.services.transcriber import transcribe

    redis: ArqRedis = ctx["redis"]
    tracker = init_cost_tracker()
    heartbeat = _Heartbeat(job_id)
    video_path = Path(video_path_str)
    video_path = await ensure_video_local(video_path)

    audio_path: Path | None = None

    async with get_db_session() as db:
        job = await db.get(Job, job_id)
        if not job:
            logger.error("Job %s not found", job_id)
            return

        transcript_task: asyncio.Task | None = None
        _frame_tasks: list[asyncio.Task] = []
        heartbeat.start()

        try:
            duration = job.video_duration or 0
            frame_interval = max(2.0, duration / 20)
            scene_timestamps = []
            t = 0.0
            while t < duration:
                scene_timestamps.append(round(t, 2))
                t += frame_interval
            if not scene_timestamps:
                scene_timestamps = [0.0]

            total_frames = len(scene_timestamps)

            # Phase 1: Extract audio (sequential — so the user sees this step)
            await _update_job(
                db, job, JobStatus.EXTRACTING_AUDIO, 0.08,
                "Извлекаем аудио...",
            )
            audio_path = await audio.extract_audio(video_path)

            # Phase 2: Start transcription in background
            await _update_job(
                db, job, JobStatus.TRANSCRIBING, 0.10,
                "Транскрибируем аудио...",
            )

            async def _run_transcription():
                if audio_path is None:
                    logger.info("No audio stream — skipping transcription")
                    await _broadcast_data(job_id, "transcript", {"segments": []})
                    return []
                segs = await transcribe(audio_path)
                await _broadcast_data(job_id, "transcript", {
                    "segments": [s.model_dump() for s in segs],
                })
                return segs

            transcript_task = asyncio.create_task(_run_transcription())

            # Phase 3: Extract frames (runs in parallel with transcription)
            await _update_job(
                db, job, JobStatus.EXTRACTING_FRAMES, 0.12,
                f"Раскадровка — {total_frames} кадров...",
            )

            # Vision pipeline — each frame analyzed the moment it is extracted
            from app.core.openai_client import get_openai_client
            _client = get_openai_client()
            vision_semaphore = asyncio.Semaphore(settings.max_concurrent_vision_calls)
            _frame_tasks: list[asyncio.Task] = []
            _frame_results: list = []

            async def _analyze_and_broadcast(i: int, path, ts: float) -> None:
                async with vision_semaphore:
                    analysis = await _analyze_single_frame(_client, path, ts, i, None, language=language)
                _frame_results.append(analysis)
                done = len(_frame_results)
                await _broadcast_data(job_id, "frame_analyzed", {"frame": analysis.model_dump()})
                await progress_tracker.broadcast(job_id, {
                    "type": "progress",
                    "status": JobStatus.ANALYZING_FRAMES.value,
                    "progress": round(0.15 + (done / total_frames) * 0.55, 3),
                    "message": f"Анализируем кадр {done}/{total_frames}...",
                })

            async def on_frame_ready(i: int, path, ts: float) -> None:
                minutes, seconds = divmod(int(ts), 60)
                await _broadcast_data(job_id, "frame_stub", {
                    "frame": {
                        "frame_index": i,
                        "timestamp": ts,
                        "timecode": f"{minutes:02d}:{seconds:02d}",
                    }
                })
                _frame_tasks.append(asyncio.create_task(_analyze_and_broadcast(i, path, ts)))

            await frame_extractor.extract_frames_pipelined(
                video_path, scene_timestamps, job.id, on_frame_ready,
                max_concurrent=2,
            )

            await _update_job(db, job, JobStatus.ANALYZING_FRAMES, 0.15, f"Анализируем {total_frames} кадров...")
            await asyncio.gather(*_frame_tasks)

            # Delete local frame copies (S3 has them, local no longer needed)
            if settings.s3_bucket:
                import shutil
                from app.storage.local import get_frames_dir
                shutil.rmtree(get_frames_dir(job.id), ignore_errors=True)

            # Wait for transcript
            transcript_segments = await transcript_task
            frame_analyses = sorted(_frame_results, key=lambda r: r.timestamp)

            # Fail-fast: if both frames AND transcript are empty, no data for analysis
            if not frame_analyses and not transcript_segments:
                from app.core.exceptions import InsufficientDataError
                raise InsufficientDataError(
                    "Не удалось извлечь данные из видео: "
                    "кадры и транскрипт пустые. Попробуйте другое видео."
                )
            if not frame_analyses:
                logger.warning(
                    "Job %s: 0 frames extracted, proceeding with transcript only",
                    job_id,
                )
            if not transcript_segments:
                logger.warning(
                    "Job %s: empty transcript, proceeding with frames only",
                    job_id,
                )

            # Serialize for the next task
            transcript_dicts = [s.model_dump() for s in transcript_segments]
            frames_dicts = [f.model_dump() for f in frame_analyses]

            # Merge cost from previous task (apify) + current (whisper, vision)
            prev_costs = job.cost_breakdown or {}
            tracker.apify_usd = prev_costs.get("apify_usd", 0.0)

            # Save intermediate results to DB (so they survive across tasks)
            job.transcript = transcript_dicts
            job.frames = frames_dicts
            job.cost_breakdown = tracker.to_dict()
            await db.commit()

            # Cleanup: video and audio no longer needed after extraction
            from app.services.storage_cleanup import cleanup_job_intermediates
            await cleanup_job_intermediates(video_path, audio_path)

            # Enqueue content generation
            await redis.enqueue_job(
                "task_generate_content",
                job_id,
                language,
                custom_content_prompt,
                custom_strategy_prompt,
                profile_json,
                comments,
            )

        except asyncio.CancelledError:
            await heartbeat.stop()
            # Cancel orphaned background tasks to stop consuming API quota
            for t in _frame_tasks:
                t.cancel()
            if transcript_task and not transcript_task.done():
                transcript_task.cancel()
            logger.warning("Job %s cancelled (timeout) at extract/analyze stage", job_id)
            await asyncio.shield(_fail_job_on_cancel(job_id, "extract/analyze"))
            raise

        except Exception as e:
            await heartbeat.stop()
            logger.exception("Job %s failed at extract/analyze stage: %s", job_id, e)
            await _fail_job(db, job, str(e))
            # Cleanup intermediates even on failure
            from app.services.storage_cleanup import cleanup_job_intermediates
            await cleanup_job_intermediates(video_path, audio_path)

        else:
            await heartbeat.stop()


# ---------------------------------------------------------------------------
# Task 3: Generate content + strategy, save to library
# ---------------------------------------------------------------------------

async def task_generate_content(
    ctx: dict,
    job_id: str,
    language: str,
    custom_content_prompt: str | None,
    custom_strategy_prompt: str | None,
    profile_json: dict | None,
    comments: list[dict],
):
    """Run Claude Sonnet (content) + Claude Haiku (strategy) in parallel, save results."""
    from app.schemas.analysis import FrameAnalysis, TranscriptSegment

    tracker = init_cost_tracker()
    heartbeat = _Heartbeat(job_id)

    async with get_db_session() as db:
        job = await db.get(Job, job_id)
        if not job:
            logger.error("Job %s not found", job_id)
            return

        # Restore costs from previous tasks
        prev_costs = job.cost_breakdown or {}
        tracker.apify_usd = prev_costs.get("apify_usd", 0.0)
        tracker.whisper_usd = prev_costs.get("whisper_usd", 0.0)
        tracker.vision_usd = prev_costs.get("vision_usd", 0.0)
        tracker._vision_calls = prev_costs.get("vision_calls", 0)

        content_task: asyncio.Task | None = None
        strategy_task: asyncio.Task | None = None
        heartbeat.start()

        try:
            await _update_job(db, job, JobStatus.GENERATING_SUMMARY, 0.80, "Генерируем сценарий и стратегию...")

            # Reconstruct typed objects from saved JSON
            transcript_segments = [TranscriptSegment(**s) for s in (job.transcript or [])]
            frame_analyses = [FrameAnalysis(**f) for f in (job.frames or [])]

            metadata = {
                "title": job.video_title,
                "duration": job.video_duration,
                "platform": job.video_platform,
                "uploader": job.video_author,
                "description": job.video_description,
                "view_count": job.video_views,
                "like_count": job.video_likes,
                "comment_count": job.video_comments,
            }

            # Detect if original language matches target language
            full_transcript = " ".join(seg.text for seg in transcript_segments)
            same_language = detect_same_language(full_transcript, language)

            # Run content + strategy in parallel
            content_task = asyncio.create_task(
                summarizer.generate_summary(
                    metadata, transcript_segments, frame_analyses,
                    comments=comments,
                    target_language=language,
                    custom_prompt=custom_content_prompt,
                    video_url=job.url,
                    profile_json=profile_json,
                    same_language=same_language,
                )
            )
            strategy_task = asyncio.create_task(
                generate_strategy(
                    metadata, transcript_segments, frame_analyses,
                    comments=comments,
                    target_language=language,
                    custom_prompt=custom_strategy_prompt,
                    profile_json=profile_json,
                )
            )

            adaptation, strategy = await asyncio.gather(content_task, strategy_task)

            # Broadcast results
            await _broadcast_data(job_id, "content_ready", {"summary": adaptation.model_dump()})
            await _broadcast_data(job_id, "strategy_ready", {"strategy": strategy.model_dump()})

            # Save results and publish to library
            transcript_dicts = [s.model_dump() for s in transcript_segments]
            frames_dicts = [f.model_dump() for f in frame_analyses]
            full_transcript_text = " ".join(seg.text for seg in transcript_segments)

            combined_summary = {
                **adaptation.model_dump(),
                **strategy.model_dump(),
            }

            tags_data = {
                "language": strategy.language,
                "content_format": strategy.content_format,
                "topics": strategy.topics,
                "keywords": strategy.keywords,
                "niche": strategy.niche,
            }

            # Check for existing library entry with same URL
            existing = await db.execute(
                select(LibraryReel).where(LibraryReel.url == job.url)
            )
            library_reel = existing.scalar_one_or_none()

            if library_reel is None:
                library_reel = LibraryReel(
                    job_id=job.id,
                    submitted_by=job.user_id,
                    url=job.url,
                    video_title=job.video_title,
                    video_duration=job.video_duration,
                    video_platform=job.video_platform,
                    video_author=job.video_author,
                    video_description=job.video_description,
                    video_views=job.video_views,
                    video_likes=job.video_likes,
                    video_comments=job.video_comments,
                    transcript_text=full_transcript_text,
                    transcript_json=transcript_dicts,
                    frames_json=frames_dicts,
                    original_language=tags_data.get("language", "en"),
                    content_format=tags_data.get("content_format", "other"),
                    cover_frame_index=strategy.cover.recommended_frame_index,
                )
                db.add(library_reel)
                await db.flush()

                # Create/link tags
                all_tags = list(tags_data.get("topics", []))
                niche = tags_data.get("niche")
                if niche:
                    all_tags.append(niche)
                for kw in tags_data.get("keywords", []):
                    all_tags.append(kw.lower().replace(" ", "-"))

                for tag_slug in set(all_tags):
                    if not tag_slug:
                        continue
                    result = await db.execute(select(Tag).where(Tag.name == tag_slug))
                    tag = result.scalar_one_or_none()
                    if tag is None:
                        tag = Tag(name=tag_slug, display_name=tag_slug.replace("-", " ").title(), category="topic")
                        db.add(tag)
                        await db.flush()
                    await db.execute(
                        library_reel_tags.insert().values(
                            library_reel_id=library_reel.id, tag_id=tag.id
                        )
                    )
            else:
                if job.video_views is not None and (library_reel.video_views is None or library_reel.video_views < job.video_views):
                    library_reel.video_views = job.video_views
                if job.video_likes is not None and (library_reel.video_likes is None or library_reel.video_likes < job.video_likes):
                    library_reel.video_likes = job.video_likes
                if job.video_comments is not None and (library_reel.video_comments is None or library_reel.video_comments < job.video_comments):
                    library_reel.video_comments = job.video_comments
                if library_reel.cover_frame_index is None:
                    library_reel.cover_frame_index = strategy.cover.recommended_frame_index

            # Finalize job
            job.transcript = transcript_dicts
            job.frames = frames_dicts
            job.adaptation_summary = combined_summary
            job.library_reel_id = library_reel.id
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            job.progress_message = "Готово!"
            job.completed_at = datetime.utcnow()
            job.cost_breakdown = tracker.to_dict()

            # Auto-create UserScript
            existing_user_script = await db.execute(
                select(UserScript).where(
                    UserScript.user_id == job.user_id,
                    UserScript.library_reel_id == library_reel.id,
                )
            )
            user_script_obj = existing_user_script.scalar_one_or_none()
            if user_script_obj is None:
                user_script_obj = UserScript(
                    user_id=job.user_id,
                    library_reel_id=library_reel.id,
                    script=adaptation.script,
                    description=adaptation.description,
                    editor_instructions=adaptation.editor_instructions,
                    original_script=adaptation.script,
                    original_description=adaptation.description,
                    original_editor_instructions=adaptation.editor_instructions,
                )
                db.add(user_script_obj)

            # Auto-track author profile for trend monitoring
            if job.video_author and job.video_platform:
                try:
                    from app.services.trend_monitor import ensure_tracked_profile
                    await ensure_tracked_profile(
                        db=db,
                        platform=job.video_platform,
                        username=job.video_author,
                        niche=tags_data.get("niche"),
                        display_name=job.video_author,
                        topics=tags_data.get("topics", []),
                    )
                except Exception as track_err:
                    logger.warning("[trends] Failed to track profile: %s", track_err)

            await db.commit()

            await progress_tracker.broadcast(
                job.id,
                {"type": "progress", "status": "completed", "progress": 1.0, "message": "Готово!"},
            )

            # Auto-generate the second-language version as a SEPARATE iteration.
            # Best-effort: a failure here must never affect the completed primary job.
            try:
                from app.schemas.profile import SUPPORTED_LANGUAGES
                dual_enabled = bool(profile_json and profile_json.get("dual_language_enabled"))
                second_lang = (profile_json or {}).get("second_language")
                # profile_json is a raw dict from the queue — validate the language ourselves.
                if second_lang not in SUPPORTED_LANGUAGES:
                    second_lang = None
                if (
                    dual_enabled
                    and second_lang
                    and second_lang != language
                    and user_script_obj is not None
                ):
                    from app.models.library import ScriptTranslation
                    from app.schemas.analysis import AdaptationSummary as _AdaptationSummary
                    from app.services.translator import compute_source_revision, translate_script

                    await db.refresh(user_script_obj)
                    source = _AdaptationSummary(
                        script=user_script_obj.script,
                        description=user_script_obj.description,
                        editor_instructions=user_script_obj.editor_instructions,
                    )
                    translated = await translate_script(
                        source=source,
                        source_language=language,
                        target_language=second_lang,
                        profile_json=profile_json,
                    )
                    revision = compute_source_revision(source)
                    existing_tr = await db.execute(
                        select(ScriptTranslation).where(
                            ScriptTranslation.user_script_id == user_script_obj.id,
                            ScriptTranslation.language == second_lang,
                        )
                    )
                    tr = existing_tr.scalar_one_or_none()
                    if tr is None:
                        tr = ScriptTranslation(
                            user_script_id=user_script_obj.id,
                            language=second_lang,
                            script=translated.script,
                            description=translated.description,
                            editor_instructions=translated.editor_instructions,
                            original_script=translated.script,
                            original_description=translated.description,
                            original_editor_instructions=translated.editor_instructions,
                            source_revision=revision,
                        )
                        db.add(tr)
                    else:
                        tr.script = translated.script
                        tr.description = translated.description
                        tr.editor_instructions = translated.editor_instructions
                        tr.source_revision = revision
                    await db.commit()
                    await progress_tracker.broadcast(
                        job.id,
                        {
                            "type": "translation_ready",
                            "language": second_lang,
                            "script": translated.script,
                            "description": translated.description,
                            "editor_instructions": translated.editor_instructions,
                        },
                    )
            except Exception as tr_err:
                logger.warning("[translate] auto-translate failed for job %s: %s", job.id, tr_err)

            # Showcase: notify admin dashboard about completion
            try:
                from app.core.showcase_tracker import emit_showcase_event
                from app.models.user import User as _User
                extra: dict[str, str] = {
                    "job_id": str(job.id),
                    "old_status": "generating_summary",
                    "new_status": "completed",
                    "progress": "1.0",
                }
                if job.video_platform:
                    extra["video_platform"] = job.video_platform
                if job.video_author:
                    extra["video_author"] = job.video_author
                if job.video_title:
                    extra["video_title"] = job.video_title[:80]
                if job.source:
                    extra["source"] = job.source
                user_email_sc = (await db.execute(
                    select(_User.email).where(_User.id == job.user_id)
                )).scalar()
                if user_email_sc:
                    local, _, domain = user_email_sc.partition("@")
                    if domain:
                        if len(local) <= 2:
                            extra["masked_email"] = f"{local[0]}***@{domain}" if local else f"***@{domain}"
                        else:
                            extra["masked_email"] = f"{local[:3]}***@{domain}"
                await emit_showcase_event("job_status", **extra)
            except Exception:
                pass  # best-effort

            # Notify Telegram user with result card
            await _notify_telegram_completion(job)

            # Send founder welcome on first completed job (idempotent)
            try:
                from app.services.founder_welcome import send_founder_welcome
                await send_founder_welcome(db, job.user_id)
            except Exception as welcome_err:
                logger.warning("Failed to send founder welcome: %s", welcome_err)

            # Onboarding drip: first analysis completed
            try:
                from app.models.user import User
                from app.services.onboarding_drip import drip_first_analysis
                drip_user = (await db.execute(
                    select(User).where(User.id == job.user_id)
                )).scalar_one_or_none()
                if drip_user:
                    await drip_first_analysis(db, drip_user, job)
            except Exception:
                logger.debug("Onboarding drip (first_analysis) failed", exc_info=True)

        except asyncio.CancelledError:
            await heartbeat.stop()
            if content_task and not content_task.done():
                content_task.cancel()
            if strategy_task and not strategy_task.done():
                strategy_task.cancel()
            logger.warning("Job %s cancelled (timeout) at content generation", job_id)
            await asyncio.shield(_fail_job_on_cancel(job_id, "content_generation"))
            raise

        except Exception as e:
            await heartbeat.stop()
            logger.exception("Job %s failed at content generation stage: %s", job_id, e)
            await _fail_job(db, job, str(e))

        else:
            await heartbeat.stop()


# ---------------------------------------------------------------------------
# Task 4: Cached Replay — simulate progress for already-analyzed videos
# ---------------------------------------------------------------------------

async def task_cached_replay(
    ctx: dict,
    job_id: str,
    language: str = "ru",
    custom_content_prompt: str | None = None,
    custom_strategy_prompt: str | None = None,
    profile_json: dict | None = None,
):
    """Replay cached analysis data with progress animation, then generate personalized script.

    When a video was already analyzed by another user (library_hit), we simulate
    the analysis progress using cached data from the Job (pre-populated from LibraryReel),
    then run real script generation for this user's profile/prompts.
    """
    redis: ArqRedis = ctx["redis"]

    async with get_db_session() as db:
        job = await db.get(Job, job_id)
        if not job:
            logger.error("Cached replay: Job %s not found", job_id)
            return

        try:
            # Load cached data from LibraryReel (Job is created empty
            # to prevent _send_current_state from leaking data on WS connect)
            lib_reel = await db.get(LibraryReel, job.library_reel_id)
            if not lib_reel:
                raise RuntimeError(f"LibraryReel {job.library_reel_id} not found")

            # Get thumbnail from original job
            orig_job_result = await db.execute(
                select(Job.thumbnail_url).where(Job.id == lib_reel.job_id)
            )
            orig_thumbnail = orig_job_result.scalar_one_or_none()

            transcript_data = lib_reel.transcript_json or []
            frames_data = lib_reel.frames_json or []
            total_frames = len(frames_data)

            # --- Simulated progress with cached data ---

            # Step 1: "Downloading"
            await _update_job(db, job, JobStatus.DOWNLOADING, 0.05, "Скачиваем видео...")
            await asyncio.sleep(1.0)

            # Broadcast metadata from LibraryReel
            await _broadcast_data(job_id, "metadata", {
                "title": lib_reel.video_title,
                "duration": lib_reel.video_duration,
                "platform": lib_reel.video_platform,
                "author": lib_reel.video_author,
                "views": lib_reel.video_views,
                "likes": lib_reel.video_likes,
                "comments": lib_reel.video_comments,
                "thumbnail": orig_thumbnail,
            })

            # Write metadata to Job (so GET /jobs/{id} works after replay)
            job.video_title = lib_reel.video_title
            job.video_duration = lib_reel.video_duration
            job.video_platform = lib_reel.video_platform
            job.video_author = lib_reel.video_author
            job.video_description = lib_reel.video_description
            job.video_views = lib_reel.video_views
            job.video_likes = lib_reel.video_likes
            job.video_comments = lib_reel.video_comments
            job.thumbnail_url = orig_thumbnail
            await db.commit()

            await asyncio.sleep(0.5)

            # Step 2: "Extracting audio"
            await _update_job(db, job, JobStatus.EXTRACTING_AUDIO, 0.08, "Извлекаем аудио...")
            await asyncio.sleep(0.5)

            # Step 3: "Transcribing"
            await _update_job(db, job, JobStatus.TRANSCRIBING, 0.10, "Транскрибируем аудио...")
            await asyncio.sleep(1.0)

            # Broadcast transcript from cache
            await _broadcast_data(job_id, "transcript", {"segments": transcript_data})
            await asyncio.sleep(0.3)

            # Step 4: "Extracting frames" — broadcast stubs one by one
            await _update_job(
                db, job, JobStatus.EXTRACTING_FRAMES, 0.12,
                f"Раскадровка — {total_frames} кадров...",
            )
            for frame in frames_data:
                await _broadcast_data(job_id, "frame_stub", {
                    "frame": {
                        "frame_index": frame.get("frame_index", 0),
                        "timestamp": frame.get("timestamp", 0),
                        "timecode": frame.get("timecode", "00:00"),
                    }
                })
                await asyncio.sleep(0.3)

            # Step 5: "Analyzing frames" — broadcast analyzed frames one by one
            await _update_job(
                db, job, JobStatus.ANALYZING_FRAMES, 0.15,
                f"Анализируем {total_frames} кадров...",
            )
            for i, frame in enumerate(frames_data):
                await _broadcast_data(job_id, "frame_analyzed", {"frame": frame})
                done = i + 1
                await progress_tracker.broadcast(job_id, {
                    "type": "progress",
                    "status": JobStatus.ANALYZING_FRAMES.value,
                    "progress": round(0.15 + (done / max(total_frames, 1)) * 0.55, 3),
                    "message": f"Анализируем кадр {done}/{total_frames}...",
                })
                await asyncio.sleep(0.3)

            # Write transcript + frames to Job DB (task_generate_content reads them)
            job.transcript = transcript_data
            job.frames = frames_data
            await db.commit()

            # --- Real script generation ---
            # Enqueue task_generate_content for personalized script
            await redis.enqueue_job(
                "task_generate_content",
                job_id,
                language,
                custom_content_prompt,
                custom_strategy_prompt,
                profile_json,
                [],  # comments — not stored in LibraryReel
            )

        except asyncio.CancelledError:
            logger.warning("Job %s cancelled (timeout) at cached replay", job_id)
            await asyncio.shield(_fail_job_on_cancel(job_id, "cached_replay"))
            raise

        except Exception as e:
            logger.exception("Cached replay job %s failed: %s", job_id, e)
            await _fail_job(db, job, str(e))


# ---------------------------------------------------------------------------
# Task 5: Re-extract frames for old jobs (migration)
# ---------------------------------------------------------------------------

async def task_reextract_frames(_ctx: dict, job_id: str):
    """Re-download video and re-extract frames to S3 for an existing completed job.

    This is a lightweight migration task — it only extracts frames,
    skipping transcription, vision analysis, and content generation
    (those results are already in the DB).
    """
    from pathlib import Path

    async with get_db_session() as db:
        job = await db.get(Job, job_id)
        if not job:
            logger.warning("Reextract: job %s not found", job_id)
            return

        try:
            logger.info("Reextract: starting for job %s (%s)", job_id, job.url)

            # Re-download video
            video_path, _metadata = await scrape_video(job.url, job_id=job_id)

            # Calculate timestamps from existing frames metadata or duration
            timestamps = []
            if job.frames:
                timestamps = [f["timestamp"] for f in job.frames if "timestamp" in f]
            if not timestamps:
                duration = job.video_duration or 0
                interval = max(2.0, duration / 20)
                t = 0.0
                while t < duration:
                    timestamps.append(round(t, 2))
                    t += interval

            # Extract and upload to S3 (no vision analysis, no broadcast)
            async def _noop(_i, _p, _ts):
                pass

            await frame_extractor.extract_frames_pipelined(
                video_path, timestamps, job.id, _noop, max_concurrent=4,
            )

            # Clean up local video
            try:
                video_path.unlink(missing_ok=True)
            except Exception:
                pass

            logger.info("Reextract: done for job %s — %d frames uploaded", job_id, len(timestamps))

        except asyncio.CancelledError:
            logger.warning("Reextract: job %s cancelled (timeout)", job_id)
            raise

        except Exception as e:
            logger.exception("Reextract: job %s failed: %s", job_id, e)


# ---------------------------------------------------------------------------
# Lightweight tasks (notifications, etc.)
# ---------------------------------------------------------------------------

async def task_notify_support_reply(ctx: dict, message_id: str, user_id: str):
    """Deferred task: notify user about a support reply if still unread."""
    from app.services.support_notifier import notify_user_support_reply

    await notify_user_support_reply(message_id, user_id)


# ---------------------------------------------------------------------------
# arq WorkerSettings
# ---------------------------------------------------------------------------

class WorkerSettings:
    """Configuration for arq worker process."""
    functions = [
        task_scrape_and_download,
        task_extract_and_analyze,
        task_generate_content,
        task_cached_replay,
        task_reextract_frames,
        task_notify_support_reply,
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 8
    job_timeout = 900  # 15 minutes per task (ffmpeg contention under load)
    retry_jobs = False  # Disabled: watchdog is the sole retry mechanism (DB-tracked retry_count)
    max_tries = 1
    health_check_interval = 30
