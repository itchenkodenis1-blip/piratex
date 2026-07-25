from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    text: Optional[str] = Field(None, max_length=5000)
    image_key: Optional[str] = Field(None, max_length=500)


class PresignSupportUploadRequest(BaseModel):
    file_name: str
    file_type: str = "image/png"


class PresignSupportUploadResponse(BaseModel):
    upload_url: str
    image_key: str


class MessageItem(BaseModel):
    id: str
    sender_type: str  # "user" | "admin"
    sender_id: str
    text: str | None = None
    image_key: str | None = None
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: str
    status: str
    unread_user: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[MessageItem] = []

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    count: int


# Admin schemas

class AdminSupportConversationItem(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    user_name: str | None = None
    user_telegram: str | None = None
    status: str
    unread_admin: int = 0
    last_message_text: str | None = None
    last_message_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminSupportConversationListResponse(BaseModel):
    items: list[AdminSupportConversationItem]
    total: int
    page: int
    per_page: int


class AdminSendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
