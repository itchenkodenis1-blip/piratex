"""Background loops extracted from main.py for the scheduler service.

These loops must NOT run inside the web process — they would duplicate
across uvicorn workers. The scheduler runs as a separate Railway service
(piratex-scheduler) with a single instance.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from arq import ArqRedis
from sqlalchemy import and_, or_, select

from app.config import settings
from app.database import async_session
from app.models.job import Job, JobStatus
from app.models.user import UserSettings

logger = logging.getLogger(__name__)

MAX_JOB_RETRIES = 2


# ---------------------------------------------------------------------------
# Redis distributed lock helper (protects billing/engagement from duplication)
# ---------------------------------------------------------------------------

async def _acquire_redis_lock(redis: ArqRedis, name: str, ttl: int = 300) -> bool:
    """Try to acquire a distributed lock via Redis SET NX EX.

    Returns True if lock acquired, False if another instance holds it.
    """
    return bool(await redis.set(f"scheduler:lock:{name}", "1", ex=ttl, nx=True))


async def _release_redis_lock(redis: ArqRedis, name: str) -> None:
    await redis.delete(f"scheduler:lock:{name}")


# ---------------------------------------------------------------------------
# Job recovery (stuck jobs)
# ---------------------------------------------------------------------------

PENDING_STALE_MINUTES = 10  # PENDING jobs lost by arq — re-enqueue after this


async def do_recover_stuck_jobs(
    arq_pool: ArqRedis | None,
    stale_minutes: int = 60,
    source: str = "startup",
):
    """Find jobs stuck in intermediate states and recover or fail them.

    Stage-aware resume:
      PENDING (lost by arq) → re-enqueue task_scrape_and_download after 30 min
      GENERATING_SUMMARY    → re-enqueue task_generate_content (data already in DB)
      Earlier stages        → re-enqueue task_scrape_and_download (need to re-download)
    """
    skip_statuses = [JobStatus.COMPLETED, JobStatus.FAILED]
    stale_cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
    pending_cutoff = datetime.utcnow() - timedelta(minutes=PENDING_STALE_MINUTES)

    jobs_to_retry: dict[str, str] = {}

    async with async_session() as db:
        result = await db.execute(
            select(Job).where(
                Job.status.notin_(skip_statuses),
                or_(
                    # Active jobs stuck in intermediate states
                    and_(Job.status != JobStatus.PENDING, Job.updated_at < stale_cutoff),
                    # PENDING jobs lost by arq (never picked up)
                    and_(Job.status == JobStatus.PENDING, Job.updated_at < pending_cutoff),
                ),
            )
        )
        stuck_jobs = result.scalars().all()

        if not stuck_jobs:
            return

        logger.info(f"[{source}] Found {len(stuck_jobs)} stuck job(s)")

        for job in stuck_jobs:
            retry_count = job.retry_count or 0
            original_status = job.status.value
            is_lost_pending = job.status == JobStatus.PENDING

            if retry_count >= MAX_JOB_RETRIES:
                job.status = JobStatus.FAILED
                if is_lost_pending:
                    job.error = f"Задача потеряна очередью после {retry_count + 1} попыток"
                else:
                    job.error = f"Не удалось обработать после {retry_count + 1} попыток (последний статус: {original_status})"
                logger.info(f"[{source}] Job {job.id} marked FAILED after {retry_count + 1} attempts")
            else:
                jobs_to_retry[job.id] = original_status
                job.status = JobStatus.PENDING
                job.progress = 0.0
                job.progress_message = None
                job.error = None
                job.retry_count = retry_count + 1
                reason = "lost by arq queue" if is_lost_pending else f"stuck at {original_status}"
                logger.info(
                    f"[{source}] Re-queuing job {job.id} (attempt {retry_count + 2}, {reason})"
                )

        await db.commit()

    if not jobs_to_retry:
        return

    async with async_session() as db:
        result = await db.execute(
            select(Job).where(Job.id.in_(list(jobs_to_retry.keys())))
        )
        to_retry = result.scalars().all()

        for job in to_retry:
            settings_result = await db.execute(
                select(UserSettings).where(UserSettings.user_id == job.user_id)
            )
            user_settings = settings_result.scalar_one_or_none()

            language = (user_settings.language if user_settings and user_settings.language else "ru")
            custom_content_prompt = user_settings.custom_content_prompt if user_settings else None
            custom_strategy_prompt = user_settings.custom_strategy_prompt if user_settings else None
            profile_json = user_settings.profile_json if user_settings else None

            original_status = jobs_to_retry.get(job.id, "")

            if original_status == "generating_summary" and job.transcript and job.frames:
                task_name = "task_generate_content"
                task_args = (job.id, language, custom_content_prompt, custom_strategy_prompt, profile_json, [])
                logger.info(f"[{source}] Resuming job {job.id} from content generation (skipping scrape+analyze)")
            else:
                task_name = "task_scrape_and_download"
                task_args = (job.id, job.url, language, custom_content_prompt, custom_strategy_prompt, profile_json)

            if arq_pool:
                await arq_pool.enqueue_job(task_name, *task_args)
            else:
                logger.error(f"[{source}] Cannot retry job {job.id} — arq pool unavailable")
                continue
            logger.info(f"[{source}] Launched retry for job {job.id} → {task_name}")


# ---------------------------------------------------------------------------
# Profile parsing recovery (stuck deep-analyze runs)
# ---------------------------------------------------------------------------

_PARSING_STALE_MINUTES = 15  # Mark "running" parsings as failed after 15 min

async def do_recover_stuck_parsings(source: str = "watchdog"):
    """Find profile_parsings stuck in 'running' state and mark them failed.

    This catches cases where:
    - HTTP request was cancelled (CancelledError)
    - Server restarted mid-analysis
    - Unhandled exception left status as 'running'
    """
    from app.models.user import ProfileParsing

    cutoff = datetime.utcnow() - timedelta(minutes=_PARSING_STALE_MINUTES)
    async with async_session() as session:
        result = await session.execute(
            select(ProfileParsing).where(
                and_(
                    ProfileParsing.status == "running",
                    ProfileParsing.created_at < cutoff,
                )
            )
        )
        stuck = result.scalars().all()
        if not stuck:
            return

        for parsing in stuck:
            parsing.status = "failed"
            parsing.error = f"Timed out — stuck in 'running' for >{_PARSING_STALE_MINUTES} min (recovered by {source})"
            logger.warning(
                "[%s] Recovered stuck profile parsing %s (user=%s, username=%s, created=%s)",
                source, parsing.id, parsing.user_id, parsing.username, parsing.created_at,
            )

        await session.commit()
        logger.info("[%s] Recovered %d stuck profile parsings", source, len(stuck))


# ---------------------------------------------------------------------------
# Individual loops
# ---------------------------------------------------------------------------

async def watchdog_loop(arq_pool: ArqRedis | None):
    """Periodically recover jobs stuck in intermediate states (every 2 min)."""
    await asyncio.sleep(120)

    while True:
        try:
            await do_recover_stuck_jobs(arq_pool, stale_minutes=5, source="watchdog")
            await do_recover_stuck_parsings(source="watchdog")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[watchdog] Loop error: %s", e, exc_info=True)
        await asyncio.sleep(120)


async def trends_check_loop(arq_pool: ArqRedis | None = None):
    """Check tracked profiles for trending reels (every 30 min).

    Uses Redis lock to prevent duplication if multiple scheduler instances exist.
    """
    await asyncio.sleep(120)

    while True:
        try:
            if arq_pool and not await _acquire_redis_lock(arq_pool, "trends_check", ttl=6000):
                logger.debug("[trends] Another instance holds lock, skipping")
                await asyncio.sleep(1800)
                continue

            try:
                async with async_session() as db:
                    from app.services.trend_monitor import check_stale_profiles, backfill_thumbnails

                    await check_stale_profiles(db, redis=arq_pool)
                    await backfill_thumbnails(db)
                # Mark successful cycle for health monitoring
                if arq_pool:
                    try:
                        await arq_pool.set("trend:last_cycle_completed", str(int(datetime.utcnow().timestamp())))
                    except Exception:
                        pass
            finally:
                if arq_pool:
                    await _release_redis_lock(arq_pool, "trends_check")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[trends] Check loop error: {e}", exc_info=True)
        await asyncio.sleep(1800)


async def apify_balance_check_loop():
    """Check Apify account balance and manage circuit breaker."""
    await asyncio.sleep(30)

    while True:
        try:
            from app.services.scraper._apify_client import _update_balance_circuit_breaker

            await _update_balance_circuit_breaker()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[apify-budget] Balance check loop error: %s", e)
        await asyncio.sleep(settings.apify_balance_check_interval)


async def billing_loop(redis: ArqRedis | None):
    """Process recurring payments, expiry, and reminders (every hour).

    Uses Redis lock to prevent duplication if multiple scheduler instances exist.
    """
    await asyncio.sleep(180)

    while True:
        try:
            if redis and not await _acquire_redis_lock(redis, "billing", ttl=3500):
                logger.debug("[billing] Another instance holds the lock, skipping")
                await asyncio.sleep(3600)
                continue

            try:
                async with async_session() as db:
                    from app.workers.billing_tasks import (
                        cleanup_abandoned_payments,
                        expire_admin_subscriptions,
                        expire_cancelled_subscriptions,
                        handle_past_due_subscriptions,
                        mark_stale_cp_subscriptions,
                        process_recurring_payments,
                        send_dunning_reminders,
                        send_renewal_reminders,
                    )

                    await process_recurring_payments(db)
                    await mark_stale_cp_subscriptions(db)
                    await handle_past_due_subscriptions(db)
                    await expire_cancelled_subscriptions(db)
                    await expire_admin_subscriptions(db)
                    await send_renewal_reminders(db)
                    await send_dunning_reminders(db)
                    await cleanup_abandoned_payments(db)
            finally:
                if redis:
                    await _release_redis_lock(redis, "billing")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[billing] Loop error: {e}", exc_info=True)
        await asyncio.sleep(3600)


async def metrics_digest_loop():
    """Send daily metrics digest to admin Telegram IDs at ~09:00 UTC."""
    await asyncio.sleep(300)

    while True:
        try:
            now = datetime.utcnow()
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(wait_seconds)

            async with async_session() as db:
                from app.services.metrics import send_daily_digest

                await send_daily_digest(db)
                logger.info("[metrics] Daily digest sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[metrics] Digest loop error: {e}", exc_info=True)
            await asyncio.sleep(3600)


async def hourly_stats_loop():
    """Send hourly mini-summary to admin Telegram IDs."""
    await asyncio.sleep(600)

    while True:
        try:
            async with async_session() as db:
                from app.services.metrics import send_hourly_stats

                await send_hourly_stats(db)
                logger.info("[metrics] Hourly stats sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[metrics] Hourly stats error: {e}", exc_info=True)
        await asyncio.sleep(3600)


async def daily_summary_loop():
    """Send end-of-day summary at 00:00 MSK (21:00 UTC)."""
    await asyncio.sleep(300)

    while True:
        try:
            now = datetime.utcnow()
            # Target 21:00 UTC = 00:00 MSK
            target = now.replace(hour=21, minute=0, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(wait_seconds)

            async with async_session() as db:
                from app.services.metrics import send_daily_summary

                await send_daily_summary(db)
                logger.info("[metrics] Daily summary (midnight MSK) sent")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[metrics] Daily summary error: {e}", exc_info=True)
            await asyncio.sleep(3600)


async def morning_briefing_loop(redis: ArqRedis | None):
    """Send personalized morning briefs at ~09:00 UTC daily.

    Uses Redis lock to prevent duplication.
    """
    await asyncio.sleep(600)

    while True:
        try:
            now = datetime.utcnow()
            if 9 <= now.hour < 10:
                if redis and not await _acquire_redis_lock(redis, "morning_brief", ttl=3500):
                    logger.debug("[morning_brief] Another instance holds lock, skipping")
                    await asyncio.sleep(3600)
                    continue

                try:
                    async with async_session() as db:
                        from app.services.morning_brief import send_morning_briefs

                        sent = await send_morning_briefs(db)
                        logger.info("[morning_brief] Sent %d briefs", sent)
                finally:
                    if redis:
                        await _release_redis_lock(redis, "morning_brief")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[morning_brief] Loop error: %s", e, exc_info=True)

        await asyncio.sleep(3600)


async def engagement_loop(redis: ArqRedis | None):
    """Weekly digest, monthly reports, daily re-engagement checks.

    Uses Redis lock to prevent duplication.
    """
    await asyncio.sleep(600)

    while True:
        try:
            if redis and not await _acquire_redis_lock(redis, "engagement", ttl=3500):
                logger.debug("[engagement] Another instance holds the lock, skipping")
                await asyncio.sleep(3600)
                continue

            try:
                now = datetime.utcnow()

                if now.weekday() == 0 and 10 <= now.hour < 11:
                    async with async_session() as db:
                        from app.services.engagement import send_weekly_digest

                        sent = await send_weekly_digest(db)
                        logger.info("[engagement] Weekly digest: %d sent", sent)

                if now.day == 1 and 10 <= now.hour < 11:
                    async with async_session() as db:
                        from app.services.engagement import send_monthly_reports

                        sent = await send_monthly_reports(db)
                        logger.info("[engagement] Monthly reports: %d sent", sent)

                if 11 <= now.hour < 12:
                    async with async_session() as db:
                        from app.services.engagement import send_reengagement_messages

                        sent = await send_reengagement_messages(db)
                        logger.info("[engagement] Re-engagement: %d sent", sent)

                # Onboarding drips: check 24h/48h nudges (every hour)
                try:
                    async with async_session() as db:
                        from app.services.onboarding_drip import check_scheduled_drips

                        drip_sent = await check_scheduled_drips(db)
                        if drip_sent:
                            logger.info("[engagement] Onboarding drips: %d sent", drip_sent)
                except Exception as drip_err:
                    logger.error("[engagement] Onboarding drip error: %s", drip_err)
            finally:
                if redis:
                    await _release_redis_lock(redis, "engagement")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[engagement] Loop error: {e}", exc_info=True)

        await asyncio.sleep(3600)


async def radar_loop(arq_pool: ArqRedis | None = None):
    """Content Radar: notify users about trending reels (every 10 min).

    Daily digest at 08:00 UTC.
    """
    await asyncio.sleep(300)
    last_digest_date = None

    while True:
        try:
            async with async_session() as db:
                from app.services.radar import send_radar_notifications

                sent = await send_radar_notifications(db, redis=arq_pool)
                if sent:
                    logger.info("[radar] Tick: %d notifications sent", sent)

            now = datetime.utcnow()
            if now.hour == 8 and (last_digest_date is None or last_digest_date != now.date()):
                async with async_session() as db:
                    from app.services.radar import send_radar_daily_digest

                    digest_sent = await send_radar_daily_digest(db)
                    logger.info("[radar] Daily digest: %d sent", digest_sent)
                    last_digest_date = now.date()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[radar] Loop error: %s", e, exc_info=True)

        await asyncio.sleep(600)


# ---------------------------------------------------------------------------
# Queue health monitoring
# ---------------------------------------------------------------------------

async def queue_health_loop(arq_pool: ArqRedis | None):
    """Monitor queue depth and alert admins if overloaded (every 5 min)."""
    await asyncio.sleep(300)
    QUEUE_ALERT_THRESHOLD = 50

    while True:
        try:
            if arq_pool:
                queued = await arq_pool.zcard(b"arq:queue")
                in_progress = await arq_pool.scard(b"arq:in-progress")

                if queued > QUEUE_ALERT_THRESHOLD:
                    logger.warning("[health] Queue overloaded: %d queued, %d in-progress", queued, in_progress)
                    # Send Telegram alert to admins
                    try:
                        admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
                        if admin_ids and settings.telegram_bot_token:
                            from app.services.telegram import send_telegram_message
                            text = (
                                f"⚠️ Queue overload: {queued} queued, {in_progress} in-progress.\n"
                                f"Consider scaling workers."
                            )
                            for tid in admin_ids[:3]:
                                await send_telegram_message(tid, settings.telegram_bot_token, text)
                    except Exception:
                        pass
                else:
                    logger.debug("[health] Queue OK: %d queued, %d in-progress", queued, in_progress)

                # Check trend watching loop health
                try:
                    last_cycle_ts = await arq_pool.get("trend:last_cycle_completed")
                    if last_cycle_ts:
                        age_min = (datetime.utcnow().timestamp() - float(last_cycle_ts)) / 60
                        if age_min > 90:  # 3 missed cycles (30 min each)
                            logger.warning("[health] Trend watching stale: last cycle %.0f min ago", age_min)
                            admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
                            if admin_ids and settings.telegram_bot_token:
                                from app.services.telegram import send_telegram_message
                                text = f"⚠️ Trend watching: последний цикл завершён {int(age_min)} мин назад. Возможно, loop завис."
                                for tid in admin_ids[:3]:
                                    await send_telegram_message(tid, settings.telegram_bot_token, text)
                except Exception:
                    pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[health] Queue health check error: %s", e)

        await asyncio.sleep(300)


# ---------------------------------------------------------------------------
# Main entry: start all loops
# ---------------------------------------------------------------------------

async def run_all_loops():
    """Start all background loops. Called by run_scheduler.py."""
    from arq.connections import RedisSettings, create_pool

    logger.info("[scheduler] Starting all background loops...")

    # Ensure critical columns exist (same as main.py startup migrations)
    try:
        from sqlalchemy import text
        from app.database import engine
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS paid_amount_kopecks BIGINT"))
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS scheduled_tier VARCHAR(20)"))
            await conn.execute(text("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS scheduled_interval VARCHAR(10)"))
        logger.info("[scheduler] Schema check completed")
    except Exception as e:
        logger.error("[scheduler] Schema check failed: %s", e)

    # Create own arq pool for job recovery
    arq_pool: ArqRedis | None = None
    try:
        arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        logger.info("[scheduler] arq Redis pool created")
    except Exception as e:
        logger.error("[scheduler] Failed to create arq Redis pool: %s", e)

    # One-shot startup recovery
    try:
        await do_recover_stuck_jobs(arq_pool, stale_minutes=5, source="startup")
    except Exception as e:
        logger.error(f"[scheduler] Startup recovery error: {e}")
    try:
        await do_recover_stuck_parsings(source="startup")
    except Exception as e:
        logger.error(f"[scheduler] Startup parsing recovery error: {e}")

    # Launch all loops
    tasks = [
        asyncio.create_task(watchdog_loop(arq_pool)),
        asyncio.create_task(trends_check_loop(arq_pool)),
        asyncio.create_task(apify_balance_check_loop()),
        asyncio.create_task(billing_loop(arq_pool)),
        asyncio.create_task(metrics_digest_loop()),
        asyncio.create_task(daily_summary_loop()),
        asyncio.create_task(morning_briefing_loop(arq_pool)),
        asyncio.create_task(engagement_loop(arq_pool)),
        asyncio.create_task(radar_loop(arq_pool)),
        asyncio.create_task(queue_health_loop(arq_pool)),
    ]

    logger.info("[scheduler] All %d loops started", len(tasks))

    # Wait forever (until SIGTERM)
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("[scheduler] Shutting down...")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if arq_pool:
            await arq_pool.close()
