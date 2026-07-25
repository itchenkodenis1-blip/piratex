"""Tests for rating API endpoints: POST /jobs/{id}/rate, GET /jobs/{id}/rating, GET /admin/ratings."""

import uuid

import pytest
import pytest_asyncio

from app.models.feedback import ScriptRating
from app.models.job import Job, JobStatus
from app.models.user import User
from tests.conftest import auth_headers


@pytest_asyncio.fixture
async def user(db_session):
    u = User(
        id=str(uuid.uuid4()),
        tier="FREE",
        email=f"test-{uuid.uuid4().hex[:8]}@test.com",
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def completed_job(db_session, user):
    j = Job(
        id=str(uuid.uuid4()),
        user_id=user.id,
        url="https://instagram.com/reel/test123",
        status=JobStatus.COMPLETED,
        adaptation_summary={"script": "Test script", "description": "Test desc"},
    )
    db_session.add(j)
    await db_session.flush()
    return j


@pytest_asyncio.fixture
async def pending_job(db_session, user):
    j = Job(
        id=str(uuid.uuid4()),
        user_id=user.id,
        url="https://instagram.com/reel/pending",
        status=JobStatus.PENDING,
    )
    db_session.add(j)
    await db_session.flush()
    return j


# --- POST /api/jobs/{job_id}/rate ---


@pytest.mark.asyncio
async def test_rate_job_success(client, user, completed_job):
    resp = await client.post(
        f"/api/jobs/{completed_job.id}/rate",
        json={"rating": 4, "comment": "Pretty good!"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rating"] == 4
    assert data["comment"] == "Pretty good!"


@pytest.mark.asyncio
async def test_rate_job_5_stars_no_comment(client, user, completed_job):
    resp = await client.post(
        f"/api/jobs/{completed_job.id}/rate",
        json={"rating": 5},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rating"] == 5
    assert data["comment"] is None


@pytest.mark.asyncio
async def test_rate_job_upsert(client, user, completed_job):
    """Second rate should update, not create duplicate."""
    headers = auth_headers(user)
    # First rate
    resp1 = await client.post(
        f"/api/jobs/{completed_job.id}/rate",
        json={"rating": 2, "comment": "Bad"},
        headers=headers,
    )
    assert resp1.status_code == 200

    # Update rate
    resp2 = await client.post(
        f"/api/jobs/{completed_job.id}/rate",
        json={"rating": 5, "comment": "Actually great!"},
        headers=headers,
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["rating"] == 5
    assert data["comment"] == "Actually great!"


@pytest.mark.asyncio
async def test_rate_job_invalid_rating(client, user, completed_job):
    resp = await client.post(
        f"/api/jobs/{completed_job.id}/rate",
        json={"rating": 6},
        headers=auth_headers(user),
    )
    assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_rate_job_zero_rating(client, user, completed_job):
    resp = await client.post(
        f"/api/jobs/{completed_job.id}/rate",
        json={"rating": 0},
        headers=auth_headers(user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rate_pending_job_fails(client, user, pending_job):
    resp = await client.post(
        f"/api/jobs/{pending_job.id}/rate",
        json={"rating": 4},
        headers=auth_headers(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rate_nonexistent_job(client, user):
    resp = await client.post(
        "/api/jobs/nonexistent-id/rate",
        json={"rating": 4},
        headers=auth_headers(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rate_job_no_auth(client, completed_job):
    resp = await client.post(
        f"/api/jobs/{completed_job.id}/rate",
        json={"rating": 4},
    )
    assert resp.status_code == 401


# --- GET /api/jobs/{job_id}/rating ---


@pytest.mark.asyncio
async def test_get_rating_exists(client, db_session, user, completed_job):
    # Create rating directly
    rating = ScriptRating(
        user_id=user.id,
        job_id=completed_job.id,
        rating=3,
        comment="OK",
    )
    db_session.add(rating)
    await db_session.flush()

    resp = await client.get(
        f"/api/jobs/{completed_job.id}/rating",
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rating"] == 3
    assert data["comment"] == "OK"


@pytest.mark.asyncio
async def test_get_rating_not_found(client, user, completed_job):
    resp = await client.get(
        f"/api/jobs/{completed_job.id}/rating",
        headers=auth_headers(user),
    )
    assert resp.status_code == 404


# --- GET /api/jobs/{job_id} includes my_rating ---


@pytest.mark.asyncio
async def test_get_job_includes_my_rating(client, db_session, user, completed_job):
    rating = ScriptRating(
        user_id=user.id,
        job_id=completed_job.id,
        rating=4,
    )
    db_session.add(rating)
    await db_session.flush()

    resp = await client.get(
        f"/api/jobs/{completed_job.id}",
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["my_rating"] == 4


@pytest.mark.asyncio
async def test_get_job_no_rating_returns_null(client, user, completed_job):
    resp = await client.get(
        f"/api/jobs/{completed_job.id}",
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["my_rating"] is None
