import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=True, index=True)
    name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)

    # Ghost user / tier system
    is_anonymous = Column(Boolean, default=False, server_default="false")
    session_token = Column(String(64), unique=True, nullable=True, index=True)

    # Seed/demo flag — marks synthetic users created by seed scripts.
    # Outbound automations (email, telegram, billing) MUST exclude these.
    is_seed = Column(Boolean, default=False, server_default="false", nullable=False, index=True)

    # Multi-provider auth
    email_verified = Column(Boolean, default=False, server_default="false")
    auth_provider = Column(String(20), nullable=True)  # primary auth provider

    tier = Column(String(20), default="ANONYMOUS", server_default="ANONYMOUS")

    # Referral
    referral_code = Column(String(12), unique=True, nullable=True, index=True)
    referred_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Stripe
    stripe_customer_id = Column(String(255), nullable=True, unique=True, index=True)

    # Telegram
    telegram_user_id = Column(String, nullable=True, unique=True, index=True)
    telegram_username = Column(String, nullable=True)
    telegram_subscribed = Column(Boolean, default=False, server_default="false")
    telegram_checked_at = Column(DateTime, nullable=True)

    # JWT revocation
    token_version = Column(Integer, default=1, server_default="1", nullable=False)

    # Support
    support_blocked = Column(Boolean, default=False, server_default="false")

    # Production pipeline role
    team_role = Column(String(20), nullable=False, default="owner", server_default="owner")

    created_at = Column(DateTime, default=datetime.utcnow)


class TelegramAuthCode(Base):
    __tablename__ = "telegram_auth_codes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(64), unique=True, nullable=False, index=True)
    ghost_user_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_user_id = Column(String, nullable=True)
    token = Column(String, nullable=True)
    confirmed = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    openai_api_key = Column(String, nullable=True)
    anthropic_api_key = Column(String, nullable=True)
    language = Column(String, nullable=True, default="ru")
    custom_content_prompt = Column(Text, nullable=True)
    custom_strategy_prompt = Column(Text, nullable=True)
    profile_json = Column(JSON, nullable=True)
    blog_analysis_json = Column(JSON, nullable=True)
    onboarding_completed = Column(Boolean, default=False, server_default="false")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProfileParsing(Base):
    __tablename__ = "profile_parsings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_id = Column(String(36), nullable=False, unique=True, index=True)
    platform = Column(String(20), nullable=False, default="instagram")
    username = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, default="running")  # running, completed, failed
    error = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    result_json = Column(JSON, nullable=True)  # full DeepAnalyzeResult
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class UserInterestSignal(Base):
    __tablename__ = "user_interest_signals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic = Column(String(100), nullable=False)
    source = Column(String(20), nullable=False)  # parse, like, follow, script, instagram
    weight = Column(Float, nullable=False, default=1.0)
    source_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
