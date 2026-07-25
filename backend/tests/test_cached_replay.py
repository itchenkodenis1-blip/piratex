"""Tests for cached replay — library_hit now creates a Job + enqueues task_cached_replay."""

import uuid

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from app.models.job import Job, JobStatus
from app.models.library import LibraryReel
from app.models.user import User, UserSettings
from app.services.job_creator import create_job_from_url


@pytest_asyncio.fixture
async def setup_library_hit(db_session):
    """Create a user + another user's LibraryReel for the same URL."""
    # Original user who analyzed the video
    original_user = User(
        id=str(uuid.uuid4()),
        tier="PRO",
        email="original@test.com",
    )
    db_session.add(original_user)

    # Original job
    original_job = Job(
        id=str(uuid.uuid4()),
        url="https://www.instagram.com/reel/ABC123",
        user_id=original_user.id,
        status=JobStatus.COMPLETED,
        video_title="Test Video",
        video_duration=30.0,
        video_platform="instagram",
        video_author="testauthor",
        video_description="Test description",
        video_views=10000,
        video_likes=500,
        video_comments=50,
        thumbnail_url="https://example.com/thumb.jpg",
        transcript=[{"text": "hello", "start": 0, "end": 1}],
        frames=[{"frame_index": 0, "timestamp": 0.0, "timecode": "00:00",
                 "frame_path": "frames/orig/frame_0000_0.jpg",
                 "visual_description": "A person", "screen_text": "", "scene_type": "talking_head"}],
    )
    db_session.add(original_job)
    await db_session.flush()

    # LibraryReel pointing to original job
    library_reel = LibraryReel(
        id=str(uuid.uuid4()),
        job_id=original_job.id,
        submitted_by=original_user.id,
        url="https://www.instagram.com/reel/ABC123",
        video_title="Test Video",
        video_duration=30.0,
        video_platform="instagram",
        video_author="testauthor",
        video_description="Test description",
        video_views=10000,
        video_likes=500,
        video_comments=50,
        transcript_text="hello",
        transcript_json=[{"text": "hello", "start": 0, "end": 1}],
        frames_json=[{"frame_index": 0, "timestamp": 0.0, "timecode": "00:00",
                       "frame_path": "frames/orig/frame_0000_0.jpg",
                       "visual_description": "A person", "screen_text": "", "scene_type": "talking_head"}],
    )
    db_session.add(library_reel)

    # New user who will hit the library
    new_user = User(
        id=str(uuid.uuid4()),
        tier="FREE",
        email="new@test.com",
    )
    db_session.add(new_user)
    await db_session.flush()

    return new_user, library_reel, original_job


@pytest.mark.asyncio
async def test_library_hit_creates_job_instead_of_instant_return(db_session, setup_library_hit):
    """When URL is in library, should create a Job + enqueue task_cached_replay, not return library_hit."""
    new_user, library_reel, original_job = setup_library_hit

    mock_pool = AsyncMock()

    # Patch pg_advisory_xact_lock for SQLite
    with patch.object(db_session, "execute", wraps=db_session.execute) as mock_exec:
        # Override only the advisory lock call
        original_execute = db_session.execute

        async def patched_execute(stmt, *args, **kwargs):
            stmt_str = str(stmt) if not hasattr(stmt, 'text') else str(stmt.text)
            if "pg_advisory_xact_lock" in stmt_str:
                return None  # Skip advisory lock on SQLite
            return await original_execute(stmt, *args, **kwargs)

        with patch.object(db_session, "execute", side_effect=patched_execute):
            result = await create_job_from_url(
                db_session,
                new_user,
                "https://www.instagram.com/reel/ABC123/",
                mock_pool,
                source="web",
            )

    # Should NOT be library_hit anymore
    assert result.outcome == "created", f"Expected 'created', got '{result.outcome}'"

    # Should have created a real Job
    assert result.job is not None
    assert result.job.user_id == new_user.id
    assert "ABC123" in result.job.url
    assert result.job.status == JobStatus.PENDING

    # Job should NOT have metadata/transcript/frames pre-populated
    # (task_cached_replay loads them from LibraryReel to preserve animation)
    assert result.job.video_title is None
    assert result.job.transcript is None
    assert result.job.frames is None

    # But should have library_reel_id set (for frame fallback + data loading)
    assert result.job.library_reel_id == library_reel.id

    # Should have enqueued task_cached_replay (not task_scrape_and_download)
    mock_pool.enqueue_job.assert_called_once()
    call_args = mock_pool.enqueue_job.call_args
    assert call_args[0][0] == "task_cached_replay"
    assert call_args[0][1] == result.job.id


@pytest.mark.asyncio
async def test_library_hit_respects_quota(db_session, setup_library_hit):
    """Cached replay should cost 1 analysis and respect tier limits."""
    new_user, library_reel, _ = setup_library_hit

    mock_pool = AsyncMock()

    # Create 3 existing jobs to exhaust FREE tier (3/month)
    for i in range(3):
        job = Job(
            id=str(uuid.uuid4()),
            url=f"https://www.instagram.com/reel/other{i}/",
            user_id=new_user.id,
            status=JobStatus.COMPLETED,
        )
        db_session.add(job)
    await db_session.flush()

    async def patched_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt) if not hasattr(stmt, 'text') else str(stmt.text)
        if "pg_advisory_xact_lock" in stmt_str:
            return None
        return await db_session.__class__.execute(db_session, stmt, *args, **kwargs)

    with patch.object(db_session, "execute", side_effect=patched_execute):
        result = await create_job_from_url(
            db_session,
            new_user,
            "https://www.instagram.com/reel/ABC123/",
            mock_pool,
            source="web",
        )

    assert result.outcome == "limit_exceeded"
    mock_pool.enqueue_job.assert_not_called()
