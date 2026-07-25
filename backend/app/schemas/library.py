from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, field_validator


class TagResponse(BaseModel):
    id: int
    name: str
    display_name: str
    category: str
    reel_count: int = 0


class UserScriptResponse(BaseModel):
    id: str
    script: str
    description: str
    editor_instructions: str
    active_hook_index: int = 0
    created_at: datetime
    updated_at: datetime


class ScriptTranslationOut(BaseModel):
    id: str
    language: str
    script: str
    description: str
    editor_instructions: str
    # True when the primary script was edited after this translation was made,
    # so the translation no longer matches the source and should be refreshed.
    stale: bool = False
    created_at: datetime
    updated_at: datetime


class UpdateScriptRequest(BaseModel):
    script: Optional[str] = None
    description: Optional[str] = None
    editor_instructions: Optional[str] = None
    active_hook_index: Optional[int] = None


class TranslateScriptRequest(BaseModel):
    language: str

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        from app.schemas.profile import SUPPORTED_LANGUAGES

        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {v}")
        return v


class LibraryReelCard(BaseModel):
    id: str
    url: str
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    video_platform: Optional[str] = None
    video_author: Optional[str] = None
    video_views: Optional[float] = None
    video_likes: Optional[float] = None
    video_comments: Optional[float] = None
    original_language: Optional[str] = None
    content_format: Optional[str] = None
    tags: list[str] = []
    job_id: str
    cover_frame_index: Optional[int] = None
    has_user_script: bool = False
    created_at: datetime


class LibraryReelDetail(BaseModel):
    id: str
    url: str
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    video_platform: Optional[str] = None
    video_author: Optional[str] = None
    video_description: Optional[str] = None
    video_views: Optional[float] = None
    video_likes: Optional[float] = None
    video_comments: Optional[float] = None
    original_language: Optional[str] = None
    content_format: Optional[str] = None
    transcript_text: Optional[str] = None
    transcript_json: Optional[Any] = None
    frames_json: Optional[Any] = None
    tags: list[TagResponse] = []
    job_id: str
    cover_frame_index: Optional[int] = None
    is_bookmarked: bool = False
    has_user_script: bool = False
    user_script: Optional[UserScriptResponse] = None
    translations: list[ScriptTranslationOut] = []
    hook_variants: Optional[list] = None
    primary_hook_score: Optional[int] = None
    primary_hook_why: Optional[str] = None
    original_primary_hook: Optional[str] = None
    hashtags: Optional[dict] = None
    share_token: Optional[str] = None
    created_at: datetime


class LibraryListResponse(BaseModel):
    items: list[LibraryReelCard]
    total: int
    page: int
    per_page: int
