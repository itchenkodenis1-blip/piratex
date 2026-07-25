"""Phase 2 — bilingual scripts: the translation service (separate LLM iteration).

The LLM call, Redis cache and cost tracker are mocked so tests are deterministic
and offline.
"""

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.analysis import AdaptationSummary
from app.services import translator
from app.services.translator import compute_source_revision, translate_script


def _fake_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def _payload(script="Look, here's the thing.", description="Caption", editor="Frame 1: face") -> str:
    return json.dumps(
        {"script": script, "description": description, "editor_instructions": editor}
    )


def _source(script="Слушайте, вот в чём дело.", description="Описание", editor="Кадр 1: лицо"):
    return AdaptationSummary(script=script, description=description, editor_instructions=editor)


def _patches(*, anthropic_text=None, anthropic_error=None, cache_hit=None, openai_text=None):
    """Build the common mock stack for translate_script."""
    stack = ExitStack()
    cache_get = stack.enter_context(
        patch.object(translator, "cache_get", AsyncMock(return_value=cache_hit))
    )
    cache_set = stack.enter_context(
        patch.object(translator, "cache_set", AsyncMock())
    )
    stack.enter_context(patch("app.core.cost_tracker.track_anthropic", MagicMock()))

    if anthropic_error is not None:
        anth = AsyncMock(side_effect=anthropic_error)
    elif isinstance(anthropic_text, list):
        anth = AsyncMock(side_effect=[_fake_response(t) for t in anthropic_text])
    elif anthropic_text is not None:
        anth = AsyncMock(return_value=_fake_response(anthropic_text))
    else:
        anth = AsyncMock(return_value=_fake_response(_payload()))
    stack.enter_context(patch("app.core.api_retry.anthropic_create_with_retry", anth))

    openai = stack.enter_context(
        patch.object(translator, "_openai_fallback_content", AsyncMock(return_value=openai_text or _payload()))
    )
    return stack, SimpleNamespace(anthropic=anth, openai=openai, cache_get=cache_get, cache_set=cache_set)


@pytest.mark.asyncio
async def test_translate_basic_returns_translated_blocks():
    stack, m = _patches(anthropic_text=_payload(script="Translated script. ~30 seconds"))
    with stack:
        out = await translate_script(_source(), "ru", "en", api_key="test-key")
    assert isinstance(out, AdaptationSummary)
    assert out.script == "Translated script. ~30 seconds"
    assert out.description == "Caption"
    assert out.editor_instructions == "Frame 1: face"
    m.cache_set.assert_awaited_once()  # result is cached


@pytest.mark.asyncio
async def test_video_reference_prefix_preserved():
    """A leading VIDEO REFERENCE line (URL) must survive verbatim, untranslated."""
    src = _source(editor="VIDEO REFERENCE: https://insta.com/reel/xyz\n\nКадр 1: лицо")
    # LLM only ever sees/returns the body, not the URL line
    stack, m = _patches(anthropic_text=_payload(editor="Frame 1: face"))
    with stack:
        out = await translate_script(src, "ru", "en", api_key="test-key")
    assert out.editor_instructions == "VIDEO REFERENCE: https://insta.com/reel/xyz\n\nFrame 1: face"
    # ensure the URL was NOT part of what we asked the model to translate
    sent_user_prompt = m.anthropic.await_args.kwargs["messages"][0]["content"]
    assert "https://insta.com/reel/xyz" not in sent_user_prompt


@pytest.mark.asyncio
async def test_cache_hit_skips_llm():
    cached = {"script": "Cached EN", "description": "Cached desc", "editor_instructions": "Cached editor"}
    src = _source(editor="VIDEO REFERENCE: https://x.com/r\n\nКадр")
    stack, m = _patches(cache_hit=cached)
    with stack:
        out = await translate_script(src, "ru", "en", api_key="test-key")
    m.anthropic.assert_not_called()
    assert out.script == "Cached EN"
    # ref prefix re-attached even on cache hit
    assert out.editor_instructions == "VIDEO REFERENCE: https://x.com/r\n\nCached editor"


@pytest.mark.asyncio
async def test_empty_script_raises():
    stack, _ = _patches()
    with stack:
        with pytest.raises(ValueError):
            await translate_script(_source(script="   "), "ru", "en", api_key="test-key")


@pytest.mark.asyncio
async def test_json_retry_then_success():
    """First call returns non-JSON, second returns valid JSON → success."""
    stack, m = _patches(anthropic_text=["this is not json at all", _payload(script="Second try EN")])
    with stack:
        out = await translate_script(_source(), "ru", "en", api_key="test-key")
    assert out.script == "Second try EN"
    assert m.anthropic.await_count == 2


@pytest.mark.asyncio
async def test_fallback_to_openai_on_claude_error():
    stack, m = _patches(anthropic_error=RuntimeError("claude down"), openai_text=_payload(script="OpenAI EN"))
    with stack:
        out = await translate_script(_source(), "ru", "en", api_key="test-key")
    assert out.script == "OpenAI EN"
    m.openai.assert_awaited()


@pytest.mark.asyncio
async def test_profile_forbidden_words_injected_into_prompt():
    stack, m = _patches()
    with stack:
        await translate_script(
            _source(), "ru", "en",
            profile_json={"forbidden_words": "literally, game-changer"},
            api_key="test-key",
        )
    system_blocks = m.anthropic.await_args.kwargs["system"]
    joined = " ".join(b["text"] for b in system_blocks)
    assert "literally, game-changer" in joined


def test_compute_source_revision_is_stable_and_sensitive():
    a = _source()
    rev1 = compute_source_revision(a)
    rev2 = compute_source_revision(_source())  # identical content
    rev3 = compute_source_revision(_source(script="другой текст"))
    assert rev1 == rev2          # deterministic
    assert rev1 != rev3          # changes when source changes
    assert len(rev1) == 64       # sha256 hex fits VARCHAR(64)
    int(rev1, 16)                # valid hex
