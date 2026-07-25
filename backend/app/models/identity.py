import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)

from app.database import Base


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_identity_provider_user"),
        Index("ix_identity_user_provider", "user_id", "provider"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(20), nullable=False)  # telegram, yandex, vk, google, email, phone
    provider_user_id = Column(String, nullable=False)
    email = Column(String, nullable=True)
    display_name = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    access_token = Column(String, nullable=True)
    refresh_token = Column(String, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    raw_profile = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MagicLinkCode(Base):
    __tablename__ = "magic_link_codes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, index=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    pin = Column(String(6), nullable=True)
    attempts = Column(Integer, default=0, server_default="0")
    ghost_user_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed = Column(Boolean, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class PhoneAuthCode(Base):
    __tablename__ = "phone_auth_codes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone = Column(String(20), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    ghost_user_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed = Column(Boolean, default=False, server_default="false")
    attempts = Column(Integer, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    state = Column(String(64), unique=True, nullable=False, index=True)
    provider = Column(String(20), nullable=False)
    ghost_user_id = Column(
        String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    redirect_url = Column(String, nullable=True)
    frontend_redirect = Column(String, nullable=True)  # pathname to return to after auth
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
