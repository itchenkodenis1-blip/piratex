"""Phase 3 — bilingual scripts: API endpoints + library response.

Covers:
- POST /library/{reel_id}/translate — create translation (LLM mocked)
- 404 when no script, 400 when target == source language
- PATCH /library/{reel_id}/translation/{language} — persist edits
- GET /library/{reel_id} returns translations + stale flag
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.job import Job, JobStatus
from app.models.library import LibraryReel, ScriptTranslation, UserScript
from app.models.user import UserSettings
from app.schemas.analysis import AdaptationSummary
from tests.conftest import auth_headers


async def _make_reel_with_script(db_session, user, *, script="Слушайте, вот в чём дело. ~30 сек"):
    job = Job(
        id=str(uuid.uuid4()),
        url=f"https://insta.com/reel/{uuid.uuid4().hex[:8]}",
        user_id=user.id,
        status=JobStatus.COMPLETED,
        video_title="T",
        video_duration=30.0,
        video_platform="instagram",
        adaptation_summary={"script": script, "description": "Описание", "editor_instructions": "Кадр 1"},
    )
    db_session.add(job)
    await db_session.flush()
    reel = LibraryReel(
        id=str(uuid.uuid4()),
        job_id=job.id,
        submitted_by=user.id,
        url=job.url,
        video_title="T",
    )
    db_session.add(reel)
    await db_session.flush()
    us = UserScript(
        id=str(uuid.uuid4()),
        user_id=user.id,
        library_reel_id=reel.id,
        script=script,
        description="Описание",
        editor_instructions="Кадр 1",
        original_script=script,
        original_description="Описание",
        original_editor_instructions="Кадр 1",
    )
    db_session.add(us)
    await db_session.flush()
    return reel, us


def _mock_translate(script="Look, here's the deal. ~30 sec"):
    return patch(
        "app.services.translator.translate_script",
        AsyncMock(return_value=AdaptationSummary(
            script=script, description="Description", editor_instructions="Frame 1",
        )),
    )


@pytest.mark.asyncio
async def test_translate_creates_translation(client, db_session, make_user):
    user = await make_user(tier="PRO")
    reel, us = await _make_reel_with_script(db_session, user)
    with _mock_translate():
        resp = await client.post(
            f"/api/library/{reel.id}/translate",
            json={"language": "en"},
            headers=auth_headers(user),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["language"] == "en"
    assert body["script"] == "Look, here's the deal. ~30 sec"
    assert body["stale"] is False

    row = (await db_session.execute(
        ScriptTranslation.__table__.select().where(ScriptTranslation.user_script_id == us.id)
    )).first()
    assert row is not None


@pytest.mark.asyncio
async def test_translate_is_idempotent_upsert(client, db_session, make_user):
    """Translating the same language twice updates, not duplicates."""
    user = await make_user(tier="PRO")
    reel, us = await _make_reel_with_script(db_session, user)
    # Bypass the per-script cooldown so we can translate twice back-to-back
    no_redis = patch("app.core.redis_pool.get_redis", AsyncMock(return_value=None))
    with no_redis:
        with _mock_translate(script="V1"):
            await client.post(f"/api/library/{reel.id}/translate", json={"language": "en"}, headers=auth_headers(user))
        with _mock_translate(script="V2"):
            resp = await client.post(f"/api/library/{reel.id}/translate", json={"language": "en"}, headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["script"] == "V2"
    rows = (await db_session.execute(
        ScriptTranslation.__table__.select().where(ScriptTranslation.user_script_id == us.id)
    )).fetchall()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_translate_404_when_no_script(client, db_session, make_user):
    user = await make_user(tier="PRO")
    with _mock_translate():
        resp = await client.post(
            f"/api/library/{uuid.uuid4()}/translate",
            json={"language": "en"},
            headers=auth_headers(user),
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_translate_400_when_same_as_source_language(client, db_session, make_user):
    user = await make_user(tier="PRO")
    db_session.add(UserSettings(user_id=user.id, language="en"))
    reel, us = await _make_reel_with_script(db_session, user)
    with _mock_translate():
        resp = await client.post(
            f"/api/library/{reel.id}/translate",
            json={"language": "en"},
            headers=auth_headers(user),
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_translate_422_unsupported_language(client, db_session, make_user):
    user = await make_user(tier="PRO")
    reel, us = await _make_reel_with_script(db_session, user)
    resp = await client.post(
        f"/api/library/{reel.id}/translate",
        json={"language": "klingon"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 422  # schema validation rejects


@pytest.mark.asyncio
async def test_update_translation_persists_edits(client, db_session, make_user):
    user = await make_user(tier="PRO")
    reel, us = await _make_reel_with_script(db_session, user)
    db_session.add(ScriptTranslation(
        id=str(uuid.uuid4()), user_script_id=us.id, language="en",
        script="old", description="d", editor_instructions="e",
    ))
    await db_session.flush()
    resp = await client.patch(
        f"/api/library/{reel.id}/translation/en",
        json={"script": "edited script"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["script"] == "edited script"


@pytest.mark.asyncio
async def test_editing_translation_clears_stale(client, db_session, make_user):
    """A manual edit re-stamps source_revision so the stale banner clears."""
    user = await make_user(tier="PRO")
    reel, us = await _make_reel_with_script(db_session, user)
    db_session.add(ScriptTranslation(
        id=str(uuid.uuid4()), user_script_id=us.id, language="en",
        script="old", description="d", editor_instructions="e",
        source_revision="STALE_REV",  # mismatched → would render stale
    ))
    await db_session.flush()

    # Before edit: GET reports stale
    before = await client.get(f"/api/library/{reel.id}", headers=auth_headers(user))
    assert before.json()["translations"][0]["stale"] is True

    # Edit → re-stamps revision to current primary
    await client.patch(
        f"/api/library/{reel.id}/translation/en",
        json={"script": "synced"},
        headers=auth_headers(user),
    )
    after = await client.get(f"/api/library/{reel.id}", headers=auth_headers(user))
    assert after.json()["translations"][0]["stale"] is False


@pytest.mark.asyncio
async def test_update_translation_400_unsupported_language(client, db_session, make_user):
    user = await make_user(tier="PRO")
    reel, us = await _make_reel_with_script(db_session, user)
    resp = await client.patch(
        f"/api/library/{reel.id}/translation/klingon",
        json={"script": "x"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_translation_404_when_missing(client, db_session, make_user):
    user = await make_user(tier="PRO")
    reel, us = await _make_reel_with_script(db_session, user)
    resp = await client.patch(
        f"/api/library/{reel.id}/translation/en",
        json={"script": "x"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_reel_returns_translations_and_stale_flag(client, db_session, make_user):
    user = await make_user(tier="PRO")
    reel, us = await _make_reel_with_script(db_session, user)

    # One fresh translation (revision matches current source) + one stale
    from app.services.translator import compute_source_revision
    current_rev = compute_source_revision(AdaptationSummary(
        script=us.script, description=us.description, editor_instructions=us.editor_instructions,
    ))
    db_session.add(ScriptTranslation(
        id=str(uuid.uuid4()), user_script_id=us.id, language="en",
        script="EN", description="d", editor_instructions="e", source_revision=current_rev,
    ))
    db_session.add(ScriptTranslation(
        id=str(uuid.uuid4()), user_script_id=us.id, language="de",
        script="DE", description="d", editor_instructions="e", source_revision="STALE_REV",
    ))
    await db_session.flush()

    resp = await client.get(f"/api/library/{reel.id}", headers=auth_headers(user))
    assert resp.status_code == 200, resp.text
    translations = {t["language"]: t for t in resp.json()["translations"]}
    assert translations["en"]["stale"] is False
    assert translations["de"]["stale"] is True
