"""Niche model — stores niche definitions in the database for admin CRUD."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped

from app.database import Base


class Niche(Base):
    __tablename__ = "niches"

    id: Mapped[int] = Column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = Column(String, unique=True, nullable=False, index=True)
    display_name: Mapped[str] = Column(String, nullable=False)
    display_name_en: Mapped[str | None] = Column(String, nullable=True)
    description: Mapped[str | None] = Column(String, nullable=True)
    keywords: Mapped[list] = Column(JSON, nullable=False, default=list)
    group_key: Mapped[str] = Column(String, nullable=False, default="other")
    sort_order: Mapped[int] = Column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = Column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
