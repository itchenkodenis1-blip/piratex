import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text

from app.database import Base


class TelegramMessage(Base):
    __tablename__ = "telegram_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    telegram_user_id = Column(String, nullable=False, index=True)
    telegram_username = Column(String, nullable=True)
    telegram_name = Column(String, nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    direction = Column(String(3), nullable=False)  # "in" or "out"
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
