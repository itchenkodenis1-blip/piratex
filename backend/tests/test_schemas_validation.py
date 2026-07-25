"""Tests for input validation on schemas."""
import pytest
from pydantic import ValidationError

from app.schemas.profile import UserProfile
from app.schemas.settings import UserSettingsUpdate


class TestUserProfile:
    def test_about_me_within_limit(self):
        p = UserProfile(about_me="x" * 2000)
        assert len(p.about_me) == 2000

    def test_about_me_exceeds_limit(self):
        with pytest.raises(ValidationError):
            UserProfile(about_me="x" * 2001)

    def test_tone_within_limit(self):
        p = UserProfile(tone="x" * 500)
        assert len(p.tone) == 500

    def test_tone_exceeds_limit(self):
        with pytest.raises(ValidationError):
            UserProfile(tone="x" * 501)

    def test_script_cta_exceeds_limit(self):
        with pytest.raises(ValidationError):
            UserProfile(script_cta="x" * 201)

    def test_description_cta_exceeds_limit(self):
        with pytest.raises(ValidationError):
            UserProfile(description_cta="x" * 201)

    def test_forbidden_words_exceeds_limit(self):
        with pytest.raises(ValidationError):
            UserProfile(forbidden_words="x" * 1001)

    def test_video_format_exceeds_limit(self):
        with pytest.raises(ValidationError):
            UserProfile(video_format="x" * 301)

    def test_empty_string_becomes_none(self):
        p = UserProfile(about_me="  ", tone="")
        assert p.about_me is None
        assert p.tone is None

    def test_none_values_accepted(self):
        p = UserProfile()
        assert p.about_me is None
        assert p.tone is None

    def test_valid_profile(self):
        p = UserProfile(
            about_me="Я продаю курсы",
            tone="conversational",
            script_cta="Подпишись",
        )
        assert p.about_me == "Я продаю курсы"
        assert p.tone == "conversational"


class TestUserSettingsUpdate:
    def test_custom_content_prompt_within_limit(self):
        s = UserSettingsUpdate(custom_content_prompt="x" * 10000)
        assert len(s.custom_content_prompt) == 10000

    def test_custom_content_prompt_exceeds_limit(self):
        with pytest.raises(ValidationError):
            UserSettingsUpdate(custom_content_prompt="x" * 10001)

    def test_custom_strategy_prompt_exceeds_limit(self):
        with pytest.raises(ValidationError):
            UserSettingsUpdate(custom_strategy_prompt="x" * 10001)

    def test_invalid_language(self):
        with pytest.raises(ValidationError):
            UserSettingsUpdate(language="xx")

    def test_valid_language(self):
        s = UserSettingsUpdate(language="ru")
        assert s.language == "ru"

    def test_none_prompts_accepted(self):
        s = UserSettingsUpdate()
        assert s.custom_content_prompt is None
        assert s.custom_strategy_prompt is None
