"""Phase 1 — bilingual scripts: data model + schemas.

Covers:
- ScriptTranslation model persistence + (user_script_id, language) uniqueness
- UserProfile dual-language fields + second_language validation
- ScriptTranslationOut serialization shape
- SUPPORTED_LANGUAGES centralized in profile and re-exported from settings
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.library import ScriptTranslation
from app.schemas.library import ScriptTranslationOut
from app.schemas.profile import SUPPORTED_LANGUAGES, UserProfile


def _make_translation(user_script_id: str, language: str = "en") -> ScriptTranslation:
    return ScriptTranslation(
        id=str(uuid.uuid4()),
        user_script_id=user_script_id,
        language=language,
        script="Hello, here's the thing...",
        description="A short description",
        editor_instructions="Frame 1: talking head",
        original_script="Hello, here's the thing...",
        original_description="A short description",
        original_editor_instructions="Frame 1: talking head",
        source_revision="abc123",
    )


@pytest.mark.asyncio
async def test_script_translation_persists(db_session):
    usid = str(uuid.uuid4())
    tr = _make_translation(usid, "en")
    db_session.add(tr)
    await db_session.flush()

    assert tr.id is not None
    assert tr.user_script_id == usid
    assert tr.language == "en"
    assert tr.source_revision == "abc123"


@pytest.mark.asyncio
async def test_script_translation_unique_per_language(db_session):
    """Same (user_script_id, language) must be rejected; different language is fine."""
    usid = str(uuid.uuid4())
    db_session.add(_make_translation(usid, "en"))
    await db_session.flush()

    # Different language for same script — allowed
    db_session.add(_make_translation(usid, "de"))
    await db_session.flush()

    # Duplicate language for same script — rejected
    db_session.add(_make_translation(usid, "en"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


def test_user_profile_accepts_dual_language_fields():
    p = UserProfile(dual_language_enabled=True, second_language="en")
    assert p.dual_language_enabled is True
    assert p.second_language == "en"


def test_user_profile_rejects_invalid_second_language():
    # Unsupported / garbage code is silently dropped to None (matches niches behavior)
    assert UserProfile(second_language="klingon").second_language is None
    assert UserProfile(second_language="").second_language is None
    assert UserProfile(second_language=None).second_language is None


@pytest.mark.parametrize("lang", sorted(SUPPORTED_LANGUAGES))
def test_user_profile_accepts_each_supported_language(lang):
    assert UserProfile(second_language=lang).second_language == lang


def test_dual_language_defaults_are_none():
    p = UserProfile()
    assert p.dual_language_enabled is None
    assert p.second_language is None


def test_script_translation_out_serialization():
    now = datetime.utcnow()
    out = ScriptTranslationOut(
        id="t1",
        language="en",
        script="s",
        description="d",
        editor_instructions="e",
        created_at=now,
        updated_at=now,
    )
    assert out.stale is False  # defaults to not-stale
    dumped = out.model_dump()
    assert dumped["language"] == "en"
    assert set(dumped) >= {
        "id", "language", "script", "description",
        "editor_instructions", "stale", "created_at", "updated_at",
    }


def test_supported_languages_shared_between_profile_and_settings():
    from app.schemas.settings import SUPPORTED_LANGUAGES as settings_langs

    assert settings_langs is SUPPORTED_LANGUAGES
    assert {"ru", "en", "fr", "pt", "de"} <= SUPPORTED_LANGUAGES
