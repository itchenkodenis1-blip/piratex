from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProductionStatus(str, Enum):
    SCRIPT_READY = "script_ready"
    FILMING = "filming"
    EDITING = "editing"
    REVIEW = "review"
    REJECTED = "rejected"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"


class StatusChangeRequest(BaseModel):
    new_status: ProductionStatus
    comment: str | None = None


class PipelineItem(BaseModel):
    script_id: str
    production_status: ProductionStatus | None = None
    assignee_id: str | None = None
    due_date: datetime | None = None
    scheduled_publish_at: datetime | None = None
    published_at: datetime | None = None

    # UserScript fields
    script: str | None = None
    description: str | None = None
    editor_instructions: str | None = None

    # LibraryReel fields
    library_reel_id: str | None = None
    job_id: str | None = None
    url: str | None = None
    video_title: str | None = None
    video_author: str | None = None

    model_config = {"from_attributes": True}


class PresignRequest(BaseModel):
    file_name: str
    file_type: str | None = None
    file_size: int | None = None


class PresignResponse(BaseModel):
    upload_url: str
    file_key: str


class AssetConfirmRequest(BaseModel):
    file_key: str
    file_name: str
    file_size: int | None = None
    file_type: str | None = None


class AssetResponse(BaseModel):
    id: str
    stage: str
    file_key: str
    file_name: str
    file_size: int | None = None
    file_type: str | None = None
    uploaded_by: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class CommentResponse(BaseModel):
    id: str
    stage: str
    author_id: str
    author_name: str | None = None
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryEntry(BaseModel):
    from_status: str | None = None
    to_status: str
    triggered_by: str | None = None
    triggered_by_name: str | None = None
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
