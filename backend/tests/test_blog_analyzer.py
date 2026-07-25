"""Tests for blog_analyzer service.

Covers:
- _parse_json_response: plain JSON, code block, text before code block,
  brace extraction, nested braces, invalid JSON, empty string
- _build_synthesis_prompt: reel essences + posts analysis formatting,
  curly braces in user content (REGRESSION: was a crash bug)
- _extract_reel_essence: per-reel Haiku extraction, fallback on failure
- _analyze_posts_batch: batch post analysis, empty captions, failure handling
- _process_single_reel: download->transcribe->frames->vision pipeline (unit test)
- analyze_blog: full pipeline, photo-only fallback, partial reel failure,
  private profile, empty profile, generation failure, None values from Claude,
  invalid niches from Claude, all-reels-fail scenario
- DeepAnalyzeResult schema: edge cases (empty lists, None, long strings)
- Profile merge logic: partial PUT preserves existing fields (REGRESSION: was data loss bug)
- ContentPromptAdditions: prompt composer integration
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.profile import VALID_NICHES, DeepAnalyzeResult, UserProfile
from app.schemas.settings import UserSettingsUpdate
from app.services.blog_analyzer import (
    EmptyProfileError,
    ProfileGenerationError,
    ProfileNotFoundError,
    _analyze_posts_batch,
    _build_synthesis_prompt,
    _extract_reel_essence,
    _parse_json_response,
    analyze_blog,
)

# ── Test data ────────────────────────────────────────────────────

MOCK_PROFILE_DATA = {
    "fullName": "Test User",
    "biography": "AI & business tips",
    "followersCount": 50000,
    "latestPosts": [
        # 3 reels
        {
            "shortCode": "reel1",
            "isVideo": True,
            "videoUrl": "https://cdn.example.com/reel1.mp4",
            "caption": "How to build AI agents",
            "videoDuration": 30,
            "videoPlayCount": 10000,
            "likesCount": 500,
            "commentsCount": 20,
        },
        {
            "shortCode": "reel2",
            "isVideo": True,
            "videoUrl": "https://cdn.example.com/reel2.mp4",
            "caption": "Top 5 AI tools",
            "videoDuration": 45,
            "videoPlayCount": 20000,
            "likesCount": 1200,
            "commentsCount": 50,
        },
        {
            "shortCode": "reel3",
            "isVideo": True,
            "videoUrl": "https://cdn.example.com/reel3.mp4",
            "caption": "Cursor IDE tutorial",
            "videoDuration": 60,
            "videoPlayCount": 15000,
            "likesCount": 800,
            "commentsCount": 35,
        },
        # 2 photo posts
        {
            "shortCode": "photo1",
            "isVideo": False,
            "caption": "Check out my new course on AI",
        },
        {
            "shortCode": "photo2",
            "isVideo": False,
            "caption": "Business automation tips",
        },
    ],
}

MOCK_CLAUDE_RESPONSE = {
    "about_me": "Я — эксперт по AI и автоматизации бизнеса.",
    "tone": "expert",
    "niches": ["ai", "business"],
    "interests": ["ai-agents", "prompt-engineering", "cursor-ide", "automation", "no-code"],
    "video_format": "screencast_voiceover",
    "script_cta": "Подпишись и включи уведомления.",
    "description_cta": "Сохрани, чтобы не потерять",
    "forbidden_words": "уничтожил, убийца, революция",
    "content_prompt_additions": "Автор всегда начинает с демонстрации результата.",
}

MOCK_REEL_ESSENCE = {
    "topic": "Как создать AI-агента",
    "hook": "Вопрос: Ты знал, что AI-агенты могут автоматизировать 80% задач?",
    "key_phrases": ["давайте разберёмся", "на практике", "вот что важно"],
    "cta": "Подпишись и включи уведомления",
    "tone_markers": ["экспертный", "уверенный", "без воды"],
    "visual_format": "скринкаст + голова",
    "content_style": "обучение",
    "ending_pattern": "CTA: подпишись",
}

MOCK_POSTS_ANALYSIS = {
    "hashtag_style": "Тематические хештеги, 3-5 штук",
    "emoji_style": "Минимально, деловой стиль",
    "description_ctas": ["Сохрани себе", "Отправь другу"],
    "recurring_themes": ["AI-автоматизация", "продуктивность", "нейросети"],
    "notable_phrases": ["давайте разберёмся", "по шагам"],
    "post_structure": "Короткие абзацы, списки",
}


# ══════════════════════════════════════════════════════════════════
# 1. _parse_json_response
# ══════════════════════════════════════════════════════════════════

class TestParseJsonResponse:
    def test_plain_json(self):
        result = _parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_code_block(self):
        text = '```json\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    def test_invalid_json(self):
        result = _parse_json_response("not json")
        assert result is None

    def test_empty_string(self):
        result = _parse_json_response("")
        assert result is None

    # ── NEW: text before code block ────────────────────────────
    def test_text_before_code_block(self):
        """Claude often prepends explanatory text before the JSON code block."""
        text = "Here's the JSON based on my analysis:\n```json\n{\"about_me\": \"test\"}\n```"
        result = _parse_json_response(text)
        assert result == {"about_me": "test"}

    def test_text_before_and_after_code_block(self):
        """Claude may add text both before and after the code block."""
        text = (
            "Based on the blog analysis, here is the profile:\n\n"
            "```json\n"
            '{"about_me": "Blogger", "tone": "expert"}\n'
            "```\n\n"
            "Let me know if you need any adjustments."
        )
        result = _parse_json_response(text)
        assert result == {"about_me": "Blogger", "tone": "expert"}

    # ── NEW: brace extraction (no code block) ──────────────────
    def test_brace_extraction_no_code_block(self):
        """Fallback: extract outermost { ... } when no code block is present."""
        text = 'Here is the result: {"niches": ["ai", "tech"]} hope this helps'
        result = _parse_json_response(text)
        assert result == {"niches": ["ai", "tech"]}

    # ── NEW: nested braces ─────────────────────────────────────
    def test_nested_braces(self):
        """JSON with nested objects should be extracted correctly."""
        inner = {"about_me": "test", "meta": {"source": "instagram", "count": 3}}
        text = f"Result: {json.dumps(inner)} end"
        result = _parse_json_response(text)
        assert result == inner

    def test_deeply_nested_braces(self):
        """Deeply nested JSON objects should parse correctly."""
        data = {"a": {"b": {"c": {"d": "deep"}}}}
        text = f"Output:\n{json.dumps(data)}\nDone."
        result = _parse_json_response(text)
        assert result == data

    # ── NEW: code block without json language tag ──────────────
    def test_code_block_without_json_tag(self):
        """Code block with just ``` (no 'json' tag) should still be parsed."""
        text = '```\n{"key": "value"}\n```'
        result = _parse_json_response(text)
        assert result == {"key": "value"}

    # ── NEW: multiline JSON in code block ──────────────────────
    def test_multiline_json_in_code_block(self):
        text = (
            '```json\n'
            '{\n'
            '  "about_me": "Я блогер",\n'
            '  "niches": [\n'
            '    "ai",\n'
            '    "tech"\n'
            '  ]\n'
            '}\n'
            '```'
        )
        result = _parse_json_response(text)
        assert result["about_me"] == "Я блогер"
        assert result["niches"] == ["ai", "tech"]

    # ── NEW: JSON with unicode characters ──────────────────────
    def test_json_with_unicode(self):
        data = {"about_me": "Эксперт по AI-автоматизации"}
        result = _parse_json_response(json.dumps(data, ensure_ascii=False))
        assert result == data

    # ── NEW: broken JSON inside code block ─────────────────────
    def test_broken_json_inside_code_block(self):
        """If the JSON inside a code block is broken, fallback should also fail."""
        text = '```json\n{"key": broken}\n```'
        result = _parse_json_response(text)
        assert result is None

    # ── NEW: empty JSON object ─────────────────────────────────
    def test_empty_json_object(self):
        result = _parse_json_response("{}")
        assert result == {}


