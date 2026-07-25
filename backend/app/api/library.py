import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

logger = logging.getLogger(__name__)
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, get_optional_user
from app.database import get_db
from app.models.job import Job, JobStatus
from app.models.library import (
    LibraryReel,
    ScriptTranslation,
    Tag,
    UserBookmark,
    UserScript,
    library_reel_tags,
)
from app.models.user import User, UserSettings
from app.schemas.analysis import AdaptationSummary, _sanitize_dashes
from app.schemas.library import (
    LibraryListResponse,
    LibraryReelCard,
    LibraryReelDetail,
    ScriptTranslationOut,
    TagResponse,
    TranslateScriptRequest,
    UpdateScriptRequest,
    UserScriptResponse,
)

library_router = APIRouter(prefix="/library", tags=["library"])


def _build_reel_card(reel, tag_names: list[str], has_script: bool = False) -> LibraryReelCard:
    """Helper to build a LibraryReelCard from a model instance."""
    return LibraryReelCard(
        id=reel.id,
        url=reel.url,
        video_title=reel.video_title,
        video_duration=reel.video_duration,
        video_platform=reel.video_platform,
        video_author=reel.video_author,
        video_views=reel.video_views,
        video_likes=reel.video_likes,
        video_comments=reel.video_comments,
        original_language=reel.original_language,
        content_format=reel.content_format,
        tags=tag_names,
        job_id=reel.job_id,
        cover_frame_index=reel.cover_frame_index,
        has_user_script=has_script,
        created_at=reel.created_at,
    )


