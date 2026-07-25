from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.profile import SUPPORTED_LANGUAGES, UserProfile  # noqa: F401 — re-export


class UserSettingsResponse(BaseModel):
    language: str = "ru"
    custom_content_prompt: Optional[str] = None
    custom_strategy_prompt: Optional[str] = None
    profile: Optional[UserProfile] = None
    onboarding_completed: bool = False


class UserSettingsUpdate(BaseModel):
    language: Optional[str] = None
    custom_content_prompt: Optional[str] = Field(None, max_length=10000)
    custom_strategy_prompt: Optional[str] = Field(None, max_length=10000)
    profile: Optional[UserProfile] = None
    onboarding_completed: Optional[bool] = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {v}. Must be one of {SUPPORTED_LANGUAGES}")
        return v