# ══════════════════════════════════════════════════════════════════
# 2. _build_synthesis_prompt
# ══════════════════════════════════════════════════════════════════

class TestBuildSynthesisPrompt:
    def test_builds_prompt_with_essences_and_posts(self):
        reel_essences = [MOCK_REEL_ESSENCE]
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, reel_essences, MOCK_POSTS_ANALYSIS)

        assert "Test User" in prompt
        assert "AI & business tips" in prompt
        assert "Reel #1" in prompt
        assert "Как создать AI-агента" in prompt
        assert "давайте разберёмся" in prompt
        assert "Тематические хештеги" in prompt

    def test_no_reels(self):
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, [], MOCK_POSTS_ANALYSIS)
        assert "No reels available for analysis." in prompt

    def test_no_posts_analysis(self):
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, [MOCK_REEL_ESSENCE], None)
        assert "Photo post analysis not available." in prompt

    # ── REGRESSION TEST — curly braces crash ─────────────────────
    def test_curly_braces_in_essence_does_not_crash(self):
        """REGRESSION: Curly braces in user content caused str.format() KeyError crash."""
        essence = {
            **MOCK_REEL_ESSENCE,
            "topic": "Use this template: {name} - {value}",
            "key_phrases": ["function() { return 42; }"],
        }
        # This MUST NOT raise KeyError
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, [essence], None)
        assert isinstance(prompt, str)
        assert "Test User" in prompt

    def test_curly_braces_in_bio(self):
        """Curly braces in the biography field should not crash."""
        profile_with_braces = {
            **MOCK_PROFILE_DATA,
            "biography": "Coding {Python} & {JS} tips",
        }
        prompt = _build_synthesis_prompt(profile_with_braces, [], None)
        assert isinstance(prompt, str)

    def test_curly_braces_in_fullname(self):
        """Curly braces in fullName should not crash."""
        profile_with_braces = {
            **MOCK_PROFILE_DATA,
            "fullName": "User {test}",
        }
        prompt = _build_synthesis_prompt(profile_with_braces, [], None)
        assert isinstance(prompt, str)

    def test_curly_braces_in_posts_analysis(self):
        """Curly braces in posts analysis fields should not crash."""
        posts = {
            **MOCK_POSTS_ANALYSIS,
            "notable_phrases": ["const obj = {key: val}"],
        }
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, [], posts)
        assert isinstance(prompt, str)

    # ── Prompt structure checks ──────────────────────────────────
    def test_prompt_contains_all_template_sections(self):
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, [MOCK_REEL_ESSENCE], MOCK_POSTS_ANALYSIS)

        assert "## Profile" in prompt
        assert "## Reel analysis" in prompt
        assert "## Task" in prompt

    def test_essence_fields_in_prompt(self):
        """All essence fields should appear when present."""
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, [MOCK_REEL_ESSENCE], None)
        assert "Topic:" in prompt
        assert "Hook:" in prompt
        assert "Key phrases:" in prompt
        assert "CTA:" in prompt
        assert "Tone:" in prompt
        assert "Visual format:" in prompt
        assert "Content style:" in prompt
        assert "Ending:" in prompt

    def test_missing_optional_profile_fields(self):
        """Profile with missing fullName / biography should use fallbacks."""
        minimal_profile = {"followersCount": 100}
        prompt = _build_synthesis_prompt(minimal_profile, [], None)
        assert "Unknown" in prompt  # fallback for missing fullName

    def test_multiple_essences(self):
        """Multiple reel essences should each have their own numbered section."""
        essences = [
            {**MOCK_REEL_ESSENCE, "topic": "Тема первого рилса"},
            {**MOCK_REEL_ESSENCE, "topic": "Тема второго рилса"},
        ]
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, essences, None)
        assert "Reel #1" in prompt
        assert "Reel #2" in prompt
        assert "Тема первого рилса" in prompt
        assert "Тема второго рилса" in prompt

    def test_reel_count_in_prompt(self):
        """The reel count should appear in the section header."""
        essences = [MOCK_REEL_ESSENCE, MOCK_REEL_ESSENCE, MOCK_REEL_ESSENCE]
        prompt = _build_synthesis_prompt(MOCK_PROFILE_DATA, essences, None)
        assert "3 reels" in prompt


