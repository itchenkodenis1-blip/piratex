import enum
import uuid
from datetime import datetime
from secrets import token_urlsafe

from sqlalchemy import Boolean, Column, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, JSON, String

from app.database import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING_AUDIO = "extracting_audio"
    TRANSCRIBING = "transcribing"
    DETECTING_SCENES = "detecting_scenes"
    EXTRACTING_FRAMES = "extracting_frames"
    ANALYZING_FRAMES = "analyzing_frames"
    GENERATING_SUMMARY = "generating_summary"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String, nullable=False)
    status = Column(SAEnum(JobStatus), default=JobStatus.PENDING)
    progress = Column(Float, default=0.0)
    progress_message = Column(String, nullable=True)
    error = Column(String, nullable=True)

    # Video metadata
    video_title = Column(String, nullable=True)
    video_duration = Column(Float, nullable=True)
    video_platform = Column(String, nullable=True)
    video_author = Column(String, nullable=True)
    video_description = Column(String, nullable=True)
    video_views = Column(Float, nullable=True)
    video_likes = Column(Float, nullable=True)
    video_comments = Column(Float, nullable=True)
    thumbnail_url = Column(String, nullable=True)

    # Results as JSON
    transcript = Column(JSON, nullable=True)
    frames = Column(JSON, nullable=True)
    adaptation_summary = Column(JSON, nullable=True)

    # Public share token
    share_token = Column(String, unique=True, nullable=True, index=True, default=lambda: token_urlsafe(12))

    # Link to public library
    library_reel_id = Column(String, ForeignKey("library_reels.id"), nullable=True)

    # Retry tracking
    retry_count = Column(Integer, default=0, server_default="0")

    # Source tracking (web, telegram, radar)
    source = Column(String, default="web", server_default="web")
    telegram_chat_id = Column(String, nullable=True)
    telegram_message_id = Column(Integer, nullable=True)

    # Security / abuse tracking
    client_ip = Column(String, nullable=True, index=True)

    # Cost tracking (per-job, filled on completion)
    cost_breakdown = Column(JSON, nullable=True)

    # User tracking
    is_filmed = Column(Boolean, default=False, server_default="false")
    is_hidden = Column(Boolean, default=False, server_default="false")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
