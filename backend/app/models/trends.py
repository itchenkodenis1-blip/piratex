import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.database import Base


class UserTrackedProfile(Base):
    __tablename__ = "user_tracked_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(String, ForeignKey("tracked_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    frozen = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "profile_id", name="uq_user_tracked_profile"),
        Index("ix_user_tracked_profiles_frozen", "user_id", "frozen"),
    )


class TrackedProfile(Base):
    __tablename__ = "tracked_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    platform = Column(String, nullable=False)
    username = Column(String, nullable=False)
    profile_url = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    followers_count = Column(Integer, nullable=True)
    median_views = Column(Float, nullable=True)
    avg_views = Column(Float, nullable=True)
    total_reels = Column(Integer, default=0)
    niche = Column(String, nullable=True)
    topics = Column(JSON, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    check_priority = Column(String, nullable=False, default="normal")  # "normal" = 12h, "high" = 4h, "cold" = 48h
    consecutive_cold_checks = Column(Integer, default=0)
    consecutive_scrape_failures = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_blocked = Column(Boolean, default=False)
    blocked_at = Column(DateTime, nullable=True)
    blocked_reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("platform", "username", name="uq_tracked_profile_platform_username"),
    )


class ProfileReel(Base):
    __tablename__ = "profile_reels"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(
        String, ForeignKey("tracked_profiles.id", ondelete="CASCADE"), nullable=False
    )
    platform_reel_id = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    caption = Column(Text, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    thumbnail_key = Column(String, nullable=True)  # storage key, e.g. "thumbnails/{id}.jpg"
    published_at = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)

    # Latest metrics
    views = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    comments = Column(Integer, nullable=True)

    # Delta-tracking for velocity
    previous_views = Column(Integer, nullable=True)
    views_updated_at = Column(DateTime, nullable=True)

    # Calculated fields
    x_factor = Column(Float, nullable=True)
    velocity = Column(Float, nullable=True)
    hot_score = Column(Float, nullable=True)
    is_trending = Column(Boolean, default=False)
    trending_since = Column(DateTime, nullable=True)
    is_hidden = Column(Boolean, default=False)
    hidden_at = Column(DateTime, nullable=True)
    hidden_reason = Column(String, nullable=True)

    # Content Radar: when push notification was sent (dedup)
    radar_notified_at = Column(DateTime, nullable=True)

    # Per-reel niche classification (inferred from caption)
    niche = Column(String, nullable=True)

    # Link to library (if reel has been parsed)
    library_reel_id = Column(
        String, ForeignKey("library_reels.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("profile_id", "platform_reel_id", name="uq_profile_reel"),
        Index("idx_profile_reels_trending", "is_trending", "x_factor"),
        Index("idx_profile_reels_hot_score", "is_trending", "hot_score"),
        Index("idx_profile_reels_niche", "niche", "is_trending"),
        Index("idx_profile_reels_trending_since", "is_trending", "trending_since"),
        Index("idx_profile_reels_profile", "profile_id"),
        Index("idx_profile_reels_library", "library_reel_id"),
    )