# ══════════════════════════════════════════════════════════════════
# 2b. _extract_reel_essence
# ══════════════════════════════════════════════════════════════════

def _mock_claude_response(content: str):
    """Create a mock Anthropic response."""
    mock_block = MagicMock()
    mock_block.text = content
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    return mock_response


@pytest.mark.anyio
class TestExtractReelEssence:
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_successful_extraction(self, mock_ai_call):
        """Happy path: AI returns valid JSON essence."""
        mock_ai_call.return_value = json.dumps(MOCK_REEL_ESSENCE)

        reel_data = {
            "caption": "How to build AI agents",
            "transcript": "Today I'll show you how to build AI agents step by step.",
            "frame_analyses": [
                {"visual_description": "Man at desk", "scene_type": "talking_head", "screen_text": ["AI Tools"]},
            ],
            "shortcode": "reel1",
            "views": 10000,
            "likes": 500,
            "comments": 20,
        }

        result = await _extract_reel_essence(reel_data)

        assert result["topic"] == MOCK_REEL_ESSENCE["topic"]
        assert result["hook"] == MOCK_REEL_ESSENCE["hook"]
        mock_ai_call.assert_called_once()

    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_api_error_returns_fallback(self, mock_ai_call):
        """If AI call returns None, return a minimal fallback dict."""
        mock_ai_call.return_value = None

        reel_data = {
            "caption": "Test caption for fallback",
            "transcript": "",
            "frame_analyses": [],
            "shortcode": "reel_fail",
        }

        result = await _extract_reel_essence(reel_data)

        assert result["topic"] == "Test caption for fallback"[:100]
        assert result["hook"] == ""
        assert result["key_phrases"] == []
        assert result["visual_format"] == "unknown"

    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_json_parse_failure_returns_fallback(self, mock_ai_call):
        """If AI returns invalid JSON, return fallback."""
        mock_ai_call.return_value = "not json at all"

        reel_data = {
            "caption": "Some caption",
            "transcript": "Some transcript",
            "frame_analyses": [],
            "shortcode": "reel_bad_json",
        }

        result = await _extract_reel_essence(reel_data)
        assert result["topic"] == "Some caption"
        assert result["visual_format"] == "unknown"

    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_empty_reel_data(self, mock_ai_call):
        """Reel with empty fields should not crash."""
        mock_ai_call.return_value = json.dumps(MOCK_REEL_ESSENCE)

        reel_data = {
            "caption": "",
            "transcript": "",
            "frame_analyses": [],
            "shortcode": "empty_reel",
        }

        result = await _extract_reel_essence(reel_data)
        assert isinstance(result, dict)

    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_long_transcript_truncated(self, mock_ai_call):
        """Transcript longer than 1500 chars should be truncated in the prompt."""
        mock_ai_call.return_value = json.dumps(MOCK_REEL_ESSENCE)

        reel_data = {
            "caption": "Test",
            "transcript": "x" * 3000,
            "frame_analyses": [],
            "shortcode": "long_reel",
        }

        await _extract_reel_essence(reel_data)

        # Verify the prompt was called — the transcript in prompt should be truncated
        call_args = mock_ai_call.call_args
        prompt_text = call_args.args[0] if call_args.args else call_args.kwargs.get("prompt", "")
        # The transcript in the prompt should be <= 1500 chars (plus some template text around it)
        assert "x" * 1501 not in prompt_text


# ══════════════════════════════════════════════════════════════════
# 2c. _analyze_posts_batch
# ══════════════════════════════════════════════════════════════════

@pytest.mark.anyio
class TestAnalyzePostsBatch:
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_successful_batch_analysis(self, mock_ai_call):
        """Happy path: AI returns valid JSON analysis."""
        mock_ai_call.return_value = json.dumps(MOCK_POSTS_ANALYSIS)

        captions = ["Check out my course", "Business tips #ai"]
        result = await _analyze_posts_batch(captions)

        assert result is not None
        assert result["hashtag_style"] == MOCK_POSTS_ANALYSIS["hashtag_style"]
        mock_ai_call.assert_called_once()

    async def test_empty_captions_returns_none(self):
        """Empty captions list should return None without calling AI."""
        result = await _analyze_posts_batch([])
        assert result is None

    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_api_error_returns_none(self, mock_ai_call):
        """If AI call returns None, return None (posts analysis is non-critical)."""
        mock_ai_call.return_value = None

        result = await _analyze_posts_batch(["Some caption"])
        assert result is None

    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_json_parse_failure_returns_none(self, mock_ai_call):
        """If AI returns invalid JSON, return None."""
        mock_ai_call.return_value = "broken response"

        result = await _analyze_posts_batch(["Some caption"])
        assert result is None

    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_long_captions_truncated(self, mock_ai_call):
        """Each caption should be truncated to 500 chars, total to 4000 chars."""
        mock_ai_call.return_value = json.dumps(MOCK_POSTS_ANALYSIS)

        # 20 captions of 400 chars each = 8000 total, should be truncated
        captions = ["x" * 400 for _ in range(20)]
        result = await _analyze_posts_batch(captions)

        assert result is not None
        # Check the prompt doesn't contain all 20 captions
        call_args = mock_ai_call.call_args
        prompt_text = call_args.args[0] if call_args.args else call_args.kwargs.get("prompt", "")
        # Total should be capped at ~4000 chars of caption content
        assert prompt_text.count("Post #") < 20


# ══════════════════════════════════════════════════════════════════
# 3. _process_single_reel (unit tests)
# ══════════════════════════════════════════════════════════════════

def _make_reel_post(shortcode="test_reel", video_url="https://cdn.example.com/v.mp4",
                    caption="Test caption", duration=30):
    return {
        "shortCode": shortcode,
        "isVideo": True,
        "videoUrl": video_url,
        "caption": caption,
        "videoDuration": duration,
        "videoPlayCount": 10000,
        "likesCount": 500,
        "commentsCount": 20,
    }


