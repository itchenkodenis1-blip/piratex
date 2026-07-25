import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy import Date, case, cast, delete, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TIER_LIMITS, settings
from app.core.auth import get_admin_user
from app.core.chat import chat_tracker
from app.database import get_db
from app.services import demo_data
from app.models.job import Job, JobStatus
from app.models.library import LibraryReel, UserScript
from app.models.message import TelegramMessage
from app.models.subscription import Payment, Subscription
from app.models.tier_config import TierConfig
from app.models.user import User, UserSettings
from app.schemas.admin import (
    AdminAnalyticsResponse,
    AdminConversationItem,
    AdminConversationListResponse,
    AdminJobItem,
    AdminJobListResponse,
    AdminJobStatsResponse,
    AdminLibraryItem,
    AdminLibraryListResponse,
    AdminMessageItem,
    AdminPaymentItem,
    AdminPaymentListResponse,
    AdminSendMessageRequest,
    AdminStatsResponse,
    AdminTrackedProfileItem,
    AdminTrackedProfileListResponse,
    AdminHiddenReelItem,
    AdminHiddenReelListResponse,
    BlockProfileRequest,
    HideReelRequest,
    AdminUserDetail,
    AdminUserItem,
    AdminUserListResponse,
    AdminUserPayment,
    AdminUserScript,
    AdminUserSettings,
    AdminUserSubscription,
    JobDayStats,
    PlatformHealth,
    RecentError,
    TierConfigItem,
    TierConfigUpdateRequest,
    UpdateTierRequest,
    UserDayStats,
    ShowcaseActiveJob,
    ShowcaseDayStats,
    ShowcaseHeatmapCell,
    ShowcasePlatformStat,
    ShowcaseStatsResponse,
    AdminParsingItem,
    AdminParsingListResponse,
    AdminParsingStatsResponse,
    AdminNicheItem,
    AdminNicheCreateRequest,
    AdminNicheUpdateRequest,
    AdminNichesResponse,
    AdminNicheStatsResponse,
    AdminNicheGroup,
    AdminTrendingReelItem,
    AdminTrendingReelsResponse,
    AdminTrendingNicheStat,
    AdminTrendingSummary,
    CostAnalyticsResponse,
    CostDayStats,
    CostPeriod,
)
from app.models.feedback import ScriptRating, SupportConversation, SupportMessage
from app.schemas.feedback import (
    AdminRatingDetail,
    AdminRatingItem,
    AdminRatingListResponse,
    OtherRatingItem,
    OtherScriptItem,
)
from app.schemas.support import (
    AdminSendMessageRequest as AdminSupportSendRequest,
    AdminSupportConversationItem,
    AdminSupportConversationListResponse,
    MessageItem as SupportMessageItem,
    UnreadCountResponse,
)
from app.services.telegram import send_telegram_message

router = APIRouter()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    tier: str = Query("", description="Filter by tier"),
    is_anonymous: bool | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    jobs_count_sq = (
        select(Job.user_id, func.count(Job.id).label("cnt"))
        .group_by(Job.user_id)
        .subquery()
    )

    query = (
        select(User, func.coalesce(jobs_count_sq.c.cnt, 0).label("jobs_count"))
        .outerjoin(jobs_count_sq, User.id == jobs_count_sq.c.user_id)
    )
    count_query = select(func.count(User.id))

    if tier:
        query = query.where(User.tier == tier)
        count_query = count_query.where(User.tier == tier)
    if is_anonymous is not None:
        query = query.where(User.is_anonymous == is_anonymous)
        count_query = count_query.where(User.is_anonymous == is_anonymous)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(query)).all()

    items = [
        AdminUserItem(
            id=row.User.id,
            email=row.User.email,
            name=row.User.name,
            is_anonymous=row.User.is_anonymous,
            tier=row.User.tier,
            telegram_username=row.User.telegram_username,
            telegram_subscribed=row.User.telegram_subscribed,
            created_at=row.User.created_at,
            jobs_count=row.jobs_count,
        )
        for row in rows
    ]
    return AdminUserListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user_detail(
    user_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # 1. User + jobs count
    jobs_count_sq = (
        select(Job.user_id, func.count(Job.id).label("cnt"))
        .group_by(Job.user_id)
        .subquery()
    )
    row = (await db.execute(
        select(User, func.coalesce(jobs_count_sq.c.cnt, 0).label("jobs_count"))
        .outerjoin(jobs_count_sq, User.id == jobs_count_sq.c.user_id)
        .where(User.id == user_id)
    )).one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    target, jobs_count = row.User, row.jobs_count

    # 2. Jobs (paginated)
    offset = (page - 1) * per_page
    recent_jobs_rows = (await db.execute(
        select(Job)
        .where(Job.user_id == user_id)
        .order_by(Job.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )).scalars().all()

    recent_jobs = [
        AdminJobItem(
            id=j.id,
            user_id=j.user_id,
            user_email=target.email,
            user_name=target.name,
            user_tier=target.tier,
            url=j.url,
            status=j.status.value if hasattr(j.status, "value") else str(j.status),
            progress=j.progress or 0.0,
            error=j.error,
            video_title=j.video_title,
            video_platform=j.video_platform,
            share_token=j.share_token,
            created_at=j.created_at,
            completed_at=j.completed_at,
        )
        for j in recent_jobs_rows
    ]

    # 3. Settings + profile
    user_settings_row = (await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )).scalar_one_or_none()

    admin_settings = None
    if user_settings_row:
        profile = user_settings_row.profile_json or {}
        admin_settings = AdminUserSettings(
            language=user_settings_row.language or "ru",
            onboarding_completed=user_settings_row.onboarding_completed or False,
            has_custom_content_prompt=bool(user_settings_row.custom_content_prompt),
            has_custom_strategy_prompt=bool(user_settings_row.custom_strategy_prompt),
            has_api_keys=bool(user_settings_row.openai_api_key or user_settings_row.anthropic_api_key),
            about_me=profile.get("about_me"),
            tone=profile.get("tone"),
            niches=profile.get("niches") or [],
            interests=profile.get("interests") or [],
            forbidden_words=profile.get("forbidden_words"),
            script_cta=profile.get("script_cta"),
            description_cta=profile.get("description_cta"),
            video_format=profile.get("video_format"),
            radar_enabled=profile.get("radar_enabled"),
            radar_mode=profile.get("radar_mode"),
        )

    # 4. Scripts with reel info (limited to 50, with total count)
    scripts_total = (await db.execute(
        select(func.count(UserScript.id)).where(UserScript.user_id == user_id)
    )).scalar_one()

    scripts_rows = (await db.execute(
        select(UserScript, LibraryReel.url, LibraryReel.video_title, LibraryReel.video_platform)
        .outerjoin(LibraryReel, UserScript.library_reel_id == LibraryReel.id)
        .where(UserScript.user_id == user_id)
        .order_by(UserScript.created_at.desc())
        .limit(50)
    )).all()

    scripts = [
        AdminUserScript(
            id=s.UserScript.id,
            script=s.UserScript.script,
            description=s.UserScript.description,
            editor_instructions=s.UserScript.editor_instructions,
            original_script=s.UserScript.original_script,
            original_description=s.UserScript.original_description,
            original_editor_instructions=s.UserScript.original_editor_instructions,
            active_hook_index=s.UserScript.active_hook_index or 0,
            reel_url=s.url,
            reel_title=s.video_title,
            reel_platform=s.video_platform,
            created_at=s.UserScript.created_at,
            updated_at=s.UserScript.updated_at,
        )
        for s in scripts_rows
    ]

    # 5. Active subscription (handle NULL current_period_end for indefinite subs)
    sub_row = (await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status.in_(["active", "cancelled"]),
            or_(
                Subscription.current_period_end > datetime.utcnow(),
                Subscription.current_period_end.is_(None),
            ),
        )
    )).scalar_one_or_none()

    admin_sub = None
    if sub_row:
        admin_sub = AdminUserSubscription(
            id=sub_row.id,
            tier=sub_row.tier,
            status=sub_row.status,
            payment_provider=sub_row.payment_provider,
            billing_interval=sub_row.billing_interval,
            amount_kopecks=sub_row.amount_kopecks or 0,
            currency=sub_row.currency or "RUB",
            current_period_start=sub_row.current_period_start,
            current_period_end=sub_row.current_period_end,
            scheduled_tier=sub_row.scheduled_tier,
            scheduled_interval=sub_row.scheduled_interval,
            created_at=sub_row.created_at,
        )

    # 6. Recent payments (last 10, with total count)
    payments_total = (await db.execute(
        select(func.count(Payment.id)).where(Payment.user_id == user_id)
    )).scalar_one()

    payments_rows = (await db.execute(
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(10)
    )).scalars().all()

    payments = [
        AdminUserPayment(
            id=p.id,
            amount_kopecks=p.amount_kopecks,
            currency=p.currency,
            status=p.status,
            payment_provider=p.payment_provider,
            payment_method=p.payment_method,
            paid_at=p.paid_at,
            created_at=p.created_at,
        )
        for p in payments_rows
    ]

    return AdminUserDetail(
        id=target.id,
        email=target.email,
        name=target.name,
        is_anonymous=target.is_anonymous,
        tier=target.tier,
        auth_provider=getattr(target, "auth_provider", None),
        telegram_username=target.telegram_username,
        telegram_subscribed=target.telegram_subscribed,
        created_at=target.created_at,
        jobs_count=jobs_count,
        jobs_total=jobs_count,
        recent_jobs=recent_jobs,
        settings=admin_settings,
        scripts=scripts,
        scripts_total=scripts_total,
        subscription=admin_sub,
        payments=payments,
        payments_total=payments_total,
    )


PAID_TIERS = {"START", "PRO", "UNLIMITED"}


@router.patch("/users/{user_id}/tier")
async def update_user_tier(
    user_id: str,
    payload: UpdateTierRequest,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    valid_tiers = (await db.execute(select(TierConfig.name))).scalars().all()
    if not valid_tiers:
        valid_tiers = list(TIER_LIMITS.keys())
    if payload.tier not in valid_tiers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier. Must be one of: {', '.join(valid_tiers)}",
        )

    if payload.duration_months is not None and payload.duration_months not in (1, 3, 6, 12):
        raise HTTPException(status_code=400, detail="duration_months must be 1, 3, 6, or 12")

    result = await db.execute(
        select(User).where(User.id == user_id).with_for_update()
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    subscription_id = None
    period_end = None

    if payload.tier in PAID_TIERS:
        # Check for existing paid (non-admin) subscription
        paid_sub = (await db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status.in_(["active", "past_due", "cancelled"]),
                Subscription.payment_provider != "admin",
                Subscription.current_period_end > now,
            )
        )).scalar_one_or_none()
        if paid_sub:
            raise HTTPException(
                status_code=409,
                detail=f"User has active {paid_sub.payment_provider} subscription "
                       f"for {paid_sub.tier} (status: {paid_sub.status}). Cancel it first.",
            )

        # Expire existing admin subscription
        existing_admin = (await db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.payment_provider == "admin",
            )
        )).scalar_one_or_none()
        if existing_admin:
            existing_admin.status = "expired"

        # Calculate period_end
        if payload.duration_months is not None:
            period_end = now + timedelta(days=payload.duration_months * 30)
            billing_interval = "yearly" if payload.duration_months >= 12 else "monthly"
        else:
            period_end = datetime(2099, 12, 31)
            billing_interval = "monthly"

        # Create Subscription
        import uuid
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tier=payload.tier,
            status="active",
            payment_provider="admin",
            amount_kopecks=0,
            paid_amount_kopecks=0,
            currency="RUB",
            billing_interval=billing_interval,
            current_period_start=now,
            current_period_end=period_end,
        )
        db.add(sub)
        await db.flush()

        # Create Payment record
        payment = Payment(
            id=str(uuid.uuid4()),
            subscription_id=sub.id,
            user_id=user_id,
            payment_provider="admin",
            amount_kopecks=0,
            currency="RUB",
            status="succeeded",
            description=f"Назначено администратором: {payload.reason}" if payload.reason else "Назначено администратором",
            paid_at=now,
        )
        db.add(payment)
        subscription_id = sub.id
    else:
        # Downgrade to free tier — expire admin subscription if exists
        existing_admin = (await db.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status == "active",
                Subscription.payment_provider == "admin",
            )
        )).scalar_one_or_none()
        if existing_admin:
            existing_admin.status = "expired"

    target.tier = payload.tier
    from app.services.trend_monitor import enforce_author_limits
    await enforce_author_limits(db, target.id, payload.tier)
    await db.commit()
    await db.refresh(target)
    return {
        "id": target.id,
        "email": target.email,
        "tier": target.tier,
        "subscription_id": subscription_id,
        "period_end": period_end.isoformat() if period_end else None,
    }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    result = await db.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")

    # Clean up storage files for all user's jobs before cascade delete
    from app.services.storage_cleanup import cleanup_job_storage
    job_ids = (await db.execute(select(Job.id).where(Job.user_id == user_id))).scalars().all()
    for jid in job_ids:
        await cleanup_job_storage(jid)

    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

