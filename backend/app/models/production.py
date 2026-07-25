import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base


class ProductionAsset(Base):
    __tablename__ = "production_assets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    script_id = Column(String, ForeignKey("user_scripts.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(20), nullable=False)
    file_key = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String(50), nullable=True)
    uploaded_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductionComment(Base):
    __tablename__ = "production_comments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    script_id = Column(String, ForeignKey("user_scripts.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(20), nullable=False)
    author_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductionHistory(Base):
    __tablename__ = "production_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    script_id = Column(String, ForeignKey("user_scripts.id", ondelete="CASCADE"), nullable=False, index=True)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=False)
    triggered_by = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