@pytest.mark.anyio
class TestProcessSingleReel:
    """Unit tests for the download->transcribe->frames->vision pipeline.

    Note: _process_single_reel uses lazy imports inside the function body,
    so we must patch at the SOURCE module paths, not at blog_analyzer level.
    """

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.vision_analyzer.analyze_frames")
    @patch("app.services.frame_extractor.extract_frames")
    @patch("app.services.transcriber.transcribe")
    @patch("app.services.audio.extract_audio")
    @patch("app.services.scraper._download.download_video_to_local")
    async def test_full_reel_pipeline(
        self, mock_download, mock_audio, mock_transcribe,
        mock_frames, mock_vision, mock_progress,
    ):
        """Happy path: all stages succeed."""
        import asyncio
        from app.services.blog_analyzer import _process_single_reel

        mock_progress.broadcast = AsyncMock()
        mock_download.return_value = Path("/tmp/test_video.mp4")
        mock_audio.return_value = Path("/tmp/test_audio.wav")

        # Mock transcript segments
        segment = MagicMock()
        segment.text = "Hello world"
        mock_transcribe.return_value = [segment]

        # Mock frame extraction
        mock_frames.return_value = [Path("/tmp/frame1.jpg"), Path("/tmp/frame2.jpg")]

        # Mock vision analysis
        frame_analysis = MagicMock()
        frame_analysis.visual_description = "Person at desk"
        frame_analysis.scene_type = MagicMock(value="talking_head")
        frame_analysis.screen_text = ["AI Tools"]
        mock_vision.return_value = [frame_analysis]

        semaphore = asyncio.Semaphore(1)
        post = _make_reel_post()

        result = await _process_single_reel(post, 0, 1, "test-id", semaphore)

        assert result is not None
        assert result["caption"] == "Test caption"
        assert result["transcript"] == "Hello world"
        assert len(result["frame_analyses"]) == 1
        assert result["frame_analyses"][0]["visual_description"] == "Person at desk"
        assert result["frame_analyses"][0]["scene_type"] == "talking_head"
        assert result["shortcode"] == "test_reel"
        assert result["views"] == 10000
        assert result["likes"] == 500
        assert result["comments"] == 20

        mock_download.assert_called_once()
        mock_audio.assert_called_once()
        mock_transcribe.assert_called_once()

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.frame_extractor.extract_frames")
    @patch("app.services.audio.extract_audio")
    @patch("app.services.scraper._download.download_video_to_local")
    async def test_reel_no_audio(self, mock_download, mock_audio, mock_frames, mock_progress):
        """When audio extraction returns None, transcript should be empty."""
        import asyncio
        from app.services.blog_analyzer import _process_single_reel

        mock_progress.broadcast = AsyncMock()
        mock_download.return_value = Path("/tmp/test_video.mp4")
        mock_audio.return_value = None  # no audio
        mock_frames.return_value = []

        semaphore = asyncio.Semaphore(1)
        post = _make_reel_post()

        result = await _process_single_reel(post, 0, 1, "test-id", semaphore)

        assert result is not None
        assert result["transcript"] == ""
        assert result["frame_analyses"] == []

    @patch("app.services.blog_analyzer.progress_tracker")
    async def test_reel_no_video_url_returns_caption_only(self, mock_progress):
        """Reel with no videoUrl (and scraping fails) should return caption-only result."""
        import asyncio
        import sys
        from app.services.blog_analyzer import _process_single_reel

        mock_progress.broadcast = AsyncMock()

        post = {
            "shortCode": "no_video",
            "isVideo": True,
            "caption": "Caption only reel",
            "videoDuration": 30,
        }

        semaphore = asyncio.Semaphore(1)

        # The lazy import `from app.services.scraper._instagram import _fetch_instagram`
        # can't be resolved in test env (redis dependency). Inject a mock module.
        mock_instagram_module = MagicMock()
        mock_instagram_module._fetch_instagram = AsyncMock(return_value={})
        saved = sys.modules.get("app.services.scraper._instagram")
        sys.modules["app.services.scraper._instagram"] = mock_instagram_module
        try:
            result = await _process_single_reel(post, 0, 1, "test-id", semaphore)
        finally:
            if saved is not None:
                sys.modules["app.services.scraper._instagram"] = saved
            else:
                sys.modules.pop("app.services.scraper._instagram", None)

        assert result is not None
        assert result["caption"] == "Caption only reel"
        assert result["transcript"] == ""
        assert result["frame_analyses"] == []

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.scraper._download.download_video_to_local")
    async def test_reel_download_failure_graceful(self, mock_download, mock_progress):
        """If download raises an exception, _process_single_reel should return a fallback result (not None)."""
        import asyncio
        from app.services.blog_analyzer import _process_single_reel

        mock_progress.broadcast = AsyncMock()
        mock_download.side_effect = Exception("Download failed: 403 Forbidden")

        semaphore = asyncio.Semaphore(1)
        post = _make_reel_post()

        result = await _process_single_reel(post, 0, 1, "test-id", semaphore)

        # The except block in _process_single_reel returns a fallback dict
        assert result is not None
        assert result["caption"] == "Test caption"
        assert result["transcript"] == ""

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.frame_extractor.extract_frames")
    @patch("app.services.transcriber.transcribe")
    @patch("app.services.audio.extract_audio")
    @patch("app.services.scraper._download.download_video_to_local")
    async def test_reel_transcription_failure_continues(
        self, mock_download, mock_audio, mock_transcribe, mock_frames, mock_progress,
    ):
        """If transcription fails, the pipeline should continue with empty transcript."""
        import asyncio
        from app.services.blog_analyzer import _process_single_reel

        mock_progress.broadcast = AsyncMock()
        mock_download.return_value = Path("/tmp/test_video.mp4")
        mock_audio.return_value = Path("/tmp/test_audio.wav")
        mock_transcribe.side_effect = Exception("Whisper API error")
        mock_frames.return_value = []

        semaphore = asyncio.Semaphore(1)
        post = _make_reel_post()

        result = await _process_single_reel(post, 0, 1, "test-id", semaphore)

        assert result is not None
        assert result["transcript"] == ""

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.vision_analyzer.analyze_frames")
    @patch("app.services.frame_extractor.extract_frames")
    @patch("app.services.transcriber.transcribe")
    @patch("app.services.audio.extract_audio")
    @patch("app.services.scraper._download.download_video_to_local")
    async def test_reel_vision_failure_continues(
        self, mock_download, mock_audio, mock_transcribe,
        mock_frames, mock_vision, mock_progress,
    ):
        """If vision analysis fails, the pipeline should return with empty frame_analyses."""
        import asyncio
        from app.services.blog_analyzer import _process_single_reel

        mock_progress.broadcast = AsyncMock()
        mock_download.return_value = Path("/tmp/test_video.mp4")
        mock_audio.return_value = Path("/tmp/test_audio.wav")

        segment = MagicMock()
        segment.text = "Some words"
        mock_transcribe.return_value = [segment]

        mock_frames.return_value = [Path("/tmp/frame1.jpg")]
        mock_vision.side_effect = Exception("OpenAI vision API error")

        semaphore = asyncio.Semaphore(1)
        post = _make_reel_post()

        result = await _process_single_reel(post, 0, 1, "test-id", semaphore)

        assert result is not None
        assert result["transcript"] == "Some words"
        assert result["frame_analyses"] == []


