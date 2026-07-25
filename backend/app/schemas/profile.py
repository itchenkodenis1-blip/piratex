from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.niches import VALID_NICHES  # noqa: F401 — re-export for backward compat

# Languages exposed to users for script generation / second-language translation.
# Centralized here so both UserProfile and settings schemas validate against one source.
SUPPORTED_LANGUAGES = {"ru", "en", "fr", "pt", "de"}


class UserProfile(BaseModel):
    """Structured profile fields that compose into personalized prompts."""

    about_me: Optional[str] = Field(None, max_length=2000)
    tone: Optional[str] = Field(None, max_length=500)
    script_cta: Optional[str] = Field(None, max_length=200)
    description_cta: Optional[str] = Field(None, max_length=200)
    forbidden_words: Optional[str] = Field(None, max_length=1000)
    video_format: Optional[str] = Field(None, max_length=300)
    niches: Optional[list[str]] = None
    interests: Optional[list[str]] = None

    @field_validator("niches", mode="before")
    @classmethod
    def validate_niches(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, list):
            filtered = [n for n in v if isinstance(n, str) and n in VALID_NICHES]
            return filtered[:3] if filtered else None
        return None

    content_prompt_additions: Optional[str] = Field(None, max_length=2000)

    # Bilingual scripts: auto-generate a second-language version after the primary one.
    dual_language_enabled: Optional[bool] = None  # None → default False
    second_language: Optional[str] = None         # target language code for the 2nd version

    @field_validator("second_language", mode="before")
    @classmethod
    def validate_second_language(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return None
        if isinstance(v, str) and v in SUPPORTED_LANGUAGES:
            return v
        return None

    # Morning Brief preferences
    morning_brief_enabled: Optional[bool] = None  # None → default True

    # Content Radar notification preferences
    radar_enabled: Optional[bool] = None        # None → default True
    radar_mode: Optional[str] = None            # "instant" | "digest" | "both"
    radar_min_x_factor: Optional[float] = None  # default 3.0
    radar_niches: Optional[list[str]] = None    # override niche filter; None → use profile niches
    radar_quiet_hours: Optional[bool] = None    # quiet hours 22:00-08:00 UTC; default True

    @field_validator("radar_mode", mode="before")
    @classmethod
    def validate_radar_mode(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str) and v in ("instant", "digest", "both"):
            return v
        return None

    @field_validator("radar_min_x_factor", mode="before")
    @classmethod
    def validate_radar_min_x_factor(cls, v: object) -> object:
        if v is None:
            return None
        try:
            val = float(v)
            return max(2.0, min(20.0, val))
        except (ValueError, TypeError):
            return None

    @field_validator("radar_niches", mode="before")
    @classmethod
    def validate_radar_niches(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, list):
            filtered = [n for n in v if isinstance(n, str) and n in VALID_NICHES]
            return filtered[:5] if filtered else None
        return None

    @field_validator("interests", mode="before")
    @classmethod
    def validate_interests(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, list):
            filtered = [n for n in v if isinstance(n, str) and 0 < len(n) <= 50]
            return filtered[:20] if filtered else None
        return None

    @field_validator("*", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class AnalyzeInstagramRequest(BaseModel):
    username: str


class DeepAnalyzeRequest(BaseModel):
    username: str
    analysis_id: str | None = None


class DeepAnalyzeResult(BaseModel):
    about_me: str
    tone: str
    niches: list[str]
    interests: list[str]
    video_format: str
    script_cta: str
    description_cta: str
    forbidden_words: str
    content_prompt_additions: str | None = None
