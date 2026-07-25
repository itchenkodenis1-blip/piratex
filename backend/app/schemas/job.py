from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, HttpUrl

from app.models.job import JobStatus


class JobCreate(BaseModel):
    url: HttpUrl
    turnstile_token: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: float = 0.0
    progress_message: Optional[str] = None
    error: Optional[str] = None
    share_token: Optional[str] = None
    library_reel_id: Optional[str] = None

    model_config = {"from_attributes": True}


class JobResultResponse(BaseModel):
    job_id: str
    url: str
    status: JobStatus
    progress: float

    # Metadata
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    video_platform: Optional[str] = None
    video_author: Optional[str] = None
    video_description: Optional[str] = None
    video_views: Optional[float] = None
    video_likes: Optional[float] = None
    video_comments: Optional[float] = None

    # Results
    transcript: Optional[Any] = None
    frames: Optional[Any] = None
    adaptation_summary: Optional[Any] = None

    share_token: Optional[str] = None
    library_reel_id: Optional[str] = None
    user_script_id: Optional[str] = None
    production_status: Optional[str] = None

    # Teaser mode for anonymous users (truncated results)
    is_teaser: bool = False
    teaser_limits: Optional[dict] = None

    # User's own rating for this job (None if not rated)
    my_rating: Optional[int] = None

    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    model_config = {"from_attributes": True}


class JobCardResponse(BaseModel):
    """Lightweight job info for the 'My Videos' list."""
    job_id: str
    url: str
    status: JobStatus
    progress: float = 0.0
    progress_message: Optional[str] = None
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    video_platform: Optional[str] = None
    video_author: Optional[str] = None
    video_views: Optional[float] = None
    video_likes: Optional[float] = None
    video_comments: Optional[float] = None
    thumbnail_url: Optional[str] = None
    is_filmed: bool = False
    library_reel_id: Optional[str] = None
    share_token: Optional[str] = None
    x_factor: Optional[float] = None
    user_script_id: Optional[str] = None
    production_status: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Paginated list of user's jobs."""
    items: list[JobCardResponse]
    total: int
    page: int
    per_page: int


class UpdateJobFieldsRequest(BaseModel):
    """Partial update for adaptation_summary fields (after refine/edit)."""
    script: Optional[str] = None
    description: Optional[str] = None
    editor_instructions: Optional[str] = None


class SharedJobResponse(BaseModel):
    """Public response for shared job — adaptation result + reference link + frames."""
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    video_platform: Optional[str] = None
    video_author: Optional[str] = None
    video_url: Optional[str] = None

    script: str
    description: str
    editor_instructions: str

    frames: Optional[Any] = None

    created_at: datetime

    # Set only when the viewer is the owner (authenticated)
    library_reel_id: Optional[str] = None