# ══════════════════════════════════════════════════════════════════
# 4. Integration tests (with mocks) — analyze_blog
# ══════════════════════════════════════════════════════════════════

@pytest.mark.anyio
class TestAnalyzeBlogFullPipeline:
    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_full_pipeline(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()

        # Mock reel processing
        mock_process_reel.side_effect = [
            {"caption": "AI agents", "transcript": "How to build AI agents", "frame_analyses": [], "shortcode": "r1"},
            {"caption": "AI tools", "transcript": "Top 5 AI tools", "frame_analyses": [], "shortcode": "r2"},
            {"caption": "Cursor IDE", "transcript": "Cursor tutorial", "frame_analyses": [], "shortcode": "r3"},
        ]

        # Mock essence extraction
        mock_extract_essence.return_value = MOCK_REEL_ESSENCE

        # Mock posts analysis
        mock_analyze_posts.return_value = MOCK_POSTS_ANALYSIS

        # Mock synthesis via _ai_call_with_fallback
        mock_ai_call.return_value = json.dumps(MOCK_CLAUDE_RESPONSE)

        result = await analyze_blog("testuser", "test-analysis-id")

        assert isinstance(result, DeepAnalyzeResult)
        assert result.about_me == MOCK_CLAUDE_RESPONSE["about_me"]
        assert result.tone == "expert"
        assert result.niches == ["ai", "business"]
        assert len(result.interests) == 5
        assert result.content_prompt_additions is not None

        mock_scrape.assert_called_once_with("testuser")
        # Essence extracted for each reel
        assert mock_extract_essence.call_count == 3
        # Posts batch analyzed once
        mock_analyze_posts.assert_called_once()
        # Final synthesis call (1 attempt via _ai_call_with_fallback)
        assert mock_ai_call.call_count == 1


@pytest.mark.anyio
class TestAnalyzeBlogNoReels:
    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_photo_only_fallback(
        self, mock_ai_call, mock_scrape, mock_analyze_posts, mock_progress,
    ):
        # Profile with only photo posts (no videoUrl, not isVideo)
        photo_only_profile = {
            "fullName": "Photo User",
            "biography": "Photographer",
            "followersCount": 10000,
            "latestPosts": [
                {"shortCode": "p1", "isVideo": False, "caption": "Beautiful sunset"},
                {"shortCode": "p2", "isVideo": False, "caption": "City lights"},
            ],
        }
        mock_scrape.return_value = photo_only_profile
        mock_progress.broadcast = AsyncMock()
        mock_analyze_posts.return_value = MOCK_POSTS_ANALYSIS

        mock_ai_call.return_value = json.dumps({
            **MOCK_CLAUDE_RESPONSE,
            "about_me": "Фотограф",
            "niches": ["lifestyle"],
        })

        result = await analyze_blog("photouser", "test-id")

        assert isinstance(result, DeepAnalyzeResult)
        assert result.about_me == "Фотограф"


@pytest.mark.anyio
class TestAnalyzeBlogPartialFailure:
    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_partial_failure(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()

        # First reel fails (returns None), others succeed
        mock_process_reel.side_effect = [
            None,  # failed reel
            {"caption": "AI tools", "transcript": "Top 5 tools", "frame_analyses": [], "shortcode": "r2"},
            {"caption": "Cursor", "transcript": "Cursor tutorial", "frame_analyses": [], "shortcode": "r3"},
        ]

        mock_extract_essence.return_value = MOCK_REEL_ESSENCE
        mock_analyze_posts.return_value = MOCK_POSTS_ANALYSIS

        mock_ai_call.return_value = json.dumps(MOCK_CLAUDE_RESPONSE)

        result = await analyze_blog("testuser", "test-id")
        assert isinstance(result, DeepAnalyzeResult)
        # Only 2 reels succeeded, so essence extraction called 2 times
        assert mock_extract_essence.call_count == 2


@pytest.mark.anyio
class TestAnalyzeBlogPrivateProfile:
    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._scrape_profile")
    async def test_private_profile(self, mock_scrape, mock_progress):
        mock_scrape.return_value = None
        mock_progress.broadcast = AsyncMock()

        with pytest.raises(ProfileNotFoundError):
            await analyze_blog("private_user", "test-id")


@pytest.mark.anyio
class TestAnalyzeBlogEmptyProfile:
    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._scrape_profile")
    async def test_empty_profile(self, mock_scrape, mock_progress):
        mock_scrape.return_value = {
            "fullName": "Empty User",
            "biography": "",
            "followersCount": 0,
            "latestPosts": [],
        }
        mock_progress.broadcast = AsyncMock()

        with pytest.raises(EmptyProfileError):
            await analyze_blog("empty_user", "test-id")


@pytest.mark.anyio
class TestAnalyzeBlogGenerationFailure:
    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_generation_failure(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()
        mock_process_reel.return_value = {"caption": "test", "transcript": "test", "frame_analyses": []}
        mock_extract_essence.return_value = MOCK_REEL_ESSENCE
        mock_analyze_posts.return_value = None

        # Return invalid JSON on all attempts (both Claude and GPT fail to produce valid JSON)
        mock_ai_call.return_value = "not json at all"

        with pytest.raises(ProfileGenerationError):
            await analyze_blog("testuser", "test-id")

        assert mock_ai_call.call_count == 2  # 2 synthesis attempts


# ── NEW: analyze_blog with None values from Claude ─────────────

@pytest.mark.anyio
class TestAnalyzeBlogNoneValuesFromClaude:
    """Test that analyze_blog handles None/missing values in Claude's JSON response."""

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_none_values_produce_defaults(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        """AI returns JSON with None/missing fields -- defaults should be applied."""
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()
        mock_process_reel.return_value = {
            "caption": "test", "transcript": "test", "frame_analyses": [], "shortcode": "r1",
        }
        mock_extract_essence.return_value = MOCK_REEL_ESSENCE
        mock_analyze_posts.return_value = None

        sparse_response = {
            "about_me": None, "tone": None, "niches": None, "interests": None,
            "video_format": None, "script_cta": None, "description_cta": None,
            "forbidden_words": None, "content_prompt_additions": None,
        }
        mock_ai_call.return_value = json.dumps(sparse_response)

        result = await analyze_blog("testuser", "test-id")

        assert isinstance(result, DeepAnalyzeResult)
        assert result.about_me == ""
        assert result.tone == "conversational"
        assert result.niches == []
        assert result.interests == []
        assert result.video_format == "head_plus_visual"
        assert result.script_cta == ""
        assert result.description_cta == ""
        assert result.forbidden_words == ""
        assert result.content_prompt_additions is None

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_missing_keys_produce_defaults(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        """AI response with completely missing keys should still produce valid result."""
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()
        mock_process_reel.return_value = {
            "caption": "test", "transcript": "test", "frame_analyses": [], "shortcode": "r1",
        }
        mock_extract_essence.return_value = MOCK_REEL_ESSENCE
        mock_analyze_posts.return_value = None

        mock_ai_call.return_value = json.dumps({"about_me": "I am a blogger"})

        result = await analyze_blog("testuser", "test-id")

        assert isinstance(result, DeepAnalyzeResult)
        assert result.about_me == "I am a blogger"
        assert result.tone == "conversational"
        assert result.niches == []
        assert result.interests == []


# ── NEW: analyze_blog with invalid niches from Claude ──────────

@pytest.mark.anyio
class TestAnalyzeBlogInvalidNichesFromClaude:
    """Test that invalid niche values from Claude are filtered out."""

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_invalid_niches_filtered(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()
        mock_process_reel.return_value = {
            "caption": "test", "transcript": "test", "frame_analyses": [], "shortcode": "r1",
        }
        mock_extract_essence.return_value = MOCK_REEL_ESSENCE
        mock_analyze_posts.return_value = None

        response_with_bad_niches = {
            **MOCK_CLAUDE_RESPONSE,
            "niches": ["artificial-intelligence", "startup", "ai"],
        }
        mock_ai_call.return_value = json.dumps(response_with_bad_niches)

        result = await analyze_blog("testuser", "test-id")
        assert result.niches == ["ai"]

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_all_niches_invalid(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        """If ALL niches from AI are invalid, result should have empty niches list."""
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()
        mock_process_reel.return_value = {
            "caption": "test", "transcript": "test", "frame_analyses": [], "shortcode": "r1",
        }
        mock_extract_essence.return_value = MOCK_REEL_ESSENCE
        mock_analyze_posts.return_value = None

        mock_ai_call.return_value = json.dumps({
            **MOCK_CLAUDE_RESPONSE,
            "niches": ["blogging", "content-creation", "social-media"],
        })

        result = await analyze_blog("testuser", "test-id")
        assert result.niches == []

    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_niches_truncated_to_three(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        """AI returns more than 3 valid niches -- only first 3 should survive."""
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()
        mock_process_reel.return_value = {
            "caption": "test", "transcript": "test", "frame_analyses": [], "shortcode": "r1",
        }
        mock_extract_essence.return_value = MOCK_REEL_ESSENCE
        mock_analyze_posts.return_value = None

        mock_ai_call.return_value = json.dumps({
            **MOCK_CLAUDE_RESPONSE,
            "niches": ["ai", "tech", "business", "marketing", "ecommerce"],
        })

        result = await analyze_blog("testuser", "test-id")
        assert len(result.niches) == 3
        assert result.niches == ["ai", "tech", "business"]


# ── NEW: analyze_blog — all reels fail ─────────────────────────

@pytest.mark.anyio
class TestAnalyzeBlogAllReelsFail:
    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_all_reels_return_none(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_analyze_posts, mock_progress,
    ):
        """All reels return None from _process_single_reel; analysis should still proceed with photo captions."""
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()

        mock_process_reel.return_value = None  # all reels fail
        mock_analyze_posts.return_value = MOCK_POSTS_ANALYSIS

        mock_ai_call.return_value = json.dumps(MOCK_CLAUDE_RESPONSE)

        result = await analyze_blog("testuser", "test-id")
        assert isinstance(result, DeepAnalyzeResult)


# ── NEW: analyze_blog — Claude API raises on first attempt, succeeds on retry ──

@pytest.mark.anyio
class TestAnalyzeBlogRetryOnApiError:
    @patch("app.services.blog_analyzer.progress_tracker")
    @patch("app.services.blog_analyzer._analyze_posts_batch")
    @patch("app.services.blog_analyzer._extract_reel_essence")
    @patch("app.services.blog_analyzer._process_single_reel")
    @patch("app.services.blog_analyzer._scrape_profile")
    @patch("app.services.blog_analyzer._ai_call_with_fallback")
    async def test_retry_on_api_exception(
        self, mock_ai_call, mock_scrape, mock_process_reel,
        mock_extract_essence, mock_analyze_posts, mock_progress,
    ):
        """If first synthesis attempt returns None, second attempt should still succeed."""
        mock_scrape.return_value = MOCK_PROFILE_DATA
        mock_progress.broadcast = AsyncMock()
        mock_process_reel.return_value = {
            "caption": "test", "transcript": "test", "frame_analyses": [], "shortcode": "r1",
        }
        mock_extract_essence.return_value = MOCK_REEL_ESSENCE
        mock_analyze_posts.return_value = None

        # First synthesis call returns None (both providers failed), second succeeds
        mock_ai_call.side_effect = [
            None,
            json.dumps(MOCK_CLAUDE_RESPONSE),
        ]

        result = await analyze_blog("testuser", "test-id")
        assert isinstance(result, DeepAnalyzeResult)
        assert mock_ai_call.call_count == 2


# ══════════════════════════════════════════════════════════════════
# 5. DeepAnalyzeResult schema edge cases
# ══════════════════════════════════════════════════════════════════

class TestDeepAnalyzeResultSchema:
    def test_valid_creation(self):
        result = DeepAnalyzeResult(
            about_me="Test blogger",
            tone="expert",
            niches=["ai"],
            interests=["prompt-engineering"],
            video_format="talking_head_only",
            script_cta="Subscribe!",
            description_cta="Save this",
            forbidden_words="cringe, hack",
            content_prompt_additions="Always starts with a question",
        )
        assert result.about_me == "Test blogger"
        assert result.niches == ["ai"]

    def test_empty_lists(self):
        result = DeepAnalyzeResult(
            about_me="Test",
            tone="calm",
            niches=[],
            interests=[],
            video_format="screencast_voiceover",
            script_cta="",
            description_cta="",
            forbidden_words="",
        )
        assert result.niches == []
        assert result.interests == []

    def test_none_content_prompt_additions(self):
        result = DeepAnalyzeResult(
            about_me="Test",
            tone="conversational",
            niches=[],
            interests=[],
            video_format="head_plus_visual",
            script_cta="",
            description_cta="",
            forbidden_words="",
            content_prompt_additions=None,
        )
        assert result.content_prompt_additions is None

    def test_very_long_about_me(self):
        """DeepAnalyzeResult has no max_length — should accept any string length."""
        long_text = "x" * 5000
        result = DeepAnalyzeResult(
            about_me=long_text,
            tone="expert",
            niches=["ai"],
            interests=["test"],
            video_format="talking_head_only",
            script_cta="",
            description_cta="",
            forbidden_words="",
        )
        assert len(result.about_me) == 5000

    def test_many_interests(self):
        """DeepAnalyzeResult should accept many interests (no limit at schema level)."""
        interests = [f"topic-{i}" for i in range(30)]
        result = DeepAnalyzeResult(
            about_me="Test",
            tone="expert",
            niches=["tech"],
            interests=interests,
            video_format="screencast_voiceover",
            script_cta="",
            description_cta="",
            forbidden_words="",
        )
        assert len(result.interests) == 30

    def test_model_dump_roundtrip(self):
        """model_dump + reconstruct should produce the same object."""
        original = DeepAnalyzeResult(
            about_me="Тест блогер",
            tone="custom:sarcastic-expert",
            niches=["ai", "business"],
            interests=["prompt-engineering", "cursor-ide"],
            video_format="custom:split-screen",
            script_cta="Лайк и подписка",
            description_cta="Сохрани себе",
            forbidden_words="хайп, кринж",
            content_prompt_additions="Uses code examples",
        )
        data = original.model_dump()
        rebuilt = DeepAnalyzeResult(**data)
        assert rebuilt == original

    def test_custom_tone_and_video_format(self):
        """Custom tone and video_format strings (custom:...) should be accepted."""
        result = DeepAnalyzeResult(
            about_me="Test",
            tone="custom:ironic and dry",
            niches=[],
            interests=[],
            video_format="custom:b-roll montage with voiceover",
            script_cta="",
            description_cta="",
            forbidden_words="",
        )
        assert result.tone.startswith("custom:")
        assert result.video_format.startswith("custom:")


# ══════════════════════════════════════════════════════════════════
# 6. UserProfile schema — niche and interest validation
# ══════════════════════════════════════════════════════════════════

class TestUserProfileNicheValidation:
    def test_valid_niches_accepted(self):
        p = UserProfile(niches=["ai", "tech", "business"])
        assert p.niches == ["ai", "tech", "business"]

    def test_invalid_niches_filtered(self):
        p = UserProfile(niches=["ai", "invalid-niche", "tech"])
        assert p.niches == ["ai", "tech"]

    def test_all_invalid_niches_become_none(self):
        p = UserProfile(niches=["blogging", "content", "social-media"])
        assert p.niches is None

    def test_niches_truncated_to_three(self):
        p = UserProfile(niches=["ai", "tech", "business", "marketing", "crypto"])
        assert len(p.niches) == 3
        assert p.niches == ["ai", "tech", "business"]

    def test_niches_none_is_accepted(self):
        p = UserProfile(niches=None)
        assert p.niches is None

    def test_niches_empty_list_becomes_none(self):
        p = UserProfile(niches=[])
        assert p.niches is None

    def test_niches_non_string_values_filtered(self):
        p = UserProfile(niches=["ai", 123, None, "tech"])
        assert p.niches == ["ai", "tech"]

    def test_niches_not_a_list_becomes_none(self):
        p = UserProfile(niches="ai")  # type: ignore
        assert p.niches is None


class TestUserProfileInterestValidation:
    def test_valid_interests(self):
        p = UserProfile(interests=["prompt-engineering", "cursor-ide", "ai-agents"])
        assert len(p.interests) == 3

    def test_interests_truncated_to_twenty(self):
        interests = [f"topic-{i}" for i in range(25)]
        p = UserProfile(interests=interests)
        assert len(p.interests) == 20

    def test_empty_string_interest_filtered(self):
        p = UserProfile(interests=["ai", "", "tech"])
        assert p.interests == ["ai", "tech"]

    def test_very_long_interest_filtered(self):
        p = UserProfile(interests=["ai", "x" * 51, "tech"])
        assert p.interests == ["ai", "tech"]

    def test_interests_none_is_accepted(self):
        p = UserProfile(interests=None)
        assert p.interests is None

    def test_interests_empty_list_becomes_none(self):
        p = UserProfile(interests=[])
        assert p.interests is None


class TestUserProfileRadarValidation:
    def test_valid_radar_mode(self):
        p = UserProfile(radar_mode="instant")
        assert p.radar_mode == "instant"

    def test_invalid_radar_mode_becomes_none(self):
        p = UserProfile(radar_mode="hourly")
        assert p.radar_mode is None

    def test_radar_min_x_factor_clamped_low(self):
        p = UserProfile(radar_min_x_factor=0.5)
        assert p.radar_min_x_factor == 2.0

    def test_radar_min_x_factor_clamped_high(self):
        p = UserProfile(radar_min_x_factor=50.0)
        assert p.radar_min_x_factor == 20.0

    def test_radar_niches_only_valid(self):
        p = UserProfile(radar_niches=["ai", "invalid", "tech"])
        assert p.radar_niches == ["ai", "tech"]

    def test_radar_niches_max_five(self):
        p = UserProfile(radar_niches=["ai", "tech", "business", "marketing", "crypto", "finance"])
        assert len(p.radar_niches) == 5


# ══════════════════════════════════════════════════════════════════
# 7. Profile merge logic (PUT /settings partial update)
# ══════════════════════════════════════════════════════════════════

class TestProfileMergeLogic:
    """Test the profile merge logic from settings.py update_settings endpoint.

    REGRESSION: Previously, PUT /settings with partial profile would overwrite the
    entire profile_json, losing fields not present in the update. The fix was to
    merge incoming fields with existing fields.

    We test the merge logic in isolation (the dict merge pattern used in the endpoint).
    """

    def test_partial_update_preserves_existing_fields(self):
        """Updating only `tone` should preserve about_me, niches, etc."""
        existing = {
            "about_me": "I am a blogger",
            "tone": "conversational",
            "niches": ["ai", "tech"],
            "interests": ["prompt-engineering"],
            "script_cta": "Subscribe!",
        }

        # User updates only tone
        update_profile = UserProfile(tone="expert")
        new_fields = update_profile.model_dump(exclude_none=True)

        # Simulate the merge logic from settings.py
        merged = {**existing}
        merged.update(new_fields)

        assert merged["about_me"] == "I am a blogger"  # PRESERVED
        assert merged["tone"] == "expert"  # UPDATED
        assert merged["niches"] == ["ai", "tech"]  # PRESERVED
        assert merged["interests"] == ["prompt-engineering"]  # PRESERVED
        assert merged["script_cta"] == "Subscribe!"  # PRESERVED

    def test_partial_update_niches_only(self):
        """Updating only niches should preserve all other fields."""
        existing = {
            "about_me": "Blogger about AI",
            "tone": "expert",
            "niches": ["tech"],
            "interests": ["ai-agents", "no-code"],
            "video_format": "screencast_voiceover",
        }

        update_profile = UserProfile(niches=["ai", "business"])
        new_fields = update_profile.model_dump(exclude_none=True)

        merged = {**existing}
        merged.update(new_fields)

        assert merged["about_me"] == "Blogger about AI"  # PRESERVED
        assert merged["tone"] == "expert"  # PRESERVED
        assert merged["niches"] == ["ai", "business"]  # UPDATED
        assert merged["interests"] == ["ai-agents", "no-code"]  # PRESERVED
        assert merged["video_format"] == "screencast_voiceover"  # PRESERVED

    def test_full_update_overwrites_all(self):
        """Sending all fields should overwrite everything."""
        existing = {
            "about_me": "Old bio",
            "tone": "calm",
            "niches": ["lifestyle"],
        }

        update_profile = UserProfile(
            about_me="New bio",
            tone="expert",
            niches=["ai"],
            interests=["prompt-engineering"],
        )
        new_fields = update_profile.model_dump(exclude_none=True)

        merged = {**existing}
        merged.update(new_fields)

        assert merged["about_me"] == "New bio"
        assert merged["tone"] == "expert"
        assert merged["niches"] == ["ai"]
        assert merged["interests"] == ["prompt-engineering"]

    def test_empty_existing_profile_gets_new_fields(self):
        """If existing profile is empty, new fields should be added."""
        existing = {}

        update_profile = UserProfile(about_me="New user", tone="conversational")
        new_fields = update_profile.model_dump(exclude_none=True)

        merged = {**existing}
        merged.update(new_fields)

        assert merged["about_me"] == "New user"
        assert merged["tone"] == "conversational"

    def test_update_with_no_fields_preserves_everything(self):
        """Updating with an empty profile (all None) should preserve everything."""
        existing = {
            "about_me": "Existing bio",
            "tone": "expert",
            "niches": ["ai"],
        }

        update_profile = UserProfile()  # All fields None
        new_fields = update_profile.model_dump(exclude_none=True)
        assert new_fields == {}  # Nothing to update

        merged = {**existing}
        merged.update(new_fields)

        assert merged == existing  # Everything preserved

    def test_model_dump_exclude_none_behavior(self):
        """Verify that model_dump(exclude_none=True) only includes set fields."""
        profile = UserProfile(about_me="Test", tone="expert")
        dumped = profile.model_dump(exclude_none=True)
        assert "about_me" in dumped
        assert "tone" in dumped
        assert "niches" not in dumped
        assert "interests" not in dumped
        assert "script_cta" not in dumped

    def test_update_settings_schema_accepts_partial_profile(self):
        """UserSettingsUpdate should accept a partial profile."""
        update = UserSettingsUpdate(
            profile=UserProfile(tone="energetic"),
        )
        assert update.profile is not None
        assert update.profile.tone == "energetic"
        assert update.profile.about_me is None  # not specified


# ══════════════════════════════════════════════════════════════════
# 8. ContentPromptAdditions in prompt_composer
# ══════════════════════════════════════════════════════════════════

class TestContentPromptAdditions:
    def test_content_prompt_additions_in_prompt(self):
        from app.services.prompt_composer import compose_content_prompt

        profile = UserProfile(
            about_me="Я — блогер",
            content_prompt_additions="Автор всегда начинает с личной истории",
        )
        result = compose_content_prompt(profile)
        assert "Additional author style instructions" in result
        assert "Автор всегда начинает с личной истории" in result
        assert "<user_content_prompt_additions>" in result

    def test_no_additions_no_section(self):
        from app.services.prompt_composer import compose_content_prompt

        profile = UserProfile(about_me="Я — блогер")
        result = compose_content_prompt(profile)
        assert "Дополнительные инструкции по стилю автора" not in result
