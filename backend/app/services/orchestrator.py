import asyncio
import logging
from datetime import datetime

from app.config import settings
from app.core.exceptions import VideoTooLongError
from app.core.progress import progress_tracker
from app.database import get_db_session
from app.models.job import Job, JobStatus
from app.models.library import LibraryReel, Tag, UserScript, library_reel_tags
from app.models.trends import ProfileReel
from app.services import audio, frame_extractor, summarizer
from app.services.language_detect import detect_same_language
from app.services.scraper import scrape_video, scrape_comments
from app.services.strategist import generate_strategy
from app.services.vision_analyzer import _analyze_single_frame
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _update_job(db, job: Job, status: JobStatus, progress: float, message: str):
    """Update job status in DB and broadcast via WebSocket."""
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


async def _broadcast_data(job_id: str, msg_type: str, data: dict):
    """Broadcast incremental data to the frontend."""
    await progress_tracker.broadcast(job_id, {"type": msg_type, **data})


async def process_job(
    job_id: str,
    language: str = "ru",
    custom_content_prompt: str | None = None,
    custom_strategy_prompt: str | None = None,
    profile_json: dict | None = None,
):
    """Main pipeline: URL -> download -> parallel processing -> analyze -> summarize + strategize."""

    async with get_db_session() as db:
        result = await db.get(Job, job_id)
        job = result
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        try:
            # Step 1: Scrape video + metadata via Apify
            await _update_job(
                db, job, JobStatus.DOWNLOADING, 0.05, "Скачиваем видео..."
            )

            # Start comment extraction in background (parallel with video scraping)
            comments_task = asyncio.create_task(scrape_comments(job.url))

            video_path, metadata = await scrape_video(job.url, job_id=job_id)

            # Check duration limit
            duration = metadata.get("duration", 0) or 0
            if duration > settings.max_video_duration_seconds:
                raise VideoTooLongError(
                    f"Video is {duration}s, max allowed is {settings.max_video_duration_seconds}s"
                )

            # Save metadata
            job.video_title = metadata.get("title")
            job.video_duration = metadata.get("duration")
            job.video_platform = metadata.get("platform")
            job.video_author = metadata.get("uploader")
            job.video_description = metadata.get("description")
            job.video_views = metadata.get("view_count")
            job.video_likes = metadata.get("like_count")
            job.video_comments = metadata.get("comment_count")

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

            # Steps 2-4: Pipeline — each frame is extracted, shown in UI, and analyzed
            # immediately; audio extraction and transcription run in parallel.
            frame_interval = max(2.0, duration / 20)
            scene_timestamps = []
            t = 0.0
            while t < duration:
                scene_timestamps.append(round(t, 2))
                t += frame_interval
            if not scene_timestamps:
                scene_timestamps = [0.0]

            total_frames = len(scene_timestamps)
            await _update_job(
                db,
                job,
                JobStatus.EXTRACTING_FRAMES,
                0.12,
                f"Раскадровка — {total_frames} кадров...",
            )

            # Audio extraction + transcription run in parallel with frame processing
            audio_task = asyncio.create_task(audio.extract_audio(video_path))

            async def _run_transcription():
                from app.services.transcriber import transcribe
                ap = await audio_task
                if ap is None:
                    logger.info("No audio stream — skipping transcription")
                    await _broadcast_data(job_id, "transcript", {"segments": []})
                    return []
                segs = await transcribe(ap)
                await _broadcast_data(job_id, "transcript", {
                    "segments": [s.model_dump() for s in segs],
                })
                return segs

            transcript_task = asyncio.create_task(_run_transcription())

            # Vision pipeline — each frame analyzed the moment it is extracted
            from app.core.openai_client import get_openai_client
            _client = get_openai_client()
            vision_semaphore = asyncio.Semaphore(settings.max_concurrent_vision_calls)
            _frame_tasks: list[asyncio.Task] = []
            _frame_results: list = []

            async def _analyze_and_broadcast(i: int, path, ts: float) -> None:
                async with vision_semaphore:
                    analysis = await _analyze_single_frame(_client, path, ts, i, None)
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

            # Extract frames — each triggers stub broadcast + immediate vision analysis.
            # max_concurrent=2 intentionally staggers extraction so frames appear
            # one by one (~1s apart) creating a dynamic cascade rather than a burst.
            await frame_extractor.extract_frames_pipelined(
                video_path, scene_timestamps, job.id, on_frame_ready,
                max_concurrent=2,
            )

            # Persist ANALYZING_FRAMES status to DB so reconnecting clients see the right state
            await _update_job(db, job, JobStatus.ANALYZING_FRAMES, 0.15, f"Анализируем {total_frames} кадров...")

            # Wait for all vision analysis tasks with:
            # - heartbeat so the user never sees a frozen progress bar
            # - overall timeout so we proceed with partial results if OpenAI hangs
            _VISION_TOTAL_TIMEOUT = 300  # 5 minutes max for all frames

            async def _heartbeat():
                """Send progress updates every 3s so the UI never looks frozen."""
                while True:
                    await asyncio.sleep(3)
                    done = len(_frame_results)
                    await progress_tracker.broadcast(job_id, {
                        "type": "progress",
                        "status": JobStatus.ANALYZING_FRAMES.value,
                        "progress": round(0.15 + (done / total_frames) * 0.55, 3),
                        "message": f"Анализируем кадр {done}/{total_frames}...",
                    })

            heartbeat_task = asyncio.create_task(_heartbeat())
            try:
                await asyncio.wait_for(
                    asyncio.gather(*_frame_tasks, return_exceptions=True),
                    timeout=_VISION_TOTAL_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Vision analysis timeout (%ds) for job %s — got %d/%d frames, proceeding",
                    _VISION_TOTAL_TIMEOUT, job_id, len(_frame_results), total_frames,
                )
                # Cancel remaining vision tasks
                for t in _frame_tasks:
                    if not t.done():
                        t.cancel()
                # Give cancelled tasks a moment to clean up
                await asyncio.gather(*_frame_tasks, return_exceptions=True)
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            if not _frame_results:
                raise Exception("All frame analyses failed or timed out")

            # Wait for transcript (likely already done by now)
            transcript_segments = await transcript_task

            # Sort frame results by timestamp for downstream use
            frame_analyses = sorted(_frame_results, key=lambda r: r.timestamp)

            # Step 5: Await comments (likely done by now) and run content + strategy in parallel
            await _update_job(
                db,
                job,
                JobStatus.GENERATING_SUMMARY,
                0.80,
                "Генерируем сценарий и стратегию...",
            )

            # Get comments (graceful — empty list if not available)
            try:
                comments = await comments_task
            except Exception:
                comments = []

            # Detect if original language matches target language
            full_transcript = " ".join(seg.text for seg in transcript_segments)
            same_language = detect_same_language(full_transcript, language)

            # Run content generation and strategy analysis in parallel
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

            # Heartbeat for generation stage — smooth progress 0.80 → 0.95
            _gen_start = asyncio.get_event_loop().time()
            _GEN_EXPECTED_DURATION = 30  # expected ~30s for generation

            async def _gen_heartbeat():
                while True:
                    await asyncio.sleep(3)
                    elapsed = asyncio.get_event_loop().time() - _gen_start
                    # Asymptotic progress: approaches 0.95 but never reaches it
                    ratio = min(elapsed / _GEN_EXPECTED_DURATION, 0.95)
                    progress = 0.80 + ratio * 0.15
                    await progress_tracker.broadcast(job_id, {
                        "type": "progress",
                        "status": JobStatus.GENERATING_SUMMARY.value,
                        "progress": round(progress, 3),
                        "message": "Генерируем сценарий и стратегию...",
                    })

            gen_heartbeat = asyncio.create_task(_gen_heartbeat())
            try:
                adaptation, strategy = await asyncio.gather(content_task, strategy_task)
            finally:
                gen_heartbeat.cancel()
                try:
                    await gen_heartbeat
                except asyncio.CancelledError:
                    pass

            # Broadcast content ready
            await _broadcast_data(job_id, "content_ready", {
                "summary": adaptation.model_dump(),
            })

            # Broadcast strategy ready
            await _broadcast_data(job_id, "strategy_ready", {
                "strategy": strategy.model_dump(),
            })

            # Step 6: Save results and publish to library
            transcript_dicts = [s.model_dump() for s in transcript_segments]
            frames_dicts = [f.model_dump() for f in frame_analyses]
            full_transcript_text = " ".join(seg.text for seg in transcript_segments)

            # Merge content + strategy into one adaptation_summary
            combined_summary = {
                **adaptation.model_dump(),
                **strategy.model_dump(),
            }

            # Use strategy's classification for library tags
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

                # Record interest signals for the user
                from app.services.interest_signals import record_signals
                all_topic_slugs = [s for s in set(all_tags) if s]
                if all_topic_slugs:
                    await record_signals(
                        db, user_id=job.user_id, topics=all_topic_slugs,
                        source="parse", weight=1.0, source_id=library_reel.id,
                    )
            else:
                # Update metrics if higher (use `is not None` — 0 is a valid count)
                if job.video_views is not None and (library_reel.video_views is None or library_reel.video_views < job.video_views):
                    library_reel.video_views = job.video_views
                if job.video_likes is not None and (library_reel.video_likes is None or library_reel.video_likes < job.video_likes):
                    library_reel.video_likes = job.video_likes
                if job.video_comments is not None and (library_reel.video_comments is None or library_reel.video_comments < job.video_comments):
                    library_reel.video_comments = job.video_comments
                if library_reel.cover_frame_index is None:
                    library_reel.cover_frame_index = strategy.cover.recommended_frame_index

            # Save results
            job.transcript = transcript_dicts
            job.frames = frames_dicts
            job.adaptation_summary = combined_summary
            job.library_reel_id = library_reel.id
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            job.progress_message = "Готово!"
            job.completed_at = datetime.utcnow()

            # Auto-create UserScript for the submitting user
            existing_user_script = await db.execute(
                select(UserScript).where(
                    UserScript.user_id == job.user_id,
                    UserScript.library_reel_id == library_reel.id,
                )
            )
            if not existing_user_script.scalar_one_or_none():
                user_script = UserScript(
                    user_id=job.user_id,
                    library_reel_id=library_reel.id,
                    script=adaptation.script,
                    description=adaptation.description,
                    editor_instructions=adaptation.editor_instructions,
                    original_script=adaptation.script,
                    original_description=adaptation.description,
                    original_editor_instructions=adaptation.editor_instructions,
                )
                db.add(user_script)

            # Propagate niche to linked ProfileReels
            reel_niche = tags_data.get("niche")
            if library_reel.id and reel_niche:
                linked_pr_result = await db.execute(
                    select(ProfileReel).where(
                        ProfileReel.library_reel_id == library_reel.id,
                        ProfileReel.niche.is_(None),
                    )
                )
                for pr in linked_pr_result.scalars().all():
                    pr.niche = reel_niche

            # Auto-track author profile for trend monitoring
            if metadata.get("uploader") and metadata.get("platform"):
                try:
                    from app.services.trend_monitor import ensure_tracked_profile

                    await ensure_tracked_profile(
                        db=db,
                        platform=metadata["platform"],
                        username=metadata["uploader"],
                        niche=tags_data.get("niche"),
                        display_name=metadata.get("uploader"),
                        topics=tags_data.get("topics", []),
                    )
                except Exception as track_err:
                    logger.warning(f"[trends] Failed to track profile: {track_err}")

            await db.commit()

            await progress_tracker.broadcast(
                job.id,
                {"type": "progress", "status": "completed", "progress": 1.0, "message": "Готово!"},
            )

        except Exception as e:
            comments_task.cancel()
            logger.exception(f"Job {job_id} failed: {e}")
            job.status = JobStatus.FAILED
            job.error = str(e)
            await db.commit()
            await progress_tracker.broadcast(
                job.id,
                {
                    "type": "progress",
                    "status": "failed",
                    "progress": job.progress,
                    "message": f"Error: {e}",
                    "error": True,
                },
            )
