from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


class TierConfig(Base):
    __tablename__ = "tier_configs"

    name = Column(String(20), primary_key=True)
    max_monthly = Column(Integer, nullable=True)
    max_total = Column(Integer, nullable=True)
    max_refines_daily = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
