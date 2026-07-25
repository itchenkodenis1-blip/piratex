"""Tests for prompt composer XML wrapping."""
from app.schemas.profile import UserProfile
from app.services.prompt_composer import compose_content_prompt, compose_strategy_prompt


class TestXmlWrapping:
    def test_default_profile_no_wrapping(self):
        result = compose_content_prompt(None)
        assert "<user_about_me>" not in result
        assert "<user_tone>" not in result
        assert "<user_script_cta>" not in result

    def test_none_profile_no_wrapping(self):
        result = compose_content_prompt(UserProfile())
        assert "<user_about_me>" not in result

    def test_custom_about_me_wrapped(self):
        profile = UserProfile(about_me="Я продаю курсы")
        result = compose_content_prompt(profile)
        assert "<user_about_me>Я продаю курсы</user_about_me>" in result

    def test_preset_tone_not_wrapped(self):
        profile = UserProfile(tone="expert")
        result = compose_content_prompt(profile)
        assert "<user_tone>" not in result
        assert "confident, expert" in result

    def test_custom_tone_wrapped(self):
        profile = UserProfile(tone="мой уникальный стиль")
        result = compose_content_prompt(profile)
        assert "<user_tone>мой уникальный стиль</user_tone>" in result

    def test_custom_script_cta_wrapped(self):
        profile = UserProfile(script_cta="Жми на ссылку")
        result = compose_content_prompt(profile)
        assert "<user_script_cta>Жми на ссылку</user_script_cta>" in result

    def test_custom_forbidden_words_wrapped(self):
        profile = UserProfile(forbidden_words="спам, реклама")
        result = compose_content_prompt(profile)
        assert "<user_forbidden_words>" in result

    def test_preset_video_format_not_wrapped(self):
        profile = UserProfile(video_format="head_plus_visual")
        result = compose_content_prompt(profile)
        assert "<user_video_format>" not in result

    def test_custom_video_format_wrapped(self):
        profile = UserProfile(video_format="мой формат видео")
        result = compose_content_prompt(profile)
        assert "<user_video_format>мой формат видео</user_video_format>" in result


class TestStrategyXmlWrapping:
    def test_default_no_wrapping(self):
        result = compose_strategy_prompt(None)
        assert "<user_about_me>" not in result
        assert "<user_tone>" not in result

    def test_custom_about_me_wrapped(self):
        profile = UserProfile(about_me="Я продаю курсы")
        result = compose_strategy_prompt(profile)
        assert "<user_about_me>Я продаю курсы</user_about_me>" in result

    def test_preset_tone_not_wrapped(self):
        profile = UserProfile(tone="expert")
        result = compose_strategy_prompt(profile)
        assert "<user_tone>" not in result

    def test_custom_tone_wrapped(self):
        profile = UserProfile(tone="мой стиль")
        result = compose_strategy_prompt(profile)
        assert "<user_tone>мой стиль</user_tone>" in result


class TestPromptIntegrity:
    """Ensure prompts still contain required structural elements."""

    def test_content_prompt_has_required_sections(self):
        result = compose_content_prompt(None)
        assert "## Who the author is" in result
        assert "## Input you receive" in result
        assert "## What you must output" in result
        assert "script" in result
        assert "description" in result
        assert "editor_instructions" in result

    def test_strategy_prompt_has_required_sections(self):
        result = compose_strategy_prompt(None)
        assert "## Author context" in result
        assert "virality_breakdown" in result
        assert "hook_variants" in result

    def test_content_prompt_with_all_custom_fields(self):
        profile = UserProfile(
            about_me="Кастомное описание",
            tone="кастомный тон",
            script_cta="Кастомный CTA",
            description_cta="Кастомный CTA описания",
            forbidden_words="слово1, слово2",
            video_format="кастомный формат",
        )
        result = compose_content_prompt(profile)
        # All custom fields should be wrapped
        assert "<user_about_me>" in result
        assert "<user_tone>" in result
        assert "<user_script_cta>" in result
        assert "<user_description_cta>" in result
        assert "<user_forbidden_words>" in result
        assert "<user_video_format>" in result
        # Template structure should be intact
        assert "## Who the author is" in result
        assert "FORBIDDEN" in result