@library_router.get("", response_model=LibraryListResponse)
async def list_library(
    q: str = Query("", description="Search query"),
    tags: str = Query("", description="Comma-separated tag slugs"),
    platform: str = Query("", description="Filter by platform"),
    sort: str = Query("recent", description="Sort: recent or popular"),
    my_scripts: bool = Query(False, description="Only show reels where I have a script"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Browse the shared reel library."""
    query = select(LibraryReel)

    # Text search
    if q:
        query = query.where(
            LibraryReel.transcript_text.icontains(q)
            | LibraryReel.video_title.icontains(q)
            | LibraryReel.video_author.icontains(q)
        )

    # Platform filter
    if platform:
        query = query.where(LibraryReel.video_platform == platform)

    # Tag filter
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            query = query.where(
                LibraryReel.id.in_(
                    select(library_reel_tags.c.library_reel_id)
                    .join(Tag, Tag.id == library_reel_tags.c.tag_id)
                    .where(Tag.name.in_(tag_list))
                )
            )

    # My scripts filter (only if authenticated)
    if my_scripts and user:
        query = query.where(
            LibraryReel.id.in_(
                select(UserScript.library_reel_id).where(UserScript.user_id == user.id)
            )
        )

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Sort
    if sort == "popular":
        query = query.order_by(LibraryReel.video_views.desc().nullslast())
    else:
        query = query.order_by(LibraryReel.created_at.desc())

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    reels = result.scalars().all()

    # Batch-query user's scripts for these reels
    user_script_reel_ids: set[str] = set()
    if reels and user:
        reel_ids = [r.id for r in reels]
        script_result = await db.execute(
            select(UserScript.library_reel_id).where(
                UserScript.user_id == user.id,
                UserScript.library_reel_id.in_(reel_ids),
            )
        )
        user_script_reel_ids = {row[0] for row in script_result.all()}

    # Batch-load tags for all reels in one query
    tags_by_reel: dict[str, list[str]] = {}
    if reels:
        reel_ids_for_tags = [r.id for r in reels]
        tag_result = await db.execute(
            select(library_reel_tags.c.library_reel_id, Tag.name)
            .join(Tag, Tag.id == library_reel_tags.c.tag_id)
            .where(library_reel_tags.c.library_reel_id.in_(reel_ids_for_tags))
        )
        for rid, tname in tag_result.all():
            tags_by_reel.setdefault(rid, []).append(tname)

    items = [
        _build_reel_card(reel, tags_by_reel.get(reel.id, []), reel.id in user_script_reel_ids)
        for reel in reels
    ]

    return LibraryListResponse(items=items, total=total, page=page, per_page=per_page)


@library_router.get("/tags", response_model=list[TagResponse])
async def list_tags(
    db: AsyncSession = Depends(get_db),
):
    """Get all tags with reel counts."""
    result = await db.execute(
        select(
            Tag.id,
            Tag.name,
            Tag.display_name,
            Tag.category,
            func.count(library_reel_tags.c.library_reel_id).label("reel_count"),
        )
        .outerjoin(library_reel_tags, Tag.id == library_reel_tags.c.tag_id)
        .group_by(Tag.id)
        .order_by(func.count(library_reel_tags.c.library_reel_id).desc())
    )

    return [
        TagResponse(
            id=row.id,
            name=row.name,
            display_name=row.display_name,
            category=row.category,
            reel_count=row.reel_count,
        )
        for row in result.all()
    ]


@library_router.get("/bookmarks", response_model=list[LibraryReelCard])
async def list_bookmarks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get user's bookmarked reels."""
    result = await db.execute(
        select(LibraryReel)
        .join(UserBookmark, UserBookmark.library_reel_id == LibraryReel.id)
        .where(UserBookmark.user_id == user.id)
        .order_by(UserBookmark.created_at.desc())
    )
    reels = result.scalars().all()

    # Batch-query user's scripts
    user_script_reel_ids: set[str] = set()
    if reels:
        reel_ids = [r.id for r in reels]
        script_result = await db.execute(
            select(UserScript.library_reel_id).where(
                UserScript.user_id == user.id,
                UserScript.library_reel_id.in_(reel_ids),
            )
        )
        user_script_reel_ids = {row[0] for row in script_result.all()}

    # Batch-load tags
    tags_by_reel: dict[str, list[str]] = {}
    if reels:
        reel_ids_for_tags = [r.id for r in reels]
        tag_result = await db.execute(
            select(library_reel_tags.c.library_reel_id, Tag.name)
            .join(Tag, Tag.id == library_reel_tags.c.tag_id)
            .where(library_reel_tags.c.library_reel_id.in_(reel_ids_for_tags))
        )
        for rid, tname in tag_result.all():
            tags_by_reel.setdefault(rid, []).append(tname)

    return [
        _build_reel_card(reel, tags_by_reel.get(reel.id, []), reel.id in user_script_reel_ids)
        for reel in reels
    ]


@library_router.get("/{reel_id}", response_model=LibraryReelDetail)
async def get_library_reel(
    reel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    """Get full details of a library reel."""
    result = await db.execute(select(LibraryReel).where(LibraryReel.id == reel_id))
    reel = result.scalar_one_or_none()
    if not reel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel not found")

    # Load tags
    tag_result = await db.execute(
        select(Tag)
        .join(library_reel_tags, Tag.id == library_reel_tags.c.tag_id)
        .where(library_reel_tags.c.library_reel_id == reel.id)
    )
    tags = [
        TagResponse(id=t.id, name=t.name, display_name=t.display_name, category=t.category)
        for t in tag_result.scalars().all()
    ]

    # Fetch share_token and hook data from the associated job
    share_token = None
    summary_json = None
    hook_variants = None
    primary_hook_score = None
    primary_hook_why = None
    original_primary_hook = None
    hashtags = None
    job_result = await db.execute(
        select(Job.share_token, Job.adaptation_summary).where(Job.id == reel.job_id)
    )
    job_row = job_result.one_or_none()
    if job_row:
        share_token = job_row[0]
        summary_json = job_row[1]
        if summary_json and isinstance(summary_json, dict):
            hook_variants = summary_json.get("hook_variants")
            primary_hook_score = summary_json.get("primary_hook_score")
            primary_hook_why = summary_json.get("primary_hook_why")
            hashtags = summary_json.get("hashtags")
            # Extract original primary hook (first paragraph of original script)
            original_script = summary_json.get("script") or ""
            split_idx = original_script.find("\n\n")
            original_primary_hook = original_script[:split_idx] if split_idx > 0 else original_script or None

    # Check bookmark & user script (only if authenticated)
    is_bookmarked = False
    user_script = None
    translations: list[ScriptTranslationOut] = []

    if user:
        bm = await db.execute(
            select(UserBookmark).where(
                UserBookmark.user_id == user.id,
                UserBookmark.library_reel_id == reel.id,
            )
        )
        is_bookmarked = bm.scalar_one_or_none() is not None

        # Use current user's share_token (not the reel creator's)
        user_token_result = await db.execute(
            select(Job.share_token).where(
                Job.user_id == user.id,
                Job.library_reel_id == reel.id,
                Job.share_token.isnot(None),
            ).limit(1)
        )
        user_share_token = user_token_result.scalar_one_or_none()
        if user_share_token:
            share_token = user_share_token

        script_result = await db.execute(
            select(UserScript).where(
                UserScript.user_id == user.id,
                UserScript.library_reel_id == reel.id,
            )
        )
        user_script_row = script_result.scalar_one_or_none()

        # Auto-create UserScript if user has a completed job but no script record
        if not user_script_row:
            user_job_result = await db.execute(
                select(Job.adaptation_summary).where(
                    Job.user_id == user.id,
                    or_(Job.library_reel_id == reel.id, Job.id == reel.job_id),
                    Job.status == JobStatus.COMPLETED,
                ).order_by(Job.completed_at.desc()).limit(1)
            )
            user_job_summary = user_job_result.scalar_one_or_none()
            if user_job_summary and isinstance(user_job_summary, dict):
                s = user_job_summary.get("script") or ""
                d = user_job_summary.get("description") or ""
                e = user_job_summary.get("editor_instructions") or ""
                if s.strip():
                    user_script_row = UserScript(
                        user_id=user.id,
                        library_reel_id=reel.id,
                        script=s,
                        description=d,
                        editor_instructions=e,
                        original_script=s,
                        original_description=d,
                        original_editor_instructions=e,
                    )
                    db.add(user_script_row)
                    await db.commit()
                    await db.refresh(user_script_row)

        # Last-resort fallback: if user is the reel submitter and summary_json exists,
        # create UserScript from the original job's adaptation_summary
        if not user_script_row and reel.submitted_by == user.id and summary_json and isinstance(summary_json, dict):
            s = summary_json.get("script") or ""
            d = summary_json.get("description") or ""
            e = summary_json.get("editor_instructions") or ""
            if s.strip():
                user_script_row = UserScript(
                    user_id=user.id,
                    library_reel_id=reel.id,
                    script=s,
                    description=d,
                    editor_instructions=e,
                    original_script=s,
                    original_description=d,
                    original_editor_instructions=e,
                )
                db.add(user_script_row)
                await db.commit()
                await db.refresh(user_script_row)

        if user_script_row:
            # Backfill empty fields from job's adaptation_summary and persist
            script_text = user_script_row.script or ""
            description_text = user_script_row.description or ""
            editor_text = user_script_row.editor_instructions or ""
            needs_save = False
            if summary_json and isinstance(summary_json, dict):
                if not script_text.strip():
                    script_text = summary_json.get("script") or ""
                    if script_text.strip():
                        user_script_row.script = script_text
                        needs_save = True
                if not description_text.strip():
                    description_text = summary_json.get("description") or ""
                    if description_text.strip():
                        user_script_row.description = description_text
                        needs_save = True
                if not editor_text.strip():
                    editor_text = summary_json.get("editor_instructions") or ""
                    if editor_text.strip():
                        user_script_row.editor_instructions = editor_text
                        needs_save = True
            if needs_save:
                await db.commit()
                await db.refresh(user_script_row)

            user_script = UserScriptResponse(
                id=user_script_row.id,
                script=script_text,
                description=description_text,
                editor_instructions=editor_text,
                active_hook_index=user_script_row.active_hook_index or 0,
                created_at=user_script_row.created_at,
                updated_at=user_script_row.updated_at,
            )

            # Load second-language translations + compute staleness vs. current source
            from app.services.translator import compute_source_revision

            current_revision = compute_source_revision(
                AdaptationSummary(
                    script=script_text,
                    description=description_text,
                    editor_instructions=editor_text,
                )
            )
            tr_result = await db.execute(
                select(ScriptTranslation)
                .where(ScriptTranslation.user_script_id == user_script_row.id)
                .order_by(ScriptTranslation.created_at)
            )
            for tr in tr_result.scalars().all():
                translations.append(
                    ScriptTranslationOut(
                        id=tr.id,
                        language=tr.language,
                        script=tr.script,
                        description=tr.description,
                        editor_instructions=tr.editor_instructions,
                        stale=tr.source_revision is not None
                        and tr.source_revision != current_revision,
                        created_at=tr.created_at,
                        updated_at=tr.updated_at,
                    )
                )

    # Use user's own job_id (for rating), fallback to reel's original job_id
    effective_job_id = reel.job_id
    if user:
        user_job_result = await db.execute(
            select(Job.id).where(
                Job.user_id == user.id,
                Job.library_reel_id == reel.id,
                Job.status == JobStatus.COMPLETED,
            ).order_by(Job.completed_at.desc()).limit(1)
        )
        user_job_id = user_job_result.scalar_one_or_none()
        if user_job_id:
            effective_job_id = user_job_id

    return LibraryReelDetail(
        id=reel.id,
        url=reel.url,
        video_title=reel.video_title,
        video_duration=reel.video_duration,
        video_platform=reel.video_platform,
        video_author=reel.video_author,
        video_description=reel.video_description,
        video_views=reel.video_views,
        video_likes=reel.video_likes,
        video_comments=reel.video_comments,
        original_language=reel.original_language,
        content_format=reel.content_format,
        transcript_text=reel.transcript_text,
        transcript_json=reel.transcript_json,
        frames_json=reel.frames_json,
        tags=tags,
        job_id=effective_job_id,
        cover_frame_index=reel.cover_frame_index,
        is_bookmarked=is_bookmarked,
        has_user_script=user_script is not None,
        user_script=user_script,
        translations=translations,
        hook_variants=hook_variants,
        primary_hook_score=primary_hook_score,
        primary_hook_why=primary_hook_why,
        original_primary_hook=original_primary_hook,
        hashtags=hashtags,
        share_token=share_token,
        created_at=reel.created_at,
    )


@library_router.post("/{reel_id}/bookmark", status_code=status.HTTP_201_CREATED)
async def bookmark_reel(
    reel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bookmark a library reel."""
    # Check reel exists
    result = await db.execute(select(LibraryReel.id).where(LibraryReel.id == reel_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel not found")

    # Check not already bookmarked
    existing = await db.execute(
        select(UserBookmark).where(
            UserBookmark.user_id == user.id,
            UserBookmark.library_reel_id == reel_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"ok": True}

    bookmark = UserBookmark(user_id=user.id, library_reel_id=reel_id)
    db.add(bookmark)
    await db.commit()
    return {"ok": True}


@library_router.delete("/{reel_id}/bookmark")
async def unbookmark_reel(
    reel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove bookmark from a library reel."""
    await db.execute(
        delete(UserBookmark).where(
            UserBookmark.user_id == user.id,
            UserBookmark.library_reel_id == reel_id,
        )
    )
    await db.commit()
    return {"ok": True}


@library_router.patch("/{reel_id}/script", response_model=UserScriptResponse)
async def update_script(
    reel_id: str,
    body: UpdateScriptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update user's script text (manual edits)."""
    result = await db.execute(
        select(UserScript).where(
            UserScript.user_id == user.id,
            UserScript.library_reel_id == reel_id,
        )
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="No script found for this reel.")

    if body.script is not None:
        script.script = _sanitize_dashes(body.script)
    if body.description is not None:
        script.description = _sanitize_dashes(body.description)
    if body.editor_instructions is not None:
        script.editor_instructions = _sanitize_dashes(body.editor_instructions)
    if body.active_hook_index is not None:
        script.active_hook_index = body.active_hook_index

    await db.commit()
    await db.refresh(script)

    return UserScriptResponse(
        id=script.id,
        script=script.script,
        description=script.description,
        editor_instructions=script.editor_instructions,
        active_hook_index=script.active_hook_index or 0,
        created_at=script.created_at,
        updated_at=script.updated_at,
    )


def _translation_out(tr: ScriptTranslation, stale: bool = False) -> ScriptTranslationOut:
    return ScriptTranslationOut(
        id=tr.id,
        language=tr.language,
        script=tr.script,
        description=tr.description,
        editor_instructions=tr.editor_instructions,
        stale=stale,
        created_at=tr.created_at,
        updated_at=tr.updated_at,
    )


@library_router.post("/{reel_id}/translate", response_model=ScriptTranslationOut)
async def translate_script_endpoint(
    reel_id: str,
    body: TranslateScriptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate (or refresh) a second-language version of the user's script.

    Runs as a separate LLM iteration on top of the finished primary script.
    Free within the analysis — no analysis credit is consumed — but guarded by
    a short per-script+language cooldown to prevent abuse.
    """
    from app.core.redis_pool import get_redis
    from app.services.translator import compute_source_revision, translate_script

    result = await db.execute(
        select(UserScript).where(
            UserScript.user_id == user.id,
            UserScript.library_reel_id == reel_id,
        )
    )
    user_script = result.scalar_one_or_none()
    if not user_script:
        raise HTTPException(status_code=404, detail="No script found for this reel.")
    if not (user_script.script or "").strip():
        raise HTTPException(status_code=400, detail="Script is empty — nothing to translate.")

    target_language = body.language

    # Anti-abuse cooldown (best-effort; skipped if Redis is down). Does NOT bill.
    redis = await get_redis()
    if redis is not None:
        cooldown_key = f"translate_cooldown:{user_script.id}:{target_language}"
        try:
            if not await redis.set(cooldown_key, "1", ex=10, nx=True):
                raise HTTPException(
                    status_code=429,
                    detail="Please wait a few seconds before translating again.",
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Redis hiccup — don't block the user

    # Load user settings for source language + author profile
    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_result.scalar_one_or_none()
    source_language = (user_settings.language if user_settings and user_settings.language else "ru")
    profile_json = user_settings.profile_json if user_settings else None
    # BYO-key users translate with their own key; others fall back to the platform
    # key inside translate_script (which does `api_key or settings.anthropic_api_key`).
    anthropic_key = (user_settings.anthropic_api_key if user_settings else None) or ""

    if target_language == source_language:
        raise HTTPException(
            status_code=400,
            detail="Second language must differ from your primary language.",
        )

    source = AdaptationSummary(
        script=user_script.script,
        description=user_script.description,
        editor_instructions=user_script.editor_instructions,
    )
    revision = compute_source_revision(source)

    try:
        translated = await translate_script(
            source=source,
            source_language=source_language,
            target_language=target_language,
            profile_json=profile_json,
            api_key=anthropic_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("[translate] generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Translation failed. Please try again.")

    # Upsert: one translation per (user_script, language)
    existing = await db.execute(
        select(ScriptTranslation).where(
            ScriptTranslation.user_script_id == user_script.id,
            ScriptTranslation.language == target_language,
        )
    )
    tr = existing.scalar_one_or_none()
    if tr:
        # Refresh current text + revision, but preserve the original_* snapshot
        # (the first machine translation, kept for comparison).
        tr.script = translated.script
        tr.description = translated.description
        tr.editor_instructions = translated.editor_instructions
        tr.source_revision = revision
    else:
        tr = ScriptTranslation(
            user_script_id=user_script.id,
            language=target_language,
            script=translated.script,
            description=translated.description,
            editor_instructions=translated.editor_instructions,
            original_script=translated.script,
            original_description=translated.description,
            original_editor_instructions=translated.editor_instructions,
            source_revision=revision,
        )
        db.add(tr)

    await db.commit()
    await db.refresh(tr)
    return _translation_out(tr, stale=False)


@library_router.patch("/{reel_id}/translation/{language}", response_model=ScriptTranslationOut)
async def update_translation(
    reel_id: str,
    language: str,
    body: UpdateScriptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist manual edits / accepted refinements to a translated version."""
    from app.schemas.profile import SUPPORTED_LANGUAGES
    from app.services.translator import compute_source_revision

    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported language")

    result = await db.execute(
        select(ScriptTranslation, UserScript)
        .join(UserScript, UserScript.id == ScriptTranslation.user_script_id)
        .where(
            UserScript.user_id == user.id,
            UserScript.library_reel_id == reel_id,
            ScriptTranslation.language == language,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Translation not found.")
    tr, user_script = row

    if body.script is not None:
        tr.script = _sanitize_dashes(body.script)
    if body.description is not None:
        tr.description = _sanitize_dashes(body.description)
    if body.editor_instructions is not None:
        tr.editor_instructions = _sanitize_dashes(body.editor_instructions)

    # A manual edit means the user has synced this translation to the current
    # primary script — re-stamp the source revision so the "stale" banner clears.
    tr.source_revision = compute_source_revision(
        AdaptationSummary(
            script=user_script.script,
            description=user_script.description,
            editor_instructions=user_script.editor_instructions,
        )
    )

    await db.commit()
    await db.refresh(tr)
    return _translation_out(tr, stale=False)


@library_router.post("/{reel_id}/generate-script", response_model=UserScriptResponse)
async def generate_script(
    reel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a user's own script from existing library reel data."""
    # 1. Load reel
    result = await db.execute(select(LibraryReel).where(LibraryReel.id == reel_id))
    reel = result.scalar_one_or_none()
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")

    # 2. Check if script already exists
    existing = await db.execute(
        select(UserScript).where(
            UserScript.user_id == user.id,
            UserScript.library_reel_id == reel_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Script already exists. Use rewrite endpoint.")

    # 3. Get user settings
    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_result.scalar_one_or_none()

    from app.config import settings as app_settings

    anthropic_key = (user_settings.anthropic_api_key if user_settings else None) or app_settings.anthropic_api_key
    if not anthropic_key:
        raise HTTPException(status_code=400, detail="Anthropic API key not configured. Go to Settings to add your key.")

    language = (user_settings.language if user_settings and user_settings.language else "ru")
    custom_prompt = user_settings.custom_content_prompt if user_settings else None
    profile_json = user_settings.profile_json if user_settings else None

    # 4. Reconstruct analysis objects from stored JSON
    from app.schemas.analysis import FrameAnalysis, TranscriptSegment

    transcript_segments = [TranscriptSegment(**s) for s in (reel.transcript_json or [])]
    frame_analyses = [FrameAnalysis(**f) for f in (reel.frames_json or [])]

    # 5. Build metadata dict
    metadata = {
        "title": reel.video_title,
        "duration": reel.video_duration,
        "platform": reel.video_platform,
        "uploader": reel.video_author,
        "description": reel.video_description,
        "view_count": reel.video_views,
        "like_count": reel.video_likes,
        "comment_count": reel.video_comments,
    }

    # 6. Generate script
    from app.services.language_detect import detect_same_language
    from app.services.summarizer import generate_summary

    full_transcript = " ".join(seg.text for seg in transcript_segments)
    same_language = detect_same_language(full_transcript, language)

    try:
        adaptation = await generate_summary(
            metadata=metadata,
            transcript_segments=transcript_segments,
            frame_analyses=frame_analyses,
            comments=None,
            api_key=anthropic_key,
            target_language=language,
            custom_prompt=custom_prompt,
            video_url=reel.url,
            profile_json=profile_json,
            same_language=same_language,
        )
    except Exception:
        logger.exception("Script generation failed")
        raise HTTPException(status_code=502, detail="Script generation failed. Please try again.")

    # 7. Save UserScript
    new_script = UserScript(
        user_id=user.id,
        library_reel_id=reel_id,
        script=adaptation.script,
        description=adaptation.description,
        editor_instructions=adaptation.editor_instructions,
        original_script=adaptation.script,
        original_description=adaptation.description,
        original_editor_instructions=adaptation.editor_instructions,
    )
    db.add(new_script)

    # 7b. Create a completed Job so the video appears in "My Videos"
    from datetime import datetime
    from app.models.job import Job, JobStatus

    existing_job = (await db.execute(
        select(Job).where(Job.user_id == user.id, Job.library_reel_id == reel_id).limit(1)
    )).scalar_one_or_none()
    if not existing_job:
        job = Job(
            user_id=user.id,
            url=reel.url,
            status=JobStatus.COMPLETED,
            progress=100.0,
            video_title=reel.video_title,
            video_duration=reel.video_duration,
            video_platform=reel.video_platform,
            video_author=reel.video_author,
            video_views=reel.video_views,
            video_likes=reel.video_likes,
            video_comments=reel.video_comments,
            transcript=reel.transcript_json,
            frames=reel.frames_json,
            adaptation_summary={
                "script": adaptation.script,
                "description": adaptation.description,
                "editor_instructions": adaptation.editor_instructions,
            },
            library_reel_id=reel_id,
            source="library",
            completed_at=datetime.utcnow(),
        )
        db.add(job)

    # Record interest signals from the script's source reel (strongest signal)
    from app.models.library import Tag, library_reel_tags
    from app.services.interest_signals import record_signals

    tag_result = await db.execute(
        select(Tag.name)
        .join(library_reel_tags, library_reel_tags.c.tag_id == Tag.id)
        .where(library_reel_tags.c.library_reel_id == reel_id)
    )
    tags = [r[0] for r in tag_result.all()]
    if tags:
        await record_signals(
            db, user_id=user.id, topics=tags,
            source="script", weight=1.2, source_id=reel_id,
        )

    await db.commit()
    await db.refresh(new_script)

    return UserScriptResponse(
        id=new_script.id,
        script=new_script.script,
        description=new_script.description,
        editor_instructions=new_script.editor_instructions,
        active_hook_index=new_script.active_hook_index or 0,
        created_at=new_script.created_at,
        updated_at=new_script.updated_at,
    )


@library_router.post("/{reel_id}/rewrite-script", response_model=UserScriptResponse)
async def rewrite_script(
    reel_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Rewrite user's existing script for uniqueness."""
    # 1. Load existing UserScript
    result = await db.execute(
        select(UserScript).where(
            UserScript.user_id == user.id,
            UserScript.library_reel_id == reel_id,
        )
    )
    existing_script = result.scalar_one_or_none()
    if not existing_script:
        raise HTTPException(status_code=404, detail="No existing script to rewrite.")

    # 2. Load reel for context
    reel_result = await db.execute(select(LibraryReel).where(LibraryReel.id == reel_id))
    reel = reel_result.scalar_one_or_none()
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")

    # 3. Get user settings
    settings_result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    user_settings = settings_result.scalar_one_or_none()

    from app.config import settings as app_settings

    anthropic_key = (user_settings.anthropic_api_key if user_settings else None) or app_settings.anthropic_api_key
    if not anthropic_key:
        raise HTTPException(status_code=400, detail="Anthropic API key not configured. Go to Settings to add your key.")

    language = (user_settings.language if user_settings and user_settings.language else "ru")

    # 4. Rewrite
    from app.services.summarizer import rewrite_summary

    try:
        adaptation = await rewrite_summary(
            existing_script=existing_script.script,
            existing_description=existing_script.description,
            existing_editor_instructions=existing_script.editor_instructions,
            transcript_text=reel.transcript_text or "",
            api_key=anthropic_key,
            target_language=language,
            video_url=reel.url,
        )
    except Exception:
        logger.exception("Script rewrite failed")
        raise HTTPException(status_code=502, detail="Script rewrite failed. Please try again.")

    # 5. Update existing record (reset hook index — new script has a new hook)
    # Backfill original_* for records created before this feature
    if not existing_script.original_script:
        existing_script.original_script = existing_script.script
        existing_script.original_description = existing_script.description
        existing_script.original_editor_instructions = existing_script.editor_instructions
    existing_script.script = adaptation.script
    existing_script.description = adaptation.description
    existing_script.editor_instructions = adaptation.editor_instructions
    existing_script.active_hook_index = 0
    await db.commit()
    await db.refresh(existing_script)

    return UserScriptResponse(
        id=existing_script.id,
        script=existing_script.script,
        description=existing_script.description,
        editor_instructions=existing_script.editor_instructions,
        active_hook_index=existing_script.active_hook_index or 0,
        created_at=existing_script.created_at,
        updated_at=existing_script.updated_at,
    )


