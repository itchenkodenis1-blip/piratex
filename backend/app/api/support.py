import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import get_current_user
from app.core.chat import chat_tracker
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.feedback import SupportConversation, SupportMessage
from app.models.subscription import ConsentLog
from app.models.user import User
from app.schemas.support import (
    ConversationResponse,
    MessageItem,
    PresignSupportUploadRequest,
    PresignSupportUploadResponse,
    SendMessageRequest,
    UnreadCountResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_IMAGE_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp")
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# Magic bytes for allowed image formats (first N bytes)
IMAGE_MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",  # RIFF....WEBP (check further below)
}


@router.get("/conversation", response_model=ConversationResponse)
async def get_conversation(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or create the user's support conversation with messages."""
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.user_id == user.id)
    )
    conv = result.scalar_one_or_none()

    if not conv:
        # First time opening chat — send founder welcome message
        from app.services.founder_welcome import send_founder_welcome
        conv = await send_founder_welcome(db, user.id)
        if not conv:
            return ConversationResponse(
                id="",
                status="open",
                unread_user=0,
                created_at=None,
                updated_at=None,
                messages=[],
            )

    # Fetch messages
    msg_result = await db.execute(
        select(SupportMessage)
        .where(SupportMessage.conversation_id == conv.id)
        .order_by(SupportMessage.created_at.asc())
    )
    messages = msg_result.scalars().all()

    # Mark admin messages as read
    unread_admin_msgs = [m for m in messages if m.sender_type == "admin" and m.read_at is None]
    if unread_admin_msgs:
        from datetime import datetime
        for m in unread_admin_msgs:
            m.read_at = datetime.utcnow()
        conv.unread_user = 0
        await db.commit()

    return ConversationResponse(
        id=conv.id,
        status=conv.status,
        unread_user=0,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageItem(
                id=m.id,
                sender_type=m.sender_type,
                sender_id=m.sender_id,
                text=m.text,
                image_key=m.image_key,
                read_at=m.read_at,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.post("/messages", response_model=MessageItem)
@limiter.limit("5/minute")
async def send_message(
    body: SendMessageRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a support message. Creates conversation on first message."""
    # Only verified users (with email or Telegram) can use support
    if not user.email and not user.telegram_user_id:
        raise HTTPException(status_code=403, detail="Please verify your email or connect Telegram to use support")

    # Blocked users cannot send messages
    if getattr(user, "support_blocked", False):
        raise HTTPException(status_code=403, detail="Support access has been restricted")

    if not body.text and not body.image_key:
        raise HTTPException(status_code=400, detail="Message must have text or image")

    # Validate image_key belongs to this user (prevent IDOR)
    if body.image_key and not body.image_key.startswith(f"support/{user.id}/"):
        raise HTTPException(status_code=400, detail="Invalid image key")

    # Find or create conversation
    result = await db.execute(
        select(SupportConversation).where(SupportConversation.user_id == user.id)
    )
    conv = result.scalar_one_or_none()

    is_first_message = conv is None
    if not conv:
        conv = SupportConversation(user_id=user.id)
        db.add(conv)
        await db.flush()

    # Reopen if resolved
    if conv.status == "resolved":
        conv.status = "open"

    # Log consent on first message (152-ФЗ)
    if is_first_message:
        db.add(ConsentLog(
            user_id=user.id,
            consent_type="support_chat_consent",
            action="granted",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent", "")[:500],
            metadata_json=json.dumps({"conversation_id": conv.id}, ensure_ascii=False),
        ))

    # Create message
    msg = SupportMessage(
        conversation_id=conv.id,
        sender_type="user",
        sender_id=user.id,
        text=body.text,
        image_key=body.image_key,
    )
    db.add(msg)
    conv.unread_admin = (conv.unread_admin or 0) + 1
    from datetime import datetime
    conv.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(msg)

    message_item = MessageItem(
        id=msg.id,
        sender_type=msg.sender_type,
        sender_id=msg.sender_id,
        text=msg.text,
        image_key=msg.image_key,
        read_at=msg.read_at,
        created_at=msg.created_at,
    )

    # Notify admin via Telegram bot (fire-and-forget, skip in test env)
    if settings.telegram_bot_token and settings.admin_telegram_ids:
        try:
            await _notify_admin_telegram(user, body.text, conv.id)
        except Exception as e:
            logger.warning("Failed to send Telegram notification to admin: %s", e)

    # Reset support notification cooldown so next admin reply triggers a fresh notification
    try:
        from app.core.redis_pool import get_redis
        r = await get_redis()
        if r:
            await r.delete(f"support_notif:{user.id}")
    except Exception:
        pass

    return message_item


async def _notify_admin_telegram(user: User, text: str | None, conversation_id: str | None = None):
    """Send Telegram notification to admin about new support message."""
    if not settings.telegram_bot_token or not settings.admin_telegram_ids:
        return

    from app.services.telegram import send_telegram_message, escape_html

    user_name = user.name or user.email or f"User {user.id[:8]}"
    preview = (text or "[screenshot]")[:200]

    admin_url = f"{settings.app_url}/admin/support"
    message = (
        f"💬 <b>Новое сообщение в поддержку</b>\n\n"
        f"👤 {escape_html(user_name)}\n"
        f"📝 {escape_html(preview)}"
    )

    # Inline keyboard: link to admin + reply button
    reply_markup: dict | None = None
    if conversation_id:
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "💬 Ответить", "callback_data": f"support_reply:{conversation_id}"},
                    {"text": "🔗 В админку", "url": admin_url},
                ],
            ]
        }

    admin_ids = [tid.strip() for tid in settings.admin_telegram_ids.split(",") if tid.strip()]
    for admin_tg_id in admin_ids:
        await send_telegram_message(
            chat_id=admin_tg_id,
            bot_token=settings.telegram_bot_token,
            text=message,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )


@router.post("/presign-upload", response_model=PresignSupportUploadResponse)
async def presign_support_upload(
    body: PresignSupportUploadRequest,
    user: User = Depends(get_current_user),
):
    """Generate a presigned S3 URL for uploading a screenshot."""
    if not settings.s3_bucket:
        raise HTTPException(status_code=501, detail="S3 storage is not configured")

    if body.file_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    safe_name = os.path.basename(body.file_name).strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid file name")

    image_key = f"support/{user.id}/{uuid.uuid4()}_{safe_name}"

    from app.storage import storage
    upload_url = await storage.get_upload_url(image_key, expires=3600, content_type=body.file_type)

    return PresignSupportUploadResponse(upload_url=upload_url, image_key=image_key)


def _is_valid_image(header: bytes) -> bool:
    """Check if file header matches known image magic bytes."""
    for magic, _ in IMAGE_MAGIC_BYTES.items():
        if header.startswith(magic):
            # Extra check for WebP: RIFF....WEBP
            if magic == b"RIFF" and len(header) >= 12 and header[8:12] != b"WEBP":
                return False
            return True
    return False


@router.get("/image/{image_key:path}")
async def get_support_image(
    image_key: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Serve a support image via presigned S3 redirect (force download)."""
    if not settings.s3_bucket:
        raise HTTPException(status_code=501, detail="S3 storage is not configured")

    # Only allow support/ prefix keys
    if not image_key.startswith("support/"):
        raise HTTPException(status_code=400, detail="Invalid image key")

    # IDOR protection: verify image belongs to requesting user or user is admin
    is_owner = image_key.startswith(f"support/{user.id}/")
    is_admin = False
    if not is_owner:
        admin_emails = [e.strip() for e in settings.admin_emails.split(",") if e.strip()]
        admin_tg_ids = [t.strip() for t in settings.admin_telegram_ids.split(",") if t.strip()]
        is_admin = (
            (user.email and user.email in admin_emails)
            or (user.telegram_user_id and user.telegram_user_id in admin_tg_ids)
        )
    if not is_owner and not is_admin:
        raise HTTPException(status_code=403, detail="Access denied")

    from app.storage import storage

    # Validate file is actually an image by checking magic bytes
    try:
        header = await storage.read_header(image_key, size=12)
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")

    if not _is_valid_image(header):
        logger.warning("Support image failed magic bytes check: %s", image_key)
        raise HTTPException(status_code=400, detail="File is not a valid image")

    try:
        url = await storage.get_url(image_key, force_download=True)
        return RedirectResponse(url=url, status_code=302)
    except Exception:
        raise HTTPException(status_code=404, detail="Image not found")


@router.get("/founder-avatar")
async def get_founder_avatar():
    """Public endpoint — returns redirect to founder avatar in S3."""
    from app.storage import storage

    for ext in ("webp", "jpg", "png"):
        key = f"system/founder-avatar.{ext}"
        try:
            if await storage.file_exists(key):
                url = await storage.get_url(key, expires=86400)
                return RedirectResponse(url=url, status_code=302)
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Avatar not found")


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get count of unread messages for the user."""
    result = await db.execute(
        select(SupportConversation.unread_user)
        .where(SupportConversation.user_id == user.id)
    )
    count = result.scalar_one_or_none() or 0
    return UnreadCountResponse(count=count)
