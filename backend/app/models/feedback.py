import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.database import Base


class ScriptRating(Base):
    """User rating for a completed analysis (1-5 stars + optional comment)."""

    __tablename__ = "script_ratings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    job_id = Column(
        String, ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    rating = Column(Integer, nullable=False)  # 1-5
    comment = Column(Text, nullable=True)
    viewed_at = Column(DateTime, nullable=True)  # NULL = unread by admin
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_script_rating_user_job"),
    )


class SupportConversation(Base):
    """One active support conversation per user (like Intercom)."""

    __tablename__ = "support_conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    status = Column(String(20), default="open", server_default="open")
    # status: open | resolved
    unread_admin = Column(Integer, default=0, server_default="0")
    unread_user = Column(Integer, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SupportMessage(Base):
    """Individual message in a support conversation."""

    __tablename__ = "support_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(
        String, ForeignKey("support_conversations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sender_type = Column(String(10), nullable=False)  # "user" | "admin"
    sender_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    text = Column(Text, nullable=True)  # nullable if image-only
    image_key = Column(String, nullable=True)  # S3 key for screenshot
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
