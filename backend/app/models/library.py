import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    JSON,
    UniqueConstraint,
)

from app.database import Base

# Many-to-many: library_reels <-> tags
library_reel_tags = Table(
    "library_reel_tags",
    Base.metadata,
    Column("library_reel_id", String, ForeignKey("library_reels.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class LibraryReel(Base):
    __tablename__ = "library_reels"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.id"), unique=True, nullable=False)
    submitted_by = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String, unique=True, nullable=False, index=True)

    # Video metadata (copied from job)
    video_title = Column(String, nullable=True)
    video_duration = Column(Float, nullable=True)
    video_platform = Column(String, nullable=True, index=True)
    video_author = Column(String, nullable=True)
    video_description = Column(Text, nullable=True)
    video_views = Column(Float, nullable=True)
    video_likes = Column(Float, nullable=True)
    video_comments = Column(Float, nullable=True)

    # Searchable transcript
    transcript_text = Column(Text, nullable=True)
    transcript_json = Column(JSON, nullable=True)
    frames_json = Column(JSON, nullable=True)
    cover_frame_index = Column(Integer, nullable=True)

    # Auto-tagged classification
    original_language = Column(String, nullable=True)
    content_format = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    category = Column(String, nullable=False, default="topic")


class UserBookmark(Base):
    __tablename__ = "user_bookmarks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    library_reel_id = Column(String, ForeignKey("library_reels.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "library_reel_id", name="uq_user_bookmark"),
    )


class UserReelLike(Base):
    __tablename__ = "user_reel_likes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_user_reel_like"),
    )


class UserScript(Base):
    __tablename__ = "user_scripts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    library_reel_id = Column(String, ForeignKey("library_reels.id", ondelete="CASCADE"), nullable=False, index=True)
    script = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    editor_instructions = Column(Text, nullable=False)
    active_hook_index = Column(Integer, nullable=True, server_default="0")

    # Original script snapshot (preserved across refines for comparison)
    original_script = Column(Text, nullable=True)
    original_description = Column(Text, nullable=True)
    original_editor_instructions = Column(Text, nullable=True)

    # Production pipeline fields
    production_status = Column(String(20), nullable=True, index=True)
    assignee_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    due_date = Column(DateTime, nullable=True)
    scheduled_publish_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "library_reel_id", name="uq_user_script"),
    )


class ScriptTranslation(Base):
    """A second-language version of a UserScript, generated as a separate iteration.

    One UserScript (primary/source language) → N translations (one per language).
    Mirrors the three script blocks so teleprompter + refine work identically.
    """

    __tablename__ = "script_translations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_script_id = Column(
        String, ForeignKey("user_scripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    language = Column(String(8), nullable=False)  # 'en','es','fr','de','pt'
    script = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    editor_instructions = Column(Text, nullable=False)

    # Snapshot of the first translation, preserved across refines for comparison
    original_script = Column(Text, nullable=True)
    original_description = Column(Text, nullable=True)
    original_editor_instructions = Column(Text, nullable=True)

    # Hash of the source RU script at translation time — lets us flag a translation
    # as stale once the user edits the primary script after translating.
    source_revision = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_script_id", "language", name="uq_script_translation"),
    )


class ShootingQueueItem(Base):
    __tablename__ = "shooting_queue"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_script_id = Column(String, ForeignKey("user_scripts.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    added_at = Column(DateTime, default=datetime.utcnow)
    filmed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "user_script_id", name="uq_shooting_queue_item"),
    )