@router.get("/jobs", response_model=AdminJobListResponse)
async def list_jobs(
    status: str = Query("", description="Filter: running | completed | failed | pending"),
    platform: str = Query("", description="Filter by video_platform"),
    source: str = Query("", description="Filter by source: web | telegram | radar"),
    date_range: str = Query("", description="Filter: today | week | month"),
    q: str = Query("", description="Search in URL or user email/name"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Job, User.email.label("user_email"), User.name.label("user_name"), User.tier.label("user_tier"))
        .outerjoin(User, Job.user_id == User.id)
    )
    count_query = select(func.count(Job.id))

    if status == "running":
        running_filter = Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PENDING])
        query = query.where(running_filter)
        count_query = count_query.where(running_filter)
    elif status == "pending":
        query = query.where(Job.status == JobStatus.PENDING)
        count_query = count_query.where(Job.status == JobStatus.PENDING)
    elif status == "completed":
        query = query.where(Job.status == JobStatus.COMPLETED)
        count_query = count_query.where(Job.status == JobStatus.COMPLETED)
    elif status == "failed":
        query = query.where(Job.status == JobStatus.FAILED)
        count_query = count_query.where(Job.status == JobStatus.FAILED)

    if platform:
        query = query.where(Job.video_platform == platform)
        count_query = count_query.where(Job.video_platform == platform)

    if source:
        query = query.where(Job.source == source)
        count_query = count_query.where(Job.source == source)

    if date_range:
        now = datetime.utcnow()
        if date_range == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "week":
            start = now - timedelta(days=7)
        elif date_range == "month":
            start = now - timedelta(days=30)
        else:
            start = None
        if start:
            query = query.where(Job.created_at >= start)
            count_query = count_query.where(Job.created_at >= start)

    if q:
        like = f"%{q}%"
        search_filter = or_(
            Job.url.ilike(like),
            User.email.ilike(like),
            User.name.ilike(like),
        )
        query = query.where(search_filter)
        count_query = count_query.join(User, Job.user_id == User.id, isouter=True).where(search_filter)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Job.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(query)).all()

    items = []
    for row in rows:
        job = row.Job
        duration = None
        if job.completed_at and job.created_at:
            duration = (job.completed_at - job.created_at).total_seconds()
        items.append(AdminJobItem(
            id=job.id,
            user_id=job.user_id,
            user_email=row.user_email,
            user_name=row.user_name,
            user_tier=row.user_tier,
            url=job.url,
            status=job.status.value if hasattr(job.status, "value") else str(job.status),
            progress=job.progress or 0.0,
            progress_message=job.progress_message,
            error=job.error,
            video_title=job.video_title,
            video_platform=job.video_platform,
            share_token=job.share_token,
            source=job.source,
            retry_count=job.retry_count or 0,
            duration_seconds=duration,
            created_at=job.created_at,
            completed_at=job.completed_at,
        ))

    # Demo mode: mask real user PII behind stable synthetic identities so a live
    # demo never leaks real emails (and the job feed looks like many customers).
    if await demo_data.is_demo_mode():
        for it in items:
            ident = demo_data.demo_identity(it.user_id or it.id)
            it.user_email = ident["user_email"]
            it.user_name = ident["user_name"]

    return AdminJobListResponse(items=items, total=total, page=page, per_page=per_page)


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Job not found")

    from app.services.storage_cleanup import cleanup_job_storage
    await cleanup_job_storage(job_id)

    await db.execute(delete(Job).where(Job.id == job_id))
    await db.commit()
    return {"deleted": True}


