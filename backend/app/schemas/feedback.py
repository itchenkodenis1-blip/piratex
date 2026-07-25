from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RateJobRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class RatingResponse(BaseModel):
    rating: int
    comment: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminRatingItem(BaseModel):
    id: str
    rating: int
    comment: str | None = None
    created_at: datetime
    viewed_at: datetime | None = None
    # User info
    user_id: str
    user_email: str | None = None
    user_name: str | None = None
    user_telegram: str | None = None
    # Job info
    job_id: str
    job_url: str | None = None
    video_title: str | None = None
    library_reel_id: str | None = None

    model_config = {"from_attributes": True}


class AdminRatingListResponse(BaseModel):
    items: list[AdminRatingItem]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------------
# Deep rating detail for investigating bad ratings
# ---------------------------------------------------------------------------


class OtherScriptItem(BaseModel):
    user_email: str | None = None
    user_name: str | None = None
    script_preview: str  # first ~300 chars
    created_at: datetime


class OtherRatingItem(BaseModel):
    user_email: str | None = None
    user_name: str | None = None
    rating: int
    comment: str | None = None
    created_at: datetime


class AdminRatingDetail(BaseModel):
    # --- Rating ---
    id: str
    rating: int
    comment: str | None = None
    created_at: datetime

    # --- User ---
    user_id: str
    user_email: str | None = None
    user_name: str | None = None
    user_telegram: str | None = None
    user_tier: str | None = None
    user_registered_at: datetime | None = None

    # User presets that influenced generation
    user_profile: dict | None = None  # about_me, tone, niches, forbidden_words, etc.

    # --- Video ---
    job_id: str
    job_url: str | None = None
    video_title: str | None = None
    video_platform: str | None = None
    video_author: str | None = None
    video_duration: float | None = None
    video_views: int | None = None
    video_likes: int | None = None
    video_comments: int | None = None

    # --- Timing ---
    job_created_at: datetime | None = None
    job_completed_at: datetime | None = None
    processing_seconds: float | None = None  # completed_at - created_at

    # --- Script the user rated ---
    adaptation_summary: dict | None = None  # script, description, editor_instructions, hooks

    # --- Library reel context ---
    library_reel_id: str | None = None
    reel_first_parsed_at: datetime | None = None
    reel_submitted_by_email: str | None = None

    # --- Stats ---
    total_jobs_for_reel: int = 0
    total_scripts_for_reel: int = 0

    # --- Other users' data for this reel ---
    other_ratings: list[OtherRatingItem] = []
    other_scripts: list[OtherScriptItem] = []