@router.get("/jobs/stats", response_model=AdminJobStatsResponse)
async def job_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Aggregated job statistics for the admin dashboard."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(hours=24)

    # DB counts
    completed_today = await db.scalar(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= today_start,
        )
    ) or 0
    failed_today = await db.scalar(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.FAILED,
            Job.created_at >= today_start,
        )
    ) or 0
    completed_total = await db.scalar(
        select(func.count(Job.id)).where(Job.status == JobStatus.COMPLETED)
    ) or 0
    failed_total = await db.scalar(
        select(func.count(Job.id)).where(Job.status == JobStatus.FAILED)
    ) or 0
    completed_week = await db.scalar(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= week_ago,
        )
    ) or 0

    # Running count from DB (not in COMPLETED/FAILED/PENDING)
    running_db = await db.scalar(
        select(func.count(Job.id)).where(
            Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.PENDING])
        )
    ) or 0

    # Average duration (last 24h completed jobs)
    avg_dur = await db.scalar(
        select(func.avg(
            extract("epoch", Job.completed_at) - extract("epoch", Job.created_at)
        )).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= day_ago,
            Job.completed_at.isnot(None),
        )
    )

    # Error rate (last 24h)
    total_24h = await db.scalar(
        select(func.count(Job.id)).where(Job.created_at >= day_ago)
    ) or 0
    failed_24h = await db.scalar(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.FAILED,
            Job.created_at >= day_ago,
        )
    ) or 0
    error_rate = round((failed_24h / total_24h * 100), 1) if total_24h > 0 else 0.0

    # Queue stats from Redis
    queued = 0
    managed = getattr(request.app.state, "managed_arq_pool", None)
    arq_pool = await managed.get_pool() if managed else getattr(request.app.state, "arq_pool", None)
    if arq_pool:
        try:
            queued = await arq_pool.zcard(b"arq:queue")
        except Exception:
            pass

    return AdminJobStatsResponse(
        queued=queued,
        running=running_db,
        completed_today=completed_today,
        failed_today=failed_today,
        completed_total=completed_total,
        failed_total=failed_total,
        avg_duration_seconds=round(avg_dur, 1) if avg_dur else None,
        error_rate_pct=error_rate,
        completed_week=completed_week,
    )


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Retry a failed job — reset to PENDING and re-enqueue."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

    # Determine which task to re-enqueue
    has_transcript = bool(job.transcript)
    has_frames = bool(job.frames)

    job.status = JobStatus.PENDING
    job.error = None
    job.progress = 0.0
    job.progress_message = None
    job.retry_count = (job.retry_count or 0) + 1
    job.completed_at = None
    await db.commit()
    await db.refresh(job)

    # Enqueue to arq
    managed = getattr(request.app.state, "managed_arq_pool", None)
    arq_pool = await managed.get_pool() if managed else getattr(request.app.state, "arq_pool", None)
    if arq_pool:
        try:
            if has_transcript and has_frames:
                await arq_pool.enqueue_job(
                    "task_generate_content",
                    job_id=job.id,
                    language=None,
                )
            else:
                await arq_pool.enqueue_job(
                    "task_scrape_and_download",
                    job_id=job.id,
                    url=job.url,
                    language=None,
                )
        except Exception:
            logger.exception("[admin/retry] Failed to enqueue job %s", job_id)

    return {"retried": True, "job_id": job.id}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Cancel a running or pending job."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        raise HTTPException(status_code=400, detail="Job is already finished")

    job.status = JobStatus.FAILED
    job.error = "Отменено администратором"
    job.completed_at = datetime.utcnow()
    await db.commit()

    return {"cancelled": True, "job_id": job.id}


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@router.get("/payments", response_model=AdminPaymentListResponse)
async def list_payments(
    status: str = Query("", description="Filter: pending | succeeded | cancelled | refunded"),
    provider: str = Query("", description="Filter: yookassa | cloudpayments | stripe"),
    q: str = Query("", description="Search by user email"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Demo mode: serve a synthetic, in-memory payment stream (no DB rows).
    if await demo_data.is_demo_mode():
        d = demo_data.payments_page(
            datetime.utcnow(), status=status, provider=provider, q=q,
            page=page, per_page=per_page,
        )
        return AdminPaymentListResponse(
            items=[AdminPaymentItem(**p) for p in d["items"]],
            total=d["total"],
            page=page,
            per_page=per_page,
            total_all=d["total_all"],
            total_succeeded=d["total_succeeded"],
            total_rub_kopecks=d["total_rub_kopecks"],
            total_eur_cents=d["total_eur_cents"],
        )

    query = (
        select(Payment, User.email.label("user_email"), User.name.label("user_name"))
        .outerjoin(User, Payment.user_id == User.id)
    )
    count_query = select(func.count(Payment.id))

    if status:
        query = query.where(Payment.status == status)
        count_query = count_query.where(Payment.status == status)

    if provider:
        query = query.where(Payment.payment_provider == provider)
        count_query = count_query.where(Payment.payment_provider == provider)

    if q:
        like = f"%{q}%"
        email_filter = User.email.ilike(like)
        query = query.where(email_filter)
        count_query = count_query.join(User, Payment.user_id == User.id).where(email_filter)

    total = (await db.execute(count_query)).scalar() or 0

    # Total count without status filter (for conversion calculation)
    total_all_query = select(func.count(Payment.id))
    if provider:
        total_all_query = total_all_query.where(Payment.payment_provider == provider)
    if q:
        total_all_query = total_all_query.join(User, Payment.user_id == User.id).where(User.email.ilike(f"%{q}%"))
    total_all = (await db.execute(total_all_query)).scalar() or 0

    # Aggregate stats for succeeded payments, split by currency
    stats_query = select(
        func.count(Payment.id).label("cnt"),
        func.coalesce(func.sum(case(
            (Payment.currency == "RUB", Payment.amount_kopecks),
            else_=0,
        )), 0).label("total_rub"),
        func.coalesce(func.sum(case(
            (Payment.currency == "EUR", Payment.amount_kopecks),
            else_=0,
        )), 0).label("total_eur"),
    ).where(Payment.status == "succeeded")
    if provider:
        stats_query = stats_query.where(Payment.payment_provider == provider)
    if q:
        stats_query = stats_query.join(User, Payment.user_id == User.id).where(User.email.ilike(f"%{q}%"))
    stats_row = (await db.execute(stats_query)).one()

    query = query.order_by(Payment.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(query)).all()

    items = [
        AdminPaymentItem(
            id=row.Payment.id,
            user_id=row.Payment.user_id,
            user_email=row.user_email,
            user_name=row.user_name,
            subscription_id=row.Payment.subscription_id,
            provider_payment_id=row.Payment.provider_payment_id,
            payment_provider=row.Payment.payment_provider,
            amount_kopecks=row.Payment.amount_kopecks,
            currency=row.Payment.currency,
            status=row.Payment.status,
            payment_method=row.Payment.payment_method,
            description=row.Payment.description,
            receipt_url=row.Payment.receipt_url,
            paid_at=row.Payment.paid_at,
            created_at=row.Payment.created_at,
        )
        for row in rows
    ]
    return AdminPaymentListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_all=total_all,
        total_succeeded=int(stats_row.cnt),
        total_rub_kopecks=int(stats_row.total_rub),
        total_eur_cents=int(stats_row.total_eur),
    )


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

@router.get("/library", response_model=AdminLibraryListResponse)
async def list_library(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(LibraryReel.id)))).scalar() or 0
    rows = (await db.execute(
        select(LibraryReel, User.email.label("submitted_by_email"))
        .outerjoin(User, LibraryReel.submitted_by == User.id)
        .order_by(LibraryReel.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )).all()

    items = [
        AdminLibraryItem(
            id=row.LibraryReel.id,
            url=row.LibraryReel.url,
            video_title=row.LibraryReel.video_title,
            video_platform=row.LibraryReel.video_platform,
            video_author=row.LibraryReel.video_author,
            submitted_by_email=row.submitted_by_email,
            created_at=row.LibraryReel.created_at,
        )
        for row in rows
    ]
    return AdminLibraryListResponse(items=items, total=total, page=page, per_page=per_page)


@router.delete("/library/{reel_id}")
async def delete_library_item(
    reel_id: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LibraryReel).where(LibraryReel.id == reel_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Library item not found")

    await db.execute(delete(LibraryReel).where(LibraryReel.id == reel_id))
    await db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Ratings (Script Quality Feedback)
# ---------------------------------------------------------------------------


@router.get("/ratings", response_model=AdminRatingListResponse)
async def list_ratings(
    rating: int | None = Query(None, ge=1, le=5, description="Filter by rating value"),
    has_comment: bool | None = Query(None, description="Filter: only with comments"),
    date_from: str | None = Query(None, description="Date from (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="Date to (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all script ratings with user and job info."""
    query = (
        select(
            ScriptRating,
            User.email.label("user_email"),
            User.name.label("user_name"),
            User.telegram_username.label("user_telegram"),
            Job.url.label("job_url"),
            Job.video_title.label("video_title"),
            Job.library_reel_id.label("library_reel_id"),
        )
        .join(User, ScriptRating.user_id == User.id)
        .join(Job, ScriptRating.job_id == Job.id)
    )

    if rating is not None:
        query = query.where(ScriptRating.rating == rating)
    if has_comment is True:
        query = query.where(ScriptRating.comment.isnot(None), ScriptRating.comment != "")
    if date_from:
        query = query.where(ScriptRating.created_at >= date_from)
    if date_to:
        query = query.where(ScriptRating.created_at <= date_to + " 23:59:59")

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(ScriptRating.created_at.desc())
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = [
        AdminRatingItem(
            id=row.ScriptRating.id,
            rating=row.ScriptRating.rating,
            comment=row.ScriptRating.comment,
            created_at=row.ScriptRating.created_at,
            viewed_at=row.ScriptRating.viewed_at,
            user_id=row.ScriptRating.user_id,
            user_email=row.user_email,
            user_name=row.user_name,
            user_telegram=row.user_telegram,
            job_id=row.ScriptRating.job_id,
            job_url=row.job_url,
            video_title=row.video_title,
            library_reel_id=row.library_reel_id,
        )
        for row in rows
    ]

    return AdminRatingListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/ratings/unread-count")
async def get_unread_ratings_count(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Count of ratings not yet viewed by admin."""
    count = (await db.execute(
        select(func.count(ScriptRating.id)).where(ScriptRating.viewed_at.is_(None))
    )).scalar() or 0
    return {"count": count}


@router.get("/ratings/{rating_id}", response_model=AdminRatingDetail)
async def get_rating_detail(
    rating_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Deep detail for a single rating — for investigating bad ratings."""
    from app.models.user import UserSettings

    # 1. Load rating + user + job in one query
    row = (
        await db.execute(
            select(ScriptRating, User, Job)
            .join(User, ScriptRating.user_id == User.id)
            .join(Job, ScriptRating.job_id == Job.id)
            .where(ScriptRating.id == rating_id)
        )
    ).first()
    if not row:
        raise HTTPException(404, "Rating not found")

    sr: ScriptRating = row[0]
    user: User = row[1]
    job: Job = row[2]

    # Mark as viewed by admin
    if sr.viewed_at is None:
        sr.viewed_at = datetime.utcnow()
        await db.commit()
        await db.refresh(sr)

    # 2. User profile/presets
    settings_row = (
        await db.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
    ).scalar_one_or_none()
    user_profile = None
    if settings_row and settings_row.profile_json:
        p = settings_row.profile_json
        user_profile = {
            k: p.get(k)
            for k in (
                "about_me", "tone", "niches", "forbidden_words",
                "script_cta", "description_cta", "video_format",
                "content_prompt_additions",
            )
            if p.get(k)
        }

    # 3. Library reel context
    reel_first_parsed_at = None
    reel_submitted_by_email = None
    total_jobs = 0
    total_scripts = 0

    if job.library_reel_id:
        reel = (
            await db.execute(
                select(LibraryReel).where(LibraryReel.id == job.library_reel_id)
            )
        ).scalar_one_or_none()
        if reel:
            reel_first_parsed_at = reel.created_at
            # Who first submitted it
            submitter = (
                await db.execute(
                    select(User.email).where(User.id == reel.submitted_by)
                )
            ).scalar_one_or_none()
            reel_submitted_by_email = submitter

        # Count jobs for this reel
        total_jobs = (
            await db.execute(
                select(func.count())
                .select_from(Job)
                .where(Job.library_reel_id == job.library_reel_id)
            )
        ).scalar() or 0

        # Count scripts for this reel
        total_scripts = (
            await db.execute(
                select(func.count())
                .select_from(UserScript)
                .where(UserScript.library_reel_id == job.library_reel_id)
            )
        ).scalar() or 0

    # 4. Other ratings for same reel (excluding current user)
    other_ratings: list[OtherRatingItem] = []
    if job.library_reel_id:
        other_r_rows = (
            await db.execute(
                select(ScriptRating, User.email, User.name)
                .join(User, ScriptRating.user_id == User.id)
                .join(Job, ScriptRating.job_id == Job.id)
                .where(
                    Job.library_reel_id == job.library_reel_id,
                    ScriptRating.user_id != user.id,
                )
                .order_by(ScriptRating.created_at.desc())
                .limit(20)
            )
        ).all()
        other_ratings = [
            OtherRatingItem(
                user_email=r[1],
                user_name=r[2],
                rating=r[0].rating,
                comment=r[0].comment,
                created_at=r[0].created_at,
            )
            for r in other_r_rows
        ]

    # 5. Other scripts for same reel (excluding current user)
    other_scripts: list[OtherScriptItem] = []
    if job.library_reel_id:
        other_s_rows = (
            await db.execute(
                select(UserScript, User.email, User.name)
                .join(User, UserScript.user_id == User.id)
                .where(
                    UserScript.library_reel_id == job.library_reel_id,
                    UserScript.user_id != user.id,
                )
                .order_by(UserScript.created_at.desc())
                .limit(20)
            )
        ).all()
        other_scripts = [
            OtherScriptItem(
                user_email=r[1],
                user_name=r[2],
                script_preview=r[0].script[:300] if r[0].script else "",
                created_at=r[0].created_at,
            )
            for r in other_s_rows
        ]

    # 6. Processing time
    processing_seconds = None
    if job.completed_at and job.created_at:
        processing_seconds = (job.completed_at - job.created_at).total_seconds()

    return AdminRatingDetail(
        id=sr.id,
        rating=sr.rating,
        comment=sr.comment,
        created_at=sr.created_at,
        user_id=user.id,
        user_email=user.email,
        user_name=user.name,
        user_telegram=user.telegram_username,
        user_tier=user.tier,
        user_registered_at=user.created_at,
        user_profile=user_profile or None,
        job_id=job.id,
        job_url=job.url,
        video_title=job.video_title,
        video_platform=job.video_platform,
        video_author=job.video_author,
        video_duration=job.video_duration,
        video_views=job.video_views,
        video_likes=job.video_likes,
        video_comments=job.video_comments,
        job_created_at=job.created_at,
        job_completed_at=job.completed_at,
        processing_seconds=processing_seconds,
        adaptation_summary=job.adaptation_summary,
        library_reel_id=job.library_reel_id,
        reel_first_parsed_at=reel_first_parsed_at,
        reel_submitted_by_email=reel_submitted_by_email,
        total_jobs_for_reel=total_jobs,
        total_scripts_for_reel=total_scripts,
        other_ratings=other_ratings,
        other_scripts=other_scripts,
    )


# ---------------------------------------------------------------------------
# Support Conversations (In-App Messenger)
# ---------------------------------------------------------------------------


@router.get("/support/conversations", response_model=AdminSupportConversationListResponse)
async def list_support_conversations(
    status: str = Query("", description="Filter by status: open, resolved"),
    q: str = Query("", description="Search by email or name"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all support conversations with user info and last message preview."""
    query = (
        select(SupportConversation, User)
        .join(User, SupportConversation.user_id == User.id)
    )

    if status:
        query = query.where(SupportConversation.status == status)
    if q:
        query = query.where(
            or_(
                User.email.ilike(f"%{q}%"),
                User.name.ilike(f"%{q}%"),
                User.telegram_username.ilike(f"%{q}%"),
            )
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = query.order_by(
        (SupportConversation.unread_admin > 0).desc(),
        SupportConversation.updated_at.desc(),
    )
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    # Fetch last message for each conversation (single query, no N+1)
    conv_ids = [row.SupportConversation.id for row in rows]
    last_messages: dict[str, tuple[str | None, datetime | None]] = {}
    if conv_ids:
        from sqlalchemy import text as raw_text
        # DISTINCT ON is PostgreSQL-specific; fallback to subquery for SQLite compat
        latest_sub = (
            select(
                SupportMessage.conversation_id,
                SupportMessage.text,
                SupportMessage.created_at,
                func.row_number().over(
                    partition_by=SupportMessage.conversation_id,
                    order_by=SupportMessage.created_at.desc(),
                ).label("rn"),
            )
            .where(SupportMessage.conversation_id.in_(conv_ids))
            .subquery()
        )
        latest_result = await db.execute(
            select(latest_sub.c.conversation_id, latest_sub.c.text, latest_sub.c.created_at)
            .where(latest_sub.c.rn == 1)
        )
        for cid, txt, created in latest_result:
            last_messages[cid] = (txt, created)

    items = [
        AdminSupportConversationItem(
            id=row.SupportConversation.id,
            user_id=row.User.id,
            user_email=row.User.email,
            user_name=row.User.name,
            user_telegram=row.User.telegram_username,
            status=row.SupportConversation.status,
            unread_admin=row.SupportConversation.unread_admin or 0,
            last_message_text=last_messages.get(row.SupportConversation.id, (None, None))[0],
            last_message_at=last_messages.get(row.SupportConversation.id, (None, None))[1],
            created_at=row.SupportConversation.created_at,
        )
        for row in rows
    ]

    return AdminSupportConversationListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/support/conversations/{conversation_id}", response_model=list[SupportMessageItem])
async def get_support_messages(
    conversation_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a support conversation."""
    conv_result = await db.execute(
        select(SupportConversation).where(SupportConversation.id == conversation_id)
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(SupportMessage)
        .where(SupportMessage.conversation_id == conversation_id)
        .order_by(SupportMessage.created_at.asc())
    )
    messages = result.scalars().all()

    # Mark user messages as read
    from datetime import datetime as dt
    unread = [m for m in messages if m.sender_type == "user" and m.read_at is None]
    if unread:
        for m in unread:
            m.read_at = dt.utcnow()
        conversation.unread_admin = 0
        await db.commit()

    return [
        SupportMessageItem(
            id=m.id,
            sender_type=m.sender_type,
            sender_id=m.sender_id,
            text=m.text,
            image_key=m.image_key,
            read_at=m.read_at,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/support/conversations/{conversation_id}/messages", response_model=SupportMessageItem)
async def admin_send_support_message(
    conversation_id: str,
    body: AdminSupportSendRequest,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin sends a reply in a support conversation."""
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="admin",
        sender_id=admin.id,
        text=body.text,
    )
    db.add(msg)
    conv.unread_user = (conv.unread_user or 0) + 1
    from datetime import datetime as dt
    conv.updated_at = dt.utcnow()
    await db.commit()
    await db.refresh(msg)

    message_item = SupportMessageItem(
        id=msg.id,
        sender_type=msg.sender_type,
        sender_id=msg.sender_id,
        text=msg.text,
        image_key=msg.image_key,
        read_at=msg.read_at,
        created_at=msg.created_at,
    )

    # Push to user's WebSocket (fire-and-forget)
    try:
        await chat_tracker.send_to_user(conv.user_id, {
            "type": "new_message",
            "message": message_item.model_dump(mode="json"),
        })
    except Exception as e:
        logger.warning("Failed to push support message via WebSocket: %s", e)

    # Schedule deferred notification (Telegram/Email) if unread after 2 min
    try:
        from app.core.arq_pool import managed_arq_pool
        pool = await managed_arq_pool.get_pool()
        if pool:
            await pool.enqueue_job(
                "task_notify_support_reply",
                str(msg.id), str(conv.user_id),
                _defer_by=timedelta(seconds=120),
            )
    except Exception as e:
        logger.warning("Failed to enqueue support notification: %s", e)

    return message_item


@router.post("/support/conversations/{conversation_id}/resolve")
async def resolve_support_conversation(
    conversation_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a support conversation as resolved."""
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.status = "resolved"
    await db.commit()
    return {"ok": True, "status": "resolved"}


@router.post("/support/conversations/{conversation_id}/block-user")
async def block_support_user(
    conversation_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Block a user from sending support messages."""
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_result = await db.execute(select(User).where(User.id == conv.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.support_blocked = True
    conv.status = "resolved"
    await db.commit()
    return {"ok": True, "blocked": True}


@router.post("/support/conversations/{conversation_id}/unblock-user")
async def unblock_support_user(
    conversation_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Unblock a user from sending support messages."""
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_result = await db.execute(select(User).where(User.id == conv.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.support_blocked = False
    await db.commit()
    return {"ok": True, "blocked": False}


@router.get("/support/unread-count", response_model=UnreadCountResponse)
async def admin_support_unread_count(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Total unread messages across all support conversations."""
    result = await db.execute(
        select(func.coalesce(func.sum(SupportConversation.unread_admin), 0))
    )
    total = result.scalar() or 0
    return UnreadCountResponse(count=total)


# ---------------------------------------------------------------------------
# Tiers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Messages / Conversations
# ---------------------------------------------------------------------------

@router.get("/messages/conversations", response_model=AdminConversationListResponse)
async def list_conversations(
    q: str = Query("", description="Search by username or name"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    # Subquery: latest message per telegram_user_id
    latest_msg_sq = (
        select(
            TelegramMessage.telegram_user_id,
            func.max(TelegramMessage.id).label("last_msg_id"),
            func.count(TelegramMessage.id).label("cnt"),
            func.max(TelegramMessage.created_at).label("last_at"),
        )
        .group_by(TelegramMessage.telegram_user_id)
        .subquery()
    )

    query = (
        select(
            latest_msg_sq.c.telegram_user_id,
            latest_msg_sq.c.cnt.label("message_count"),
            latest_msg_sq.c.last_at.label("last_message_at"),
            TelegramMessage.text.label("last_message_text"),
            TelegramMessage.telegram_username,
            TelegramMessage.telegram_name,
            TelegramMessage.user_id,
        )
        .join(TelegramMessage, TelegramMessage.id == latest_msg_sq.c.last_msg_id)
    )
    count_query = select(func.count()).select_from(latest_msg_sq)

    if q:
        like = f"%{q}%"
        query = query.where(
            TelegramMessage.telegram_username.ilike(like)
            | TelegramMessage.telegram_name.ilike(like)
        )
        # For count with search, use a different approach
        count_query = (
            select(func.count(func.distinct(TelegramMessage.telegram_user_id)))
            .where(
                TelegramMessage.telegram_username.ilike(like)
                | TelegramMessage.telegram_name.ilike(like)
            )
        )

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(latest_msg_sq.c.last_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(query)).all()

    items = [
        AdminConversationItem(
            telegram_user_id=row.telegram_user_id,
            telegram_username=row.telegram_username,
            telegram_name=row.telegram_name,
            user_id=row.user_id,
            message_count=row.message_count,
            last_message_text=row.last_message_text,
            last_message_at=row.last_message_at,
        )
        for row in rows
    ]
    return AdminConversationListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/messages/{telegram_user_id}", response_model=list[AdminMessageItem])
async def get_conversation(
    telegram_user_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(TelegramMessage)
        .where(TelegramMessage.telegram_user_id == telegram_user_id)
        .order_by(TelegramMessage.created_at.asc())
    )).scalars().all()

    return [
        AdminMessageItem(
            id=m.id,
            telegram_user_id=m.telegram_user_id,
            direction=m.direction,
            text=m.text,
            created_at=m.created_at,
        )
        for m in rows
    ]


@router.post("/messages/{telegram_user_id}/send", response_model=AdminMessageItem)
async def admin_send_message(
    telegram_user_id: str,
    body: AdminSendMessageRequest,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to a Telegram user from admin panel."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text is empty")

    sent = await send_telegram_message(
        telegram_user_id,
        settings.telegram_bot_token,
        text,
    )
    if not sent:
        raise HTTPException(status_code=502, detail="Failed to send via Telegram")

    # Log outgoing message
    msg = TelegramMessage(
        telegram_user_id=telegram_user_id,
        direction="out",
        text=text,
    )
    # Copy username/name from latest message in this conversation
    latest = (await db.execute(
        select(TelegramMessage)
        .where(TelegramMessage.telegram_user_id == telegram_user_id)
        .order_by(TelegramMessage.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if latest:
        msg.telegram_username = latest.telegram_username
        msg.telegram_name = latest.telegram_name
        msg.user_id = latest.user_id

    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return AdminMessageItem(
        id=msg.id,
        telegram_user_id=msg.telegram_user_id,
        direction=msg.direction,
        text=msg.text,
        created_at=msg.created_at,
    )


# ---------------------------------------------------------------------------
# Tiers
# ---------------------------------------------------------------------------

TIER_ORDER = ["ANONYMOUS", "REGISTERED", "FREE", "START", "PRO", "UNLIMITED"]


@router.get("/tiers", response_model=list[TierConfigItem])
async def list_tiers(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(TierConfig))).scalars().all()
    by_name = {r.name: r for r in rows}
    return [
        TierConfigItem.model_validate(by_name[n])
        for n in TIER_ORDER
        if n in by_name
    ]


@router.put("/tiers/{name}", response_model=TierConfigItem)
async def update_tier(
    name: str,
    payload: TierConfigUpdateRequest,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TierConfig).where(TierConfig.name == name))
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")

    tier.max_monthly = payload.max_monthly
    tier.max_total = payload.max_total
    tier.max_refines_daily = payload.max_refines_daily
    tier.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tier)
    return TierConfigItem.model_validate(tier)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        user_counts = (await db.execute(
            select(
                func.count(User.id).label("total"),
                func.count(case((User.is_anonymous == True, 1))).label("anonymous"),  # noqa: E712
                func.count(case((User.tier == "REGISTERED", 1))).label("registered"),
                func.count(case((User.tier == "FREE", 1))).label("free"),
                func.count(case((User.tier == "START", 1))).label("start"),
                func.count(case((User.tier == "PRO", 1))).label("pro"),
                func.count(case((User.tier == "UNLIMITED", 1))).label("unlimited"),
            )
        )).one()

        job_counts = (await db.execute(
            select(
                func.count(Job.id).label("total"),
                func.count(case((Job.created_at >= today_start, 1))).label("today"),
                func.count(case((
                    Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]), 1
                ))).label("running"),
                func.count(case((Job.status == JobStatus.COMPLETED, 1))).label("completed"),
                func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
                func.count(case((
                    (Job.status == JobStatus.FAILED) & (Job.created_at >= today_start), 1
                ))).label("failed_today"),
            )
        )).one()

        library_count = (await db.execute(select(func.count(LibraryReel.id)))).scalar() or 0

        # Demo mode: replace the user funnel with the synthetic roster so tier
        # counts reconcile with the revenue shown elsewhere. Operational job /
        # library numbers stay real.
        if await demo_data.is_demo_mode():
            f = demo_data.funnel(now)
            total_users = f["total_users"]
            anonymous_users = f["anonymous"]
            registered_users = f["registered_tier"]
            free_users = f["free"]
            start_users = f["start_users"]
            pro_users = f["pro_users"]
            unlimited_users = f["unlimited_users"]
        else:
            total_users = user_counts.total
            anonymous_users = user_counts.anonymous
            registered_users = user_counts.registered
            free_users = user_counts.free
            start_users = user_counts.start
            pro_users = user_counts.pro
            unlimited_users = user_counts.unlimited

        return AdminStatsResponse(
            total_users=total_users,
            anonymous_users=anonymous_users,
            registered_users=registered_users,
            free_users=free_users,
            start_users=start_users,
            pro_users=pro_users,
            unlimited_users=unlimited_users,
            total_jobs=job_counts.total,
            jobs_today=job_counts.today,
            jobs_running=job_counts.running,
            jobs_completed=job_counts.completed,
            jobs_failed=job_counts.failed,
            jobs_failed_today=job_counts.failed_today,
            library_reels=library_count,
        )
    except Exception as e:
        logger.exception("[admin/stats] error")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get("/analytics", response_model=AdminAnalyticsResponse)
async def get_analytics(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        cutoff = datetime.utcnow() - timedelta(days=14)
        today = datetime.utcnow().date()

        # 1. Jobs per day
        jobs_daily = (await db.execute(
            select(
                cast(Job.created_at, Date).label("day"),
                func.count(Job.id).label("total"),
                func.count(case((Job.status == JobStatus.COMPLETED, 1))).label("completed"),
                func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
            )
            .where(Job.created_at >= cutoff)
            .group_by(cast(Job.created_at, Date))
            .order_by(cast(Job.created_at, Date))
        )).all()

        day_map = {row.day: row for row in jobs_daily}
        jobs_per_day = []
        for i in range(13, -1, -1):
            d = today - timedelta(days=i)
            row = day_map.get(d)
            jobs_per_day.append(JobDayStats(
                date=d.isoformat(),
                total=row.total if row else 0,
                completed=row.completed if row else 0,
                failed=row.failed if row else 0,
            ))

        # 2. Users per day
        users_daily = (await db.execute(
            select(
                cast(User.created_at, Date).label("day"),
                func.count(User.id).label("cnt"),
            )
            .where(User.created_at >= cutoff)
            .where(User.is_anonymous == False)  # noqa: E712
            .group_by(cast(User.created_at, Date))
            .order_by(cast(User.created_at, Date))
        )).all()

        user_day_map = {row.day: row.cnt for row in users_daily}
        users_per_day = []
        for i in range(13, -1, -1):
            d = today - timedelta(days=i)
            users_per_day.append(UserDayStats(
                date=d.isoformat(),
                new_users=user_day_map.get(d, 0),
            ))

        # 3. Platform health
        platform_rows = (await db.execute(
            select(
                Job.video_platform,
                func.count(Job.id).label("total_jobs"),
                func.count(case((Job.status == JobStatus.COMPLETED, 1))).label("completed"),
                func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
            )
            .where(Job.created_at >= cutoff)
            .where(Job.video_platform.isnot(None))
            .group_by(Job.video_platform)
        )).all()

        platform_map = {row.video_platform: row for row in platform_rows}
        platform_health = []
        for p in ["instagram", "youtube", "tiktok"]:
            row = platform_map.get(p)
            total = row.total_jobs if row else 0
            completed = row.completed if row else 0
            failed = row.failed if row else 0
            platform_health.append(PlatformHealth(
                platform=p,
                total_jobs=total,
                completed=completed,
                failed=failed,
                success_rate=round(completed / total * 100, 1) if total > 0 else 0.0,
            ))

        # 4. Recent errors
        error_rows = (await db.execute(
            select(Job.url, Job.video_platform, Job.error, Job.share_token, Job.created_at)
            .where(Job.status == JobStatus.FAILED)
            .order_by(Job.created_at.desc())
            .limit(10)
        )).all()

        recent_errors = [
            RecentError(
                url=row.url,
                platform=row.video_platform,
                error=row.error,
                share_token=row.share_token,
                created_at=row.created_at,
            )
            for row in error_rows
        ]

        return AdminAnalyticsResponse(
            jobs_per_day=jobs_per_day,
            users_per_day=users_per_day,
            platform_health=platform_health,
            recent_errors=recent_errors,
        )
    except Exception as e:
        logger.exception("[admin/analytics] error")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Cost Analytics
# ---------------------------------------------------------------------------


def _aggregate_costs(rows) -> CostPeriod:
    """Aggregate cost_breakdown JSON from multiple jobs into a CostPeriod."""
    result = CostPeriod()
    for row in rows:
        cb = row.cost_breakdown
        if not cb or not isinstance(cb, dict):
            continue
        result.apify_usd += cb.get("apify_usd", 0.0)
        result.whisper_usd += cb.get("whisper_usd", 0.0)
        result.vision_usd += cb.get("vision_usd", 0.0)
        result.sonnet_usd += cb.get("sonnet_usd", 0.0)
        result.haiku_usd += cb.get("haiku_usd", 0.0)
        result.total_usd += cb.get("total_usd", 0.0)
        result.jobs_count += 1
    # Round
    result.apify_usd = round(result.apify_usd, 4)
    result.whisper_usd = round(result.whisper_usd, 4)
    result.vision_usd = round(result.vision_usd, 4)
    result.sonnet_usd = round(result.sonnet_usd, 4)
    result.haiku_usd = round(result.haiku_usd, 4)
    result.total_usd = round(result.total_usd, 4)
    return result


@router.get("/cost-analytics", response_model=CostAnalyticsResponse)
async def get_cost_analytics(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Cost analytics for the business dashboard."""
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cutoff_14d = now - timedelta(days=14)

        # Fetch jobs with cost data for different periods
        all_jobs_with_cost = (await db.execute(
            select(Job.cost_breakdown, Job.completed_at)
            .where(Job.cost_breakdown.isnot(None))
            .where(Job.status == JobStatus.COMPLETED)
        )).all()

        today_jobs = [j for j in all_jobs_with_cost if j.completed_at and j.completed_at >= today_start]
        yesterday_jobs = [j for j in all_jobs_with_cost if j.completed_at and yesterday_start <= j.completed_at < today_start]
        month_jobs = [j for j in all_jobs_with_cost if j.completed_at and j.completed_at >= month_start]

        today_costs = _aggregate_costs(today_jobs)
        yesterday_costs = _aggregate_costs(yesterday_jobs)
        month_costs = _aggregate_costs(month_jobs)
        all_time_costs = _aggregate_costs(all_jobs_with_cost)

        # Average cost per reel
        avg_per_reel = round(all_time_costs.total_usd / all_time_costs.jobs_count, 4) if all_time_costs.jobs_count > 0 else 0.0

        # Daily costs (14 days)
        daily_costs = []
        for i in range(13, -1, -1):
            d = (now - timedelta(days=i)).date()
            day_start = datetime(d.year, d.month, d.day)
            day_end = day_start + timedelta(days=1)
            day_jobs = [j for j in all_jobs_with_cost if j.completed_at and day_start <= j.completed_at < day_end]
            day_total = sum((j.cost_breakdown or {}).get("total_usd", 0.0) for j in day_jobs)
            daily_costs.append(CostDayStats(
                date=d.isoformat(),
                total_usd=round(day_total, 4),
                jobs_count=len(day_jobs),
            ))

        # Apify budget (prefer Redis cache, fallback to live with 5s timeout)
        apify_budget = None
        try:
            import json as _json
            from app.core.redis_pool import get_redis
            _r = await get_redis()
            if _r:
                cached = await _r.get("apify:balance:cached")
                if cached:
                    apify_budget = _json.loads(cached)
            if not apify_budget:
                from app.services.scraper._apify_client import check_apify_balance
                apify_budget = await asyncio.wait_for(check_apify_balance(), timeout=5)
        except Exception:
            pass

        # Revenue
        revenue_today_rub = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount_kopecks), 0))
            .where(Payment.status == "succeeded", Payment.currency == "RUB", Payment.paid_at >= today_start)
        )).scalar() or 0

        revenue_yesterday_rub = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount_kopecks), 0))
            .where(Payment.status == "succeeded", Payment.currency == "RUB",
                   Payment.paid_at >= yesterday_start, Payment.paid_at < today_start)
        )).scalar() or 0

        revenue_month_rub = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount_kopecks), 0))
            .where(Payment.status == "succeeded", Payment.currency == "RUB", Payment.paid_at >= month_start)
        )).scalar() or 0

        revenue_today_eur = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount_kopecks), 0))
            .where(Payment.status == "succeeded", Payment.currency == "EUR", Payment.paid_at >= today_start)
        )).scalar() or 0

        revenue_month_eur = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount_kopecks), 0))
            .where(Payment.status == "succeeded", Payment.currency == "EUR", Payment.paid_at >= month_start)
        )).scalar() or 0

        # MRR from active subscriptions
        mrr_rub = (await db.execute(
            select(func.coalesce(func.sum(Subscription.amount_kopecks), 0))
            .where(Subscription.status == "active", Subscription.currency == "RUB",
                   Subscription.billing_interval == "monthly")
        )).scalar() or 0
        # Add yearly converted to monthly
        mrr_yearly_rub = (await db.execute(
            select(func.coalesce(func.sum(Subscription.amount_kopecks / 12), 0))
            .where(Subscription.status == "active", Subscription.currency == "RUB",
                   Subscription.billing_interval == "yearly")
        )).scalar() or 0
        mrr_rub = int(mrr_rub + mrr_yearly_rub)

        mrr_eur = (await db.execute(
            select(func.coalesce(func.sum(Subscription.amount_kopecks), 0))
            .where(Subscription.status == "active", Subscription.currency == "EUR",
                   Subscription.billing_interval == "monthly")
        )).scalar() or 0
        mrr_yearly_eur = (await db.execute(
            select(func.coalesce(func.sum(Subscription.amount_kopecks / 12), 0))
            .where(Subscription.status == "active", Subscription.currency == "EUR",
                   Subscription.billing_interval == "yearly")
        )).scalar() or 0
        mrr_eur = int(mrr_eur + mrr_yearly_eur)

        # Paid users count
        paid_users = (await db.execute(
            select(func.count(User.id))
            .where(User.tier.in_(["START", "PRO", "UNLIMITED"]))
        )).scalar() or 0

        # Demo mode: overlay synthetic revenue/MRR/paid-users. Real costs are
        # kept as-is so the cost→revenue margin reads authentically.
        if await demo_data.is_demo_mode():
            dr = demo_data.cost_revenue(now)
            revenue_today_rub = dr["revenue_today_rub"]
            revenue_yesterday_rub = dr["revenue_yesterday_rub"]
            revenue_month_rub = dr["revenue_month_rub"]
            revenue_today_eur = dr["revenue_today_eur"]
            revenue_month_eur = dr["revenue_month_eur"]
            mrr_rub = dr["mrr_rub"]
            mrr_eur = dr["mrr_eur"]
            paid_users = dr["paid_users"]

        cost_per_paid_user = round(month_costs.total_usd / paid_users, 4) if paid_users > 0 else 0.0

        return CostAnalyticsResponse(
            today=today_costs,
            yesterday=yesterday_costs,
            month=month_costs,
            all_time=all_time_costs,
            avg_per_reel_usd=avg_per_reel,
            apify_budget=apify_budget,
            revenue_today_rub=revenue_today_rub,
            revenue_yesterday_rub=revenue_yesterday_rub,
            revenue_month_rub=revenue_month_rub,
            revenue_today_eur=revenue_today_eur,
            revenue_month_eur=revenue_month_eur,
            mrr_rub=mrr_rub,
            mrr_eur=mrr_eur,
            daily_costs=daily_costs,
            paid_users=paid_users,
            cost_per_paid_user_usd=cost_per_paid_user,
        )
    except Exception:
        logger.exception("[admin/cost-analytics] error")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

async def cleanup_ghost_users(db: AsyncSession) -> int:
    cutoff = datetime.utcnow() - timedelta(days=30)

    users_with_jobs = select(func.distinct(Job.user_id))
    users_with_reels = select(func.distinct(LibraryReel.submitted_by))

    stmt = (
        delete(User)
        .where(User.is_anonymous == True)  # noqa: E712
        .where(User.created_at < cutoff)
        .where(User.id.notin_(users_with_jobs))
        .where(User.id.notin_(users_with_reels))
    )

    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount


@router.post("/cleanup-ghosts")
async def cleanup_ghosts(
    _user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    count = await cleanup_ghost_users(db)
    return {"deleted": count}


@router.post("/gc-storage")
async def gc_storage(
    _user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Find and delete orphaned storage files whose jobs no longer exist."""
    from app.services.storage_cleanup import garbage_collect_orphaned_files
    result = await garbage_collect_orphaned_files(db)
    return result


@router.post("/cleanup-failed")
async def cleanup_failed(
    _user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete failed jobs older than retention period, including their storage files."""
    from app.services.storage_cleanup import cleanup_failed_jobs
    result = await cleanup_failed_jobs(db, ttl_days=settings.failed_job_retention_days)
    return result


@router.post("/purge-intermediates")
async def purge_intermediates(
    _user: User = Depends(get_admin_user),
):
    """Delete ALL video and audio files from bucket (one-time cleanup)."""
    from app.storage import storage
    videos = await storage.delete_prefix("videos/")
    audio = await storage.delete_prefix("audio/")
    return {"deleted_videos": videos, "deleted_audio": audio}


# ---------------------------------------------------------------------------
# Queue monitoring (arq)
# ---------------------------------------------------------------------------

@router.get("/queue-stats")
async def queue_stats(
    request: Request,
    _admin: User = Depends(get_admin_user),
):
    """Get arq task queue statistics from Redis."""
    managed = getattr(request.app.state, "managed_arq_pool", None)
    arq_pool = await managed.get_pool() if managed else getattr(request.app.state, "arq_pool", None)
    if not arq_pool:
        return {"error": "arq pool not available"}

    try:
        # arq stores queued jobs in a sorted set
        queued = await arq_pool.zcard(b"arq:queue")
        # arq stores in-progress jobs in a set
        in_progress = await arq_pool.scard(b"arq:in-progress")
        # arq stores results with prefix arq:result:
        info = await arq_pool.info()

        return {
            "queued": queued,
            "in_progress": in_progress,
            "redis_memory": info.get("used_memory_human", "unknown"),
            "redis_connected_clients": info.get("connected_clients", 0),
        }
    except Exception as e:
        logger.exception("[admin/queue-status] error")
        return {"error": "Internal server error"}


@router.get("/scaling-dashboard")
async def scaling_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    """Comprehensive scaling metrics for monitoring at 1000+ users."""
    from datetime import datetime, timedelta

    from sqlalchemy import func, select

    from app.database import engine
    from app.models.job import Job, JobStatus

    result: dict = {}

    # 1. Queue metrics
    managed = getattr(request.app.state, "managed_arq_pool", None)
    arq_pool = await managed.get_pool() if managed else getattr(request.app.state, "arq_pool", None)
    if arq_pool:
        try:
            result["queue"] = {
                "queued": await arq_pool.zcard(b"arq:queue"),
                "in_progress": await arq_pool.scard(b"arq:in-progress"),
            }
        except Exception:
            result["queue"] = {"error": "redis unavailable"}
    else:
        result["queue"] = {"error": "arq pool unavailable"}

    # 2. DB pool utilization
    pool = engine.pool
    result["db_pool"] = {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "max_overflow": pool._max_overflow,
    }

    # 3. Job throughput (last hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    completed_count = await db.scalar(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= one_hour_ago,
        )
    )
    failed_count = await db.scalar(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.FAILED,
            Job.updated_at >= one_hour_ago,
        )
    )
    pending_count = await db.scalar(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.PENDING,
        )
    )

    # Average job duration (last hour, completed only)
    avg_duration = await db.scalar(
        select(
            func.avg(
                func.extract("epoch", Job.completed_at) - func.extract("epoch", Job.created_at)
            )
        ).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= one_hour_ago,
        )
    )

    result["jobs"] = {
        "completed_last_hour": completed_count or 0,
        "failed_last_hour": failed_count or 0,
        "pending_now": pending_count or 0,
        "avg_duration_seconds": round(avg_duration, 1) if avg_duration else None,
    }

    return result


# ---------------------------------------------------------------------------
# Apify budget monitoring
# ---------------------------------------------------------------------------

@router.get("/apify-budget")
async def apify_budget(
    _admin: User = Depends(get_admin_user),
):
    """Show current Apify budget status: daily runs, balance, circuit breaker."""
    import json
    from datetime import date

    from app.services.scraper._apify_client import (
        _get_budget_redis,
        check_apify_balance,
    )

    r = await _get_budget_redis()
    result: dict = {"redis_available": r is not None}

    if r:
        today_key = f"apify:runs:{date.today().isoformat()}"
        result["daily_runs"] = int(await r.get(today_key) or 0)
        result["circuit_breaker_open"] = bool(await r.exists("apify:circuit_breaker"))

        cached = await r.get("apify:balance:cached")
        if cached:
            result["cached_balance"] = json.loads(cached)

    try:
        result["live_balance"] = await check_apify_balance()
    except Exception as e:
        logger.exception("[admin/apify-budget] live balance fetch error")
        result["live_balance_error"] = "Failed to fetch live balance"

    return result


# ---------------------------------------------------------------------------
# Migration: re-extract frames to S3 for old jobs
# ---------------------------------------------------------------------------

@router.post("/reextract-frames")
async def reextract_frames(
    request: Request,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Find completed jobs missing frames in S3 and re-extract them."""
    from app.storage import storage

    managed = getattr(request.app.state, "managed_arq_pool", None)
    arq_pool = await managed.get_pool() if managed else getattr(request.app.state, "arq_pool", None)
    if not arq_pool:
        raise HTTPException(status_code=503, detail="Task queue unavailable")

    # Get all completed jobs that have frames metadata
    result = await db.execute(
        select(Job.id).where(
            Job.status == JobStatus.COMPLETED,
            Job.frames.isnot(None),
        )
    )
    job_ids = [row[0] for row in result.all()]

    # Check which jobs are missing frames in S3
    enqueued = []
    for job_id in job_ids:
        try:
            keys = await storage.find_keys(f"frames/{job_id}/", limit=1)
            if not keys:
                await arq_pool.enqueue_job("task_reextract_frames", job_id)
                enqueued.append(job_id)
        except Exception:
            # S3 check failed — enqueue anyway
            await arq_pool.enqueue_job("task_reextract_frames", job_id)
            enqueued.append(job_id)

    return {
        "total_completed": len(job_ids),
        "missing_frames": len(enqueued),
        "enqueued_job_ids": enqueued,
    }


# ---------------------------------------------------------------------------
# Promo codes
# ---------------------------------------------------------------------------

@router.get("/promos")
async def list_promos(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all promo codes."""
    from app.models.promo import PromoCode

    result = await db.execute(
        select(PromoCode).order_by(PromoCode.created_at.desc())
    )
    promos = result.scalars().all()
    return {
        "promos": [
            {
                "id": p.id,
                "code": p.code,
                "discount_percent": p.discount_percent,
                "discount_kopecks": p.discount_kopecks,
                "max_uses": p.max_uses,
                "used_count": p.used_count,
                "duration_months": p.duration_months,
                "valid_tiers": p.valid_tiers,
                "valid_intervals": p.valid_intervals,
                "starts_at": p.starts_at.isoformat() if p.starts_at else None,
                "expires_at": p.expires_at.isoformat() if p.expires_at else None,
                "is_active": p.is_active,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in promos
        ]
    }


@router.post("/promos")
async def create_promo(
    payload: dict,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new promo code."""
    from app.models.promo import PromoCode

    code = payload.get("code", "").upper().strip()
    if not code or len(code) < 3:
        raise HTTPException(status_code=400, detail="Code must be at least 3 characters")

    # Check for duplicate
    existing = await db.execute(
        select(PromoCode).where(PromoCode.code == code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Code already exists")

    promo = PromoCode(
        code=code,
        discount_percent=payload.get("discount_percent"),
        discount_kopecks=payload.get("discount_kopecks"),
        max_uses=payload.get("max_uses"),
        duration_months=payload.get("duration_months"),
        valid_tiers=payload.get("valid_tiers"),
        valid_intervals=payload.get("valid_intervals"),
        starts_at=datetime.fromisoformat(payload["starts_at"]) if payload.get("starts_at") else None,
        expires_at=datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None,
    )
    db.add(promo)
    await db.commit()

    return {"ok": True, "id": promo.id, "code": promo.code}


@router.patch("/promos/{promo_id}")
async def update_promo(
    promo_id: str,
    payload: dict,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a promo code (toggle active, change limits, etc.)."""
    from app.models.promo import PromoCode

    result = await db.execute(select(PromoCode).where(PromoCode.id == promo_id))
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promo not found")

    if "is_active" in payload:
        promo.is_active = payload["is_active"]
    if "max_uses" in payload:
        promo.max_uses = payload["max_uses"]
    if "expires_at" in payload:
        promo.expires_at = datetime.fromisoformat(payload["expires_at"]) if payload["expires_at"] else None

    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@router.get("/metrics")
async def get_metrics(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current business metrics."""
    from app.services.metrics import calculate_daily_metrics, format_metrics_digest

    metrics = await calculate_daily_metrics(db)
    return {"metrics": metrics, "digest": format_metrics_digest(metrics)}


@router.post("/metrics/send-digest")
async def send_digest_now(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Send metrics digest to admin Telegram IDs now."""
    from app.services.metrics import send_daily_digest

    sent = await send_daily_digest(db)
    return {"ok": sent}


# ---------------------------------------------------------------------------
# Tracked Profiles (Trends)
# ---------------------------------------------------------------------------

@router.get("/tracked-profiles", response_model=AdminTrackedProfileListResponse)
async def list_tracked_profiles(
    q: str = Query("", description="Search by username"),
    source: str = Query("", description="Filter: user | auto | all"),
    active: str = Query("", description="Filter: active | inactive"),
    blocked: str = Query("", description="Filter: blocked | not_blocked"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tracked profiles with tracking user counts and trending reel counts."""
    from app.models.trends import ProfileReel, TrackedProfile, UserTrackedProfile

    # Subquery: count of users tracking each profile
    users_count_sq = (
        select(
            UserTrackedProfile.profile_id,
            func.count(UserTrackedProfile.id).label("cnt"),
        )
        .group_by(UserTrackedProfile.profile_id)
        .subquery()
    )

    # Subquery: count of trending reels per profile
    trending_sq = (
        select(
            ProfileReel.profile_id,
            func.count(ProfileReel.id).label("cnt"),
        )
        .where(ProfileReel.is_trending == True)  # noqa: E712
        .where(ProfileReel.is_hidden == False)  # noqa: E712
        .group_by(ProfileReel.profile_id)
        .subquery()
    )

    query = (
        select(
            TrackedProfile,
            func.coalesce(users_count_sq.c.cnt, 0).label("tracking_users_count"),
            func.coalesce(trending_sq.c.cnt, 0).label("trending_reels_count"),
        )
        .outerjoin(users_count_sq, TrackedProfile.id == users_count_sq.c.profile_id)
        .outerjoin(trending_sq, TrackedProfile.id == trending_sq.c.profile_id)
    )
    count_query = select(func.count(TrackedProfile.id))

    # Filters
    if q:
        like = f"%{q}%"
        query = query.where(TrackedProfile.username.ilike(like))
        count_query = count_query.where(TrackedProfile.username.ilike(like))

    if source == "user":
        # Only profiles that have at least one user tracking them
        has_users = select(UserTrackedProfile.profile_id).distinct()
        query = query.where(TrackedProfile.id.in_(has_users))
        count_query = count_query.where(TrackedProfile.id.in_(has_users))
    elif source == "auto":
        # Only profiles with no users tracking them (auto-added by parser)
        has_users = select(UserTrackedProfile.profile_id).distinct()
        query = query.where(TrackedProfile.id.notin_(has_users))
        count_query = count_query.where(TrackedProfile.id.notin_(has_users))

    if active == "active":
        query = query.where(TrackedProfile.is_active == True)  # noqa: E712
        count_query = count_query.where(TrackedProfile.is_active == True)  # noqa: E712
    elif active == "inactive":
        query = query.where(TrackedProfile.is_active == False)  # noqa: E712
        count_query = count_query.where(TrackedProfile.is_active == False)  # noqa: E712

    if blocked == "blocked":
        query = query.where(TrackedProfile.is_blocked == True)  # noqa: E712
        count_query = count_query.where(TrackedProfile.is_blocked == True)  # noqa: E712
    elif blocked == "not_blocked":
        query = query.where(TrackedProfile.is_blocked == False)  # noqa: E712
        count_query = count_query.where(TrackedProfile.is_blocked == False)  # noqa: E712

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(TrackedProfile.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(query)).all()

    # Stats: count profiles by creation date
    from app.schemas.admin import AdminTrackedProfileStats

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    stats_query = select(
        func.count(TrackedProfile.id).label("total"),
        func.count(TrackedProfile.id).filter(TrackedProfile.created_at >= today_start).label("today"),
        func.count(TrackedProfile.id).filter(
            TrackedProfile.created_at >= yesterday_start,
            TrackedProfile.created_at < today_start,
        ).label("yesterday"),
        func.count(TrackedProfile.id).filter(TrackedProfile.created_at >= week_start).label("week"),
        func.count(TrackedProfile.id).filter(TrackedProfile.created_at >= month_start).label("month"),
    )
    stats_row = (await db.execute(stats_query)).one()
    stats = AdminTrackedProfileStats(
        total=stats_row.total,
        today=stats_row.today,
        yesterday=stats_row.yesterday,
        week=stats_row.week,
        month=stats_row.month,
    )

    items = [
        AdminTrackedProfileItem(
            id=row.TrackedProfile.id,
            platform=row.TrackedProfile.platform,
            username=row.TrackedProfile.username,
            display_name=row.TrackedProfile.display_name,
            followers_count=row.TrackedProfile.followers_count,
            median_views=row.TrackedProfile.median_views,
            total_reels=row.TrackedProfile.total_reels or 0,
            niche=row.TrackedProfile.niche,
            is_active=row.TrackedProfile.is_active,
            is_blocked=row.TrackedProfile.is_blocked,
            blocked_at=row.TrackedProfile.blocked_at,
            blocked_reason=row.TrackedProfile.blocked_reason,
            check_priority=row.TrackedProfile.check_priority,
            last_checked_at=row.TrackedProfile.last_checked_at,
            created_at=row.TrackedProfile.created_at,
            tracking_users_count=row.tracking_users_count,
            trending_reels_count=row.trending_reels_count,
        )
        for row in rows
    ]
    return AdminTrackedProfileListResponse(items=items, total=total, page=page, per_page=per_page, stats=stats)


@router.patch("/tracked-profiles/{profile_id}")
async def toggle_tracked_profile(
    profile_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle is_active for a tracked profile."""
    from app.models.trends import TrackedProfile

    result = await db.execute(select(TrackedProfile).where(TrackedProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.is_active = not profile.is_active
    await db.commit()
    return {"id": profile.id, "is_active": profile.is_active}


@router.delete("/tracked-profiles/{profile_id}")
async def delete_tracked_profile(
    profile_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tracked profile and all its reels and user links."""
    from app.models.trends import TrackedProfile

    result = await db.execute(select(TrackedProfile).where(TrackedProfile.id == profile_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Profile not found")

    # CASCADE will handle ProfileReel and UserTrackedProfile
    await db.execute(delete(TrackedProfile).where(TrackedProfile.id == profile_id))
    await db.commit()
    return {"deleted": True}


@router.post("/tracked-profiles/{profile_id}/block")
async def block_tracked_profile(
    profile_id: str,
    payload: BlockProfileRequest,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Block a tracked profile — hides from trends, stops scraping, prevents adding."""
    from app.models.trends import TrackedProfile

    result = await db.execute(select(TrackedProfile).where(TrackedProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.is_blocked = True
    profile.blocked_at = datetime.utcnow()
    profile.blocked_reason = payload.reason or None
    profile.is_active = False
    await db.commit()
    return {
        "id": profile.id,
        "is_blocked": True,
        "is_active": False,
        "blocked_at": profile.blocked_at.isoformat() if profile.blocked_at else None,
    }


@router.post("/tracked-profiles/{profile_id}/unblock")
async def unblock_tracked_profile(
    profile_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Unblock a tracked profile — restores to active state."""
    from app.models.trends import TrackedProfile

    result = await db.execute(select(TrackedProfile).where(TrackedProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.is_blocked = False
    profile.blocked_at = None
    profile.blocked_reason = None
    profile.is_active = True
    await db.commit()
    return {"id": profile.id, "is_blocked": False, "is_active": True}


@router.post("/reels/{reel_id}/hide")
async def hide_reel(
    reel_id: str,
    payload: HideReelRequest,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Hide a reel from trends (soft-delete from public visibility)."""
    from app.models.trends import ProfileReel

    result = await db.execute(select(ProfileReel).where(ProfileReel.id == reel_id))
    reel = result.scalar_one_or_none()
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")

    reel.is_hidden = True
    reel.hidden_at = datetime.utcnow()
    reel.hidden_reason = payload.reason or None
    await db.commit()
    return {
        "id": reel.id,
        "is_hidden": True,
        "hidden_at": reel.hidden_at.isoformat() if reel.hidden_at else None,
    }


@router.post("/reels/{reel_id}/unhide")
async def unhide_reel(
    reel_id: str,
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Unhide a reel — restore to trends visibility."""
    from app.models.trends import ProfileReel

    result = await db.execute(select(ProfileReel).where(ProfileReel.id == reel_id))
    reel = result.scalar_one_or_none()
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")

    reel.is_hidden = False
    reel.hidden_at = None
    reel.hidden_reason = None
    await db.commit()
    return {"id": reel.id, "is_hidden": False}


@router.get("/hidden-reels", response_model=AdminHiddenReelListResponse)
async def list_hidden_reels(
    q: str = Query("", description="Search by URL, caption, or author"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all hidden reels with author info."""
    from app.models.trends import ProfileReel, TrackedProfile

    base = (
        select(ProfileReel, TrackedProfile)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(ProfileReel.is_hidden == True)  # noqa: E712
    )
    count_base = (
        select(func.count(ProfileReel.id))
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(ProfileReel.is_hidden == True)  # noqa: E712
    )

    if q:
        like = f"%{q}%"
        flt = or_(
            ProfileReel.url.ilike(like),
            ProfileReel.caption.ilike(like),
            TrackedProfile.username.ilike(like),
        )
        base = base.where(flt)
        count_base = count_base.where(flt)

    total = (await db.execute(count_base)).scalar() or 0
    rows = (
        await db.execute(
            base.order_by(ProfileReel.hidden_at.desc().nullslast())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
    ).all()

    items = [
        AdminHiddenReelItem(
            id=reel.id,
            url=reel.url,
            caption=reel.caption,
            thumbnail_url=reel.thumbnail_url,
            views=reel.views,
            profile_username=profile.username,
            profile_platform=profile.platform,
            hidden_at=reel.hidden_at,
            hidden_reason=reel.hidden_reason,
        )
        for reel, profile in rows
    ]
    return AdminHiddenReelListResponse(items=items, total=total, page=page, per_page=per_page)


# ---------------------------------------------------------------------------
# Admin Trending Reels
# ---------------------------------------------------------------------------

@router.get("/trending-reels", response_model=AdminTrendingReelsResponse)
async def list_trending_reels(
    date_range: str = Query("today", description="today, yesterday, 2days, week, all"),
    niche: str = Query("", description="Filter by niche"),
    platform: str = Query("", description="Filter by platform"),
    sort: str = Query("hot_score", description="hot_score, x_factor, views, recent"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List trending reels for admin dashboard with date filtering and summary stats."""
    from app.models.trends import ProfileReel, TrackedProfile

    # Date range filter on trending_since (exclusive upper bound to avoid duplicates at midnight)
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    date_filter = None
    if date_range == "today":
        date_filter = ProfileReel.trending_since >= today_start
    elif date_range == "yesterday":
        yesterday_start = today_start - timedelta(days=1)
        date_filter = (ProfileReel.trending_since >= yesterday_start) & (ProfileReel.trending_since < today_start)
    elif date_range == "2days":
        two_days_start = today_start - timedelta(days=2)
        date_filter = (ProfileReel.trending_since >= two_days_start) & (ProfileReel.trending_since < today_start)
    elif date_range == "week":
        date_filter = ProfileReel.trending_since >= now - timedelta(days=7)

    # Base query
    base_where = [
        ProfileReel.is_trending == True,  # noqa: E712
        ProfileReel.is_hidden == False,  # noqa: E712
        TrackedProfile.is_blocked == False,  # noqa: E712
    ]
    if date_filter is not None:
        base_where.append(date_filter)
    if niche:
        base_where.append(ProfileReel.niche == niche)
    if platform:
        base_where.append(TrackedProfile.platform == platform)

    # Count
    count_q = (
        select(func.count(ProfileReel.id))
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(*base_where)
    )
    total = (await db.execute(count_q)).scalar() or 0

    # Summary: avg hot_score
    summary_q = (
        select(func.avg(ProfileReel.hot_score))
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(*base_where)
    )
    avg_hot = (await db.execute(summary_q)).scalar()

    # Summary: top niches
    niche_q = (
        select(ProfileReel.niche, func.count(ProfileReel.id).label("cnt"))
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(*base_where, ProfileReel.niche.isnot(None), ProfileReel.niche != "")
        .group_by(ProfileReel.niche)
        .order_by(func.count(ProfileReel.id).desc())
        .limit(5)
    )
    niche_rows = (await db.execute(niche_q)).all()
    top_niches = [AdminTrendingNicheStat(niche=r[0], count=r[1]) for r in niche_rows]

    # Sort
    sort_col = ProfileReel.hot_score.desc().nullslast()
    if sort == "x_factor":
        sort_col = ProfileReel.x_factor.desc().nullslast()
    elif sort == "views":
        sort_col = ProfileReel.views.desc().nullslast()
    elif sort == "recent":
        sort_col = ProfileReel.trending_since.desc().nullslast()

    # Main query
    main_q = (
        select(ProfileReel, TrackedProfile)
        .join(TrackedProfile, ProfileReel.profile_id == TrackedProfile.id)
        .where(*base_where)
        .order_by(sort_col)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(main_q)).all()

    items = [
        AdminTrendingReelItem(
            id=reel.id,
            url=reel.url,
            caption=reel.caption,
            thumbnail_url=reel.thumbnail_url,
            published_at=reel.published_at,
            trending_since=reel.trending_since,
            duration=reel.duration,
            views=reel.views,
            likes=reel.likes,
            comments=reel.comments,
            x_factor=reel.x_factor,
            velocity=reel.velocity,
            hot_score=reel.hot_score,
            niche=reel.niche,
            author_id=profile.id,
            author_username=profile.username,
            author_platform=profile.platform,
            author_display_name=profile.display_name,
            author_followers=profile.followers_count,
        )
        for reel, profile in rows
    ]

    return AdminTrendingReelsResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        summary=AdminTrendingSummary(
            total_trending=total,
            avg_hot_score=round(avg_hot, 4) if avg_hot is not None else None,
            top_niches=top_niches,
        ),
    )


# ---------------------------------------------------------------------------
# Showcase Dashboard (cinematic stats for social media content)
# ---------------------------------------------------------------------------

@router.post("/reset-baseline")
async def reset_baseline(
    _admin: User = Depends(get_admin_user),
):
    """Reset showcase stats baseline to current moment."""
    from app.core.redis_pool import get_redis
    r = await get_redis()
    if not r:
        raise HTTPException(status_code=500, detail="Redis unavailable")
    now = datetime.utcnow().isoformat()
    await r.set("showcase:baseline", now)
    return {"baseline": now}


# ---------------------------------------------------------------------------
# Demo mode toggle
# ---------------------------------------------------------------------------

@router.get("/demo-mode")
async def get_demo_mode(_admin: User = Depends(get_admin_user)):
    """Current state of the demo-data overlay."""
    return {"enabled": await demo_data.is_demo_mode()}


@router.post("/demo-mode")
async def update_demo_mode(
    enabled: bool = Body(..., embed=True),
    _admin: User = Depends(get_admin_user),
):
    """Toggle the demo-data overlay on/off (admin only).

    When ON, analytics dashboards show a synthetic ≈500 000 ₽/мес picture.
    Nothing is written to the DB and real payment logic is untouched.
    """
    try:
        await demo_data.set_demo_mode(enabled)
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Redis unavailable")
    return {"enabled": enabled}


@router.get("/showcase", response_model=ShowcaseStatsResponse)
async def get_showcase_stats(
    _admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    today: bool = False,
):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_30d = now - timedelta(days=30)
    today_date = now.date()

    # Launch date: read from Redis (set by /reset-baseline), fallback to hardcoded
    from app.core.redis_pool import get_redis
    _default_launch = datetime(2026, 3, 21, 18, 30)
    r = await get_redis()
    baseline_str = await r.get("showcase:baseline") if r else None
    launch_date = datetime.fromisoformat(baseline_str) if baseline_str else _default_launch

    # When today=True, filter everything from today_start instead of launch_date
    period_start = today_start if today else launch_date

    # 1. User counts by tier
    # Headline "Пользователей" shows ALL non-anonymous users (full lifetime), not
    # filtered by launch date — the launch-date filter made the number look fake
    # (under-counted, since pre-launch beta users don't suddenly stop being users).
    # `today=True` keeps the today-only filter for the daily mode.
    user_filter = (User.created_at >= period_start) if today else (User.is_anonymous == False)  # noqa: E712
    user_counts = (await db.execute(
        select(
            func.count(case((User.is_anonymous == False, 1))).label("registered"),  # noqa: E712
            func.count(case((User.tier == "FREE", 1))).label("free"),
            func.count(case((User.tier == "START", 1))).label("start"),
            func.count(case((User.tier == "PRO", 1))).label("pro"),
            func.count(case((User.tier == "UNLIMITED", 1))).label("unlimited"),
        ).where(user_filter)
    )).one()

    total_registered = user_counts.registered
    total_paid = user_counts.start + user_counts.pro + user_counts.unlimited
    conversion_pct = round((total_paid / total_registered * 100) if total_registered > 0 else 0, 1)

    # 2. Revenue totals — all succeeded payments (full lifetime, unless today=True)
    revenue_where = [Payment.status == "succeeded"]
    if today:
        revenue_where.append(Payment.paid_at >= period_start)
    revenue = (await db.execute(
        select(
            func.coalesce(func.sum(case(
                (Payment.currency == "RUB", Payment.amount_kopecks),
                else_=0,
            )), 0).label("rub"),
            func.coalesce(func.sum(case(
                (Payment.currency == "EUR", Payment.amount_kopecks),
                else_=0,
            )), 0).label("eur"),
        ).where(*revenue_where)
    )).one()

    # 3. Analyses — completed jobs with known platform (matches success-rate ring + platform sum)
    analyses_where = [
        Job.status == JobStatus.COMPLETED,
        Job.video_platform.isnot(None),
    ]
    if today:
        analyses_where.append(Job.created_at >= period_start)
    total_analyses = (await db.execute(
        select(func.count(Job.id)).where(*analyses_where)
    )).scalar() or 0

    analyses_today = (await db.execute(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.COMPLETED,
            Job.video_platform.isnot(None),
            Job.created_at >= max(today_start, period_start),
        )
    )).scalar() or 0

    # 4. Daily breakdown (30 days): new users, revenue, analyses
    daily_cutoff = max(cutoff_30d, launch_date)

    users_daily = dict((await db.execute(
        select(
            cast(User.created_at, Date).label("day"),
            func.count(User.id).label("cnt"),
        )
        .where(User.created_at >= daily_cutoff, User.is_anonymous == False)  # noqa: E712
        .group_by(cast(User.created_at, Date))
    )).all())

    revenue_daily_rows = (await db.execute(
        select(
            cast(Payment.paid_at, Date).label("day"),
            func.coalesce(func.sum(case(
                (Payment.currency == "RUB", Payment.amount_kopecks), else_=0,
            )), 0).label("rub"),
            func.coalesce(func.sum(case(
                (Payment.currency == "EUR", Payment.amount_kopecks), else_=0,
            )), 0).label("eur"),
        )
        .where(Payment.status == "succeeded", Payment.paid_at >= daily_cutoff)
        .group_by(cast(Payment.paid_at, Date))
    )).all()
    revenue_daily = {row.day: row for row in revenue_daily_rows}

    analyses_daily = dict((await db.execute(
        select(
            cast(Job.created_at, Date).label("day"),
            func.count(Job.id).label("cnt"),
        )
        .where(Job.status == JobStatus.COMPLETED, Job.created_at >= daily_cutoff)
        .group_by(cast(Job.created_at, Date))
    )).all())

    daily = []
    for i in range(29, -1, -1):
        d = today_date - timedelta(days=i)
        rev = revenue_daily.get(d)
        daily.append(ShowcaseDayStats(
            date=d.isoformat(),
            new_users=users_daily.get(d, 0),
            revenue_rub_kopecks=rev.rub if rev else 0,
            revenue_eur_cents=rev.eur if rev else 0,
            analyses=analyses_daily.get(d, 0),
        ))

    # 5. Ratings stats
    rating_stats = (await db.execute(
        select(
            func.avg(ScriptRating.rating).label("avg"),
            func.count(ScriptRating.id).label("total"),
            func.count(case((ScriptRating.viewed_at.is_(None), 1))).label("unread"),
        )
    )).one()

    # 6. Unread support conversations
    unread_support = (await db.execute(
        select(func.coalesce(func.sum(SupportConversation.unread_admin), 0))
    )).scalar() or 0

    # 7. Job stats (completed / failed / running)
    # Lifetime in default mode so the success-rate ring matches "Транскрибировано".
    # Filter out null platform so totals match Platform breakdown below.
    job_counts_where = [Job.video_platform.isnot(None)]
    if today:
        job_counts_where.append(Job.created_at >= period_start)
    job_counts = (await db.execute(
        select(
            func.count(case((Job.status == JobStatus.COMPLETED, 1))).label("completed"),
            func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
            func.count(case((
                Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]), 1
            ))).label("running"),
        ).where(*job_counts_where)
    )).one()
    jobs_total = job_counts.completed + job_counts.failed
    jobs_success_rate = round(
        (job_counts.completed / jobs_total * 100) if jobs_total > 0 else 0, 1
    )

    # 8. Platform breakdown — same time window as job_counts so sums line up
    platform_where = [Job.video_platform.isnot(None)]
    if today:
        platform_where.append(Job.created_at >= period_start)
    platform_rows = (await db.execute(
        select(
            Job.video_platform.label("platform"),
            func.count(Job.id).label("total"),
            func.count(case((Job.status == JobStatus.COMPLETED, 1))).label("completed"),
            func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
        )
        .where(*platform_where)
        .group_by(Job.video_platform)
    )).all()
    platform_stats = [
        ShowcasePlatformStat(
            platform=row.platform,
            total=row.total,
            completed=row.completed,
            failed=row.failed,
            success_rate=round((row.completed / row.total * 100) if row.total > 0 else 0, 1),
        )
        for row in platform_rows
    ]

    # 9. Speed metrics
    one_hour_ago = now - timedelta(hours=1)
    avg_proc = (await db.execute(
        select(func.avg(
            extract("epoch", Job.completed_at) - extract("epoch", Job.created_at)
        )).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at.isnot(None),
            Job.created_at >= period_start,
        )
    )).scalar()

    fastest_today = (await db.execute(
        select(func.min(
            extract("epoch", Job.completed_at) - extract("epoch", Job.created_at)
        )).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at.isnot(None),
            Job.created_at >= today_start,
        )
    )).scalar()

    jobs_last_hour = (await db.execute(
        select(func.count(Job.id)).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= one_hour_ago,
        )
    )).scalar() or 0

    # 10. Active jobs (for pipeline visualization)
    active_rows = (await db.execute(
        select(Job, User.email)
        .join(User, Job.user_id == User.id, isouter=True)
        .where(Job.status.notin_([JobStatus.COMPLETED, JobStatus.FAILED]))
        .order_by(Job.created_at.desc())
        .limit(15)
    )).all()

    def _mask_email(email: str | None) -> str | None:
        if not email:
            return None
        local, _, domain = email.partition("@")
        if not domain:
            return None
        if len(local) <= 2:
            return f"{local[0]}***@{domain}" if local else f"***@{domain}"
        return f"{local[:3]}***@{domain}"

    active_jobs = [
        ShowcaseActiveJob(
            job_id=j.id,
            status=j.status.value,
            progress=j.progress or 0.0,
            video_platform=j.video_platform,
            video_author=j.video_author,
            video_title=j.video_title[:80] if j.video_title else None,
            source=j.source,
            masked_email=_mask_email(email),
            created_at=j.created_at.isoformat() if j.created_at else "",
        )
        for j, email in active_rows
    ]

    # 11a. Trend monitoring stats (lifetime — what the system has tracked overall)
    from app.models.trends import TrackedProfile, ProfileReel
    tracked_authors = (await db.execute(
        select(func.count(TrackedProfile.id)).where(
            TrackedProfile.is_active == True,  # noqa: E712
            func.coalesce(TrackedProfile.is_blocked, False) == False,  # noqa: E712
        )
    )).scalar() or 0
    total_trends_found = (await db.execute(
        select(func.count(ProfileReel.id))
    )).scalar() or 0
    trends_currently_hot = (await db.execute(
        select(func.count(ProfileReel.id)).where(ProfileReel.is_trending == True)  # noqa: E712
    )).scalar() or 0
    avg_trends_per_author = round(total_trends_found / tracked_authors, 1) if tracked_authors > 0 else 0.0

    # 11. Activity heatmap (completed jobs grouped by weekday x hour, last 30 days)
    heatmap_rows = (await db.execute(
        select(
            extract("dow", Job.created_at).label("dow"),  # 0=Sun in PG
            extract("hour", Job.created_at).label("hr"),
            func.count(Job.id).label("cnt"),
        )
        .where(Job.status == JobStatus.COMPLETED, Job.created_at >= daily_cutoff)
        .group_by(extract("dow", Job.created_at), extract("hour", Job.created_at))
    )).all()
    # Convert PG dow (0=Sun) to Python weekday (0=Mon)
    activity_heatmap = [
        ShowcaseHeatmapCell(
            weekday=(int(row.dow) - 1) % 7,  # PG: 0=Sun → Python: 6=Sun
            hour=int(row.hr),
            count=row.cnt,
        )
        for row in heatmap_rows
    ]

    # Demo mode: overlay synthetic funnel + revenue. Operational metrics
    # (analyses, platform health, ratings, active jobs, heatmap) stay real.
    free_users_out = user_counts.free
    start_users_out = user_counts.start
    pro_users_out = user_counts.pro
    unlimited_users_out = user_counts.unlimited
    total_rub_out = revenue.rub
    total_eur_out = revenue.eur
    if await demo_data.is_demo_mode():
        ov = demo_data.showcase_overlay(now, launch_date, today)
        total_registered = ov["total_registered"]
        total_paid = ov["total_paid"]
        conversion_pct = ov["conversion_pct"]
        free_users_out = ov["free_users"]
        start_users_out = ov["start_users"]
        pro_users_out = ov["pro_users"]
        unlimited_users_out = ov["unlimited_users"]
        total_rub_out = ov["total_rub_kopecks"]
        total_eur_out = ov["total_eur_cents"]
        for ds in daily:
            r = ov["daily_revenue"].get(ds.date)
            if r:
                ds.revenue_rub_kopecks = r["rub"]
                ds.revenue_eur_cents = r["eur"]
        # Mask real user emails in the live pipeline feed.
        for aj in active_jobs:
            aj.masked_email = demo_data.mask_email(demo_data.demo_identity(aj.job_id)["user_email"])

    return ShowcaseStatsResponse(
        total_registered=total_registered,
        total_paid=total_paid,
        conversion_pct=conversion_pct,
        free_users=free_users_out,
        start_users=start_users_out,
        pro_users=pro_users_out,
        unlimited_users=unlimited_users_out,
        total_rub_kopecks=total_rub_out,
        total_eur_cents=total_eur_out,
        total_analyses=total_analyses,
        analyses_today=analyses_today,
        avg_rating=round(float(rating_stats.avg), 2) if rating_stats.avg else None,
        total_ratings=rating_stats.total,
        unread_ratings=rating_stats.unread,
        unread_support=unread_support,
        daily=daily,
        launched_at=launch_date.date().isoformat(),
        # New fields
        jobs_completed=job_counts.completed,
        jobs_failed=job_counts.failed,
        jobs_running=job_counts.running,
        jobs_success_rate=jobs_success_rate,
        platform_stats=platform_stats,
        avg_processing_seconds=round(float(avg_proc), 1) if avg_proc else None,
        fastest_today_seconds=round(float(fastest_today), 1) if fastest_today else None,
        jobs_per_hour=float(jobs_last_hour),
        active_jobs=active_jobs,
        activity_heatmap=activity_heatmap,
        tracked_authors=tracked_authors,
        total_trends_found=total_trends_found,
        trends_currently_hot=trends_currently_hot,
        avg_trends_per_author=avg_trends_per_author,
    )


# ---------------------------------------------------------------------------
# Founder avatar upload
# ---------------------------------------------------------------------------

FOUNDER_AVATAR_KEY = "system/founder-avatar"
AVATAR_ALLOWED_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/webp")
AVATAR_MAX_SIZE = 2 * 1024 * 1024  # 2MB


@router.post("/founder-avatar")
async def upload_founder_avatar(
    file: UploadFile = File(...),
    admin: User = Depends(get_admin_user),
):
    """Upload founder avatar image (admin only). Stored in S3."""
    if file.content_type not in AVATAR_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, or WebP images allowed")

    data = await file.read()
    if len(data) > AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 2MB)")

    from app.storage import storage

    # Determine extension from content type
    ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp"}
    ext = ext_map.get(file.content_type, "jpg")
    key = f"{FOUNDER_AVATAR_KEY}.{ext}"

    # Delete old avatars (any extension)
    for old_ext in ("png", "jpg", "webp"):
        old_key = f"{FOUNDER_AVATAR_KEY}.{old_ext}"
        try:
            if await storage.file_exists(old_key):
                await storage.delete_file(old_key)
        except Exception:
            pass

    await storage.write_file(key, data)
    logger.info("Founder avatar uploaded by admin %s (%s, %d bytes)", admin.email, ext, len(data))

    return {"ok": True, "key": key}


@router.get("/founder-avatar")
async def get_founder_avatar_admin(
    admin: User = Depends(get_admin_user),
):
    """Get founder avatar URL (admin, for preview)."""
    from app.storage import storage

    for ext in ("webp", "jpg", "png"):
        key = f"{FOUNDER_AVATAR_KEY}.{ext}"
        try:
            if await storage.file_exists(key):
                url = await storage.get_url(key, expires=3600)
                return {"url": url, "key": key}
        except Exception:
            pass

    return {"url": None, "key": None}


# ---------------------------------------------------------------------------
# Profile Parsing (deep-analyze tracking)
# ---------------------------------------------------------------------------

@router.get("/parsings", response_model=AdminParsingListResponse)
async def list_parsings(
    status: str | None = None,
    platform: str | None = None,
    q: str | None = None,
    date_range: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from app.models.user import ProfileParsing

    query = (
        select(ProfileParsing, User.email, User.name, User.tier)
        .outerjoin(User, ProfileParsing.user_id == User.id)
    )
    count_query = select(func.count(ProfileParsing.id))

    if status:
        query = query.where(ProfileParsing.status == status)
        count_query = count_query.where(ProfileParsing.status == status)

    if platform:
        query = query.where(ProfileParsing.platform == platform)
        count_query = count_query.where(ProfileParsing.platform == platform)

    if q:
        like = f"%{q}%"
        filt = or_(
            ProfileParsing.username.ilike(like),
            User.email.ilike(like),
            User.name.ilike(like),
        )
        query = query.where(filt)
        count_query = count_query.outerjoin(User, ProfileParsing.user_id == User.id).where(filt)

    if date_range == "today":
        since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(ProfileParsing.created_at >= since)
        count_query = count_query.where(ProfileParsing.created_at >= since)
    elif date_range == "week":
        since = datetime.utcnow() - timedelta(days=7)
        query = query.where(ProfileParsing.created_at >= since)
        count_query = count_query.where(ProfileParsing.created_at >= since)
    elif date_range == "month":
        since = datetime.utcnow() - timedelta(days=30)
        query = query.where(ProfileParsing.created_at >= since)
        count_query = count_query.where(ProfileParsing.created_at >= since)

    query = query.order_by(ProfileParsing.created_at.desc()).offset((page - 1) * per_page).limit(per_page)

    total = (await db.execute(count_query)).scalar() or 0
    rows = (await db.execute(query)).all()

    items = [
        AdminParsingItem(
            id=row.ProfileParsing.id,
            user_id=row.ProfileParsing.user_id,
            user_email=row.email,
            user_name=row.name,
            user_tier=row.tier,
            analysis_id=row.ProfileParsing.analysis_id,
            platform=row.ProfileParsing.platform,
            username=row.ProfileParsing.username,
            status=row.ProfileParsing.status,
            error=row.ProfileParsing.error,
            duration_seconds=row.ProfileParsing.duration_seconds,
            result_json=row.ProfileParsing.result_json,
            created_at=row.ProfileParsing.created_at,
            completed_at=row.ProfileParsing.completed_at,
        )
        for row in rows
    ]

    return AdminParsingListResponse(items=items, total=total, page=page, per_page=per_page)


@router.get("/parsings/stats", response_model=AdminParsingStatsResponse)
async def get_parsing_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from app.models.user import ProfileParsing

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(
            func.count(ProfileParsing.id).filter(ProfileParsing.status == "running").label("running"),
            func.count(ProfileParsing.id).filter(
                ProfileParsing.status == "completed",
                ProfileParsing.created_at >= today,
            ).label("completed_today"),
            func.count(ProfileParsing.id).filter(
                ProfileParsing.status == "failed",
                ProfileParsing.created_at >= today,
            ).label("failed_today"),
            func.count(ProfileParsing.id).filter(ProfileParsing.status == "completed").label("completed_total"),
            func.count(ProfileParsing.id).filter(ProfileParsing.status == "failed").label("failed_total"),
            func.avg(ProfileParsing.duration_seconds).filter(
                ProfileParsing.status == "completed"
            ).label("avg_duration"),
        )
    )
    row = result.one()

    return AdminParsingStatsResponse(
        running=row.running or 0,
        completed_today=row.completed_today or 0,
        failed_today=row.failed_today or 0,
        completed_total=row.completed_total or 0,
        failed_total=row.failed_total or 0,
        avg_duration_seconds=round(row.avg_duration, 1) if row.avg_duration else None,
    )


# ── Niches CRUD ──────────────────────────────────────────────────────────

@router.get("/niches", response_model=AdminNichesResponse)
async def list_niches(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """List all niches with video/author counts."""
    from app.models.niches import Niche
    from app.models.trends import ProfileReel, TrackedProfile

    # Fetch all niches
    result = await db.execute(select(Niche).order_by(Niche.group_key, Niche.sort_order))
    niches = result.scalars().all()

    # Video counts per niche
    vid_result = await db.execute(
        select(ProfileReel.niche, func.count(ProfileReel.id))
        .where(ProfileReel.niche.isnot(None))
        .group_by(ProfileReel.niche)
    )
    vid_counts: dict[str, int] = dict(vid_result.all())

    # Author counts per niche
    auth_result = await db.execute(
        select(TrackedProfile.niche, func.count(TrackedProfile.id))
        .where(TrackedProfile.niche.isnot(None))
        .group_by(TrackedProfile.niche)
    )
    auth_counts: dict[str, int] = dict(auth_result.all())

    # Videos/authors without niche
    vid_no_niche = await db.execute(
        select(func.count(ProfileReel.id)).where(
            or_(ProfileReel.niche.is_(None), ProfileReel.niche == "")
        )
    )
    auth_no_niche = await db.execute(
        select(func.count(TrackedProfile.id)).where(
            or_(TrackedProfile.niche.is_(None), TrackedProfile.niche == "")
        )
    )

    items = []
    for n in niches:
        items.append(AdminNicheItem(
            id=n.id,
            slug=n.slug,
            display_name=n.display_name,
            display_name_en=n.display_name_en,
            description=n.description,
            keywords=n.keywords or [],
            group_key=n.group_key,
            sort_order=n.sort_order,
            is_active=n.is_active,
            videos_count=vid_counts.get(n.slug, 0),
            authors_count=auth_counts.get(n.slug, 0),
            created_at=n.created_at,
            updated_at=n.updated_at,
        ))

    # Build groups from DB data
    groups_map: dict[str, list[str]] = {}
    for n in niches:
        groups_map.setdefault(n.group_key, []).append(n.slug)

    GROUP_LABELS = {
        "tech_ai": "Технологии и ИИ",
        "business_money": "Бизнес и деньги",
        "marketing_growth": "Маркетинг и рост",
        "creative": "Креатив",
        "education_career": "Образование и карьера",
        "health_wellness": "Здоровье и велнес",
        "lifestyle": "Лайфстайл",
        "entertainment": "Развлечения",
        "other": "Другое",
    }

    groups = [
        AdminNicheGroup(key=k, label=GROUP_LABELS.get(k, k), niches=v)
        for k, v in groups_map.items()
    ]

    return AdminNichesResponse(
        items=items,
        groups=groups,
        stats=AdminNicheStatsResponse(
            total_niches=len(niches),
            active_niches=sum(1 for n in niches if n.is_active),
            videos_without_niche=vid_no_niche.scalar() or 0,
            authors_without_niche=auth_no_niche.scalar() or 0,
        ),
    )


@router.post("/niches", response_model=AdminNicheItem, status_code=201)
async def create_niche(
    req: AdminNicheCreateRequest,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new niche."""
    import re
    from app.models.niches import Niche
    from app.core.niche_cache import niche_cache

    # Validate slug format
    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", req.slug) and len(req.slug) > 1:
        raise HTTPException(400, "Slug must contain only lowercase letters, numbers, and hyphens")
    if len(req.slug) < 2 or len(req.slug) > 50:
        raise HTTPException(400, "Slug must be 2-50 characters")

    # Check uniqueness
    existing = await db.execute(select(Niche).where(Niche.slug == req.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Niche with slug '{req.slug}' already exists")

    niche = Niche(
        slug=req.slug,
        display_name=req.display_name,
        display_name_en=req.display_name_en,
        description=req.description,
        keywords=req.keywords,
        group_key=req.group_key,
        sort_order=req.sort_order,
    )
    db.add(niche)
    await db.commit()
    await db.refresh(niche)

    # Refresh cache
    await niche_cache.refresh(db)

    return AdminNicheItem(
        id=niche.id,
        slug=niche.slug,
        display_name=niche.display_name,
        display_name_en=niche.display_name_en,
        description=niche.description,
        keywords=niche.keywords or [],
        group_key=niche.group_key,
        sort_order=niche.sort_order,
        is_active=niche.is_active,
        videos_count=0,
        authors_count=0,
        created_at=niche.created_at,
        updated_at=niche.updated_at,
    )


@router.patch("/niches/{slug}", response_model=AdminNicheItem)
async def update_niche(
    slug: str,
    req: AdminNicheUpdateRequest,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing niche."""
    from app.models.niches import Niche
    from app.models.trends import ProfileReel, TrackedProfile
    from app.core.niche_cache import niche_cache

    result = await db.execute(select(Niche).where(Niche.slug == slug))
    niche = result.scalar_one_or_none()
    if not niche:
        raise HTTPException(404, f"Niche '{slug}' not found")

    update_data = req.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(niche, field, value)

    await db.commit()
    await db.refresh(niche)

    # Refresh cache
    await niche_cache.refresh(db)

    # Get counts
    vid_count = await db.execute(
        select(func.count(ProfileReel.id)).where(ProfileReel.niche == slug)
    )
    auth_count = await db.execute(
        select(func.count(TrackedProfile.id)).where(TrackedProfile.niche == slug)
    )

    return AdminNicheItem(
        id=niche.id,
        slug=niche.slug,
        display_name=niche.display_name,
        display_name_en=niche.display_name_en,
        description=niche.description,
        keywords=niche.keywords or [],
        group_key=niche.group_key,
        sort_order=niche.sort_order,
        is_active=niche.is_active,
        videos_count=vid_count.scalar() or 0,
        authors_count=auth_count.scalar() or 0,
        created_at=niche.created_at,
        updated_at=niche.updated_at,
    )


@router.delete("/niches/{slug}")
async def deactivate_niche(
    slug: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: deactivate a niche (keeps data integrity)."""
    from app.models.niches import Niche
    from app.core.niche_cache import niche_cache

    result = await db.execute(select(Niche).where(Niche.slug == slug))
    niche = result.scalar_one_or_none()
    if not niche:
        raise HTTPException(404, f"Niche '{slug}' not found")

    niche.is_active = False
    await db.commit()
    await niche_cache.refresh(db)
    return {"deactivated": True, "slug": slug}


@router.post("/niches/{slug}/activate")
async def activate_niche(
    slug: str,
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-activate a deactivated niche."""
    from app.models.niches import Niche
    from app.core.niche_cache import niche_cache

    result = await db.execute(select(Niche).where(Niche.slug == slug))
    niche = result.scalar_one_or_none()
    if not niche:
        raise HTTPException(404, f"Niche '{slug}' not found")

    niche.is_active = True
    await db.commit()
    await niche_cache.refresh(db)
    return {"activated": True, "slug": slug}
