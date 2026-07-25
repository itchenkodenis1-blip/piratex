import asyncio
import logging
import time
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from sqlalchemy import select

from app.config import settings
from app.core.auth import decode_token
from app.core.chat import chat_tracker
from app.core.progress import progress_tracker
from app.core.showcase_tracker import showcase_tracker
from app.core.trend_tracker import trend_tracker
from app.database import async_session
from app.models.job import Job
from app.models.user import User

logger = logging.getLogger(__name__)

ws_router = APIRouter()

# --- WebSocket connection limits (DoS protection) ---
_MAX_CONNECTIONS_PER_USER = 10
_MAX_CONNECTIONS_PER_IP = 20
_IDLE_TIMEOUT_SECONDS = 300  # 5 minutes

# In-memory connection counters (per-process; sufficient for single-instance)
_user_connections: dict[str, int] = defaultdict(int)
_ip_connections: dict[str, int] = defaultdict(int)


def _get_client_ip(websocket: WebSocket) -> str:
    """Extract client IP from WebSocket connection."""
    forwarded = websocket.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return websocket.client.host if websocket.client else "unknown"


def _authenticate_ws(websocket: WebSocket) -> str | None:
    """Extract and validate JWT from query params. Returns user_id or None."""
    token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        return decode_token(token)
    except HTTPException:
        return None


async def _ws_receive_with_timeout(websocket: WebSocket, timeout: float) -> str:
    """Receive a WS message with idle timeout. Raises WebSocketDisconnect on timeout."""
    try:
        return await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
    except asyncio.TimeoutError:
        raise WebSocketDisconnect(code=4008, reason="Idle timeout")


async def _check_connection_limits(websocket: WebSocket, user_id: str) -> bool:
    """Check per-user and per-IP connection limits. Returns False if limit exceeded."""
    client_ip = _get_client_ip(websocket)
    if _user_connections[user_id] >= _MAX_CONNECTIONS_PER_USER:
        logger.warning("WS connection limit per user: user=%s count=%d", user_id, _user_connections[user_id])
        await websocket.accept()
        await websocket.close(code=4029, reason="Too many connections")
        return False
    if _ip_connections[client_ip] >= _MAX_CONNECTIONS_PER_IP:
        logger.warning("WS connection limit per IP: ip=%s count=%d", client_ip, _ip_connections[client_ip])
        await websocket.accept()
        await websocket.close(code=4029, reason="Too many connections")
        return False
    _user_connections[user_id] += 1
    _ip_connections[client_ip] += 1
    return True


def _release_connection(websocket: WebSocket, user_id: str) -> None:
    """Decrement connection counters on disconnect."""
    client_ip = _get_client_ip(websocket)
    _user_connections[user_id] = max(0, _user_connections[user_id] - 1)
    _ip_connections[client_ip] = max(0, _ip_connections[client_ip] - 1)
    # Clean up zero entries to prevent memory leak
    if _user_connections[user_id] == 0:
        _user_connections.pop(user_id, None)
    if _ip_connections[client_ip] == 0:
        _ip_connections.pop(client_ip, None)


async def _verify_job_owner(job_id: str, user_id: str) -> bool:
    """Check that job belongs to user."""
    async with async_session() as db:
        result = await db.execute(
            select(Job.user_id).where(Job.id == job_id)
        )
        owner_id = result.scalar_one_or_none()
        return owner_id == user_id


@ws_router.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(websocket: WebSocket, job_id: str):
    token_user_id = _authenticate_ws(websocket)
    if token_user_id is None:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing or invalid token")
        return

    if not await _verify_job_owner(job_id, token_user_id):
        await websocket.accept()
        await websocket.close(code=4003, reason="Access denied")
        return

    if not await _check_connection_limits(websocket, token_user_id):
        return

    await progress_tracker.connect(job_id, websocket)
    try:
        while True:
            await _ws_receive_with_timeout(websocket, _IDLE_TIMEOUT_SECONDS)
    except WebSocketDisconnect:
        await progress_tracker.disconnect(job_id, websocket)
        _release_connection(websocket, token_user_id)


@ws_router.websocket("/ws/blog-analysis/{analysis_id}")
async def blog_analysis_ws(websocket: WebSocket, analysis_id: str):
    token_user_id = _authenticate_ws(websocket)
    if token_user_id is None:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing or invalid token")
        return

    if not await _check_connection_limits(websocket, token_user_id):
        return

    # analysis_id is a server-generated UUID4 (unpredictable); auth is sufficient
    await progress_tracker.connect(analysis_id, websocket)
    try:
        while True:
            await _ws_receive_with_timeout(websocket, _IDLE_TIMEOUT_SECONDS)
    except WebSocketDisconnect:
        await progress_tracker.disconnect(analysis_id, websocket)
        _release_connection(websocket, token_user_id)


@ws_router.websocket("/ws/pipeline/{user_id}")
async def pipeline_ws(websocket: WebSocket, user_id: str):
    token_user_id = _authenticate_ws(websocket)
    if token_user_id is None:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing or invalid token")
        return
    if token_user_id != user_id:
        await websocket.accept()
        await websocket.close(code=4003, reason="User mismatch")
        return

    if not await _check_connection_limits(websocket, token_user_id):
        return

    await progress_tracker.connect(f"pipeline:{user_id}", websocket)
    try:
        while True:
            await _ws_receive_with_timeout(websocket, _IDLE_TIMEOUT_SECONDS)
    except WebSocketDisconnect:
        await progress_tracker.disconnect(f"pipeline:{user_id}", websocket)
        _release_connection(websocket, token_user_id)


@ws_router.websocket("/ws/support/{user_id}")
async def support_chat_ws(websocket: WebSocket, user_id: str):
    """WebSocket for real-time support chat messages."""
    token_user_id = _authenticate_ws(websocket)
    if token_user_id is None:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing or invalid token")
        return
    if token_user_id != user_id:
        await websocket.accept()
        await websocket.close(code=4003, reason="User mismatch")
        return

    if not await _check_connection_limits(websocket, token_user_id):
        return

    await chat_tracker.connect(user_id, websocket)
    try:
        while True:
            await _ws_receive_with_timeout(websocket, _IDLE_TIMEOUT_SECONDS)
    except WebSocketDisconnect:
        await chat_tracker.disconnect(user_id, websocket)
        _release_connection(websocket, token_user_id)


async def _is_admin_user(user_id: str) -> bool:
    """Check if user_id belongs to an admin."""
    admin_emails = [e.strip() for e in settings.admin_emails.split(",") if e.strip()]
    admin_tg_ids = [t.strip() for t in settings.admin_telegram_ids.split(",") if t.strip()]
    async with async_session() as db:
        user = await db.get(User, user_id)
        if not user:
            return False
        return bool(
            (user.email and user.email in admin_emails)
            or (user.telegram_user_id and user.telegram_user_id in admin_tg_ids)
        )


@ws_router.websocket("/ws/admin/trend-watching")
async def admin_trend_watching_ws(websocket: WebSocket):
    """WebSocket for real-time trend monitoring dashboard (admin only)."""
    token_user_id = _authenticate_ws(websocket)
    if token_user_id is None:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing or invalid token")
        return

    try:
        is_admin = await _is_admin_user(token_user_id)
    except Exception:
        await websocket.accept()
        await websocket.close(code=4500, reason="Auth check failed")
        return

    if not is_admin:
        await websocket.accept()
        await websocket.close(code=4003, reason="Admin access required")
        return

    if not await _check_connection_limits(websocket, token_user_id):
        return

    await trend_tracker.connect(websocket)
    try:
        while True:
            await _ws_receive_with_timeout(websocket, _IDLE_TIMEOUT_SECONDS)
    except WebSocketDisconnect:
        await trend_tracker.disconnect(websocket)
        _release_connection(websocket, token_user_id)


@ws_router.websocket("/ws/admin/showcase")
async def admin_showcase_ws(websocket: WebSocket):
    """WebSocket for real-time showcase events (admin only)."""
    token_user_id = _authenticate_ws(websocket)
    if token_user_id is None:
        await websocket.accept()
        await websocket.close(code=4001, reason="Missing or invalid token")
        return

    try:
        is_admin = await _is_admin_user(token_user_id)
    except Exception:
        await websocket.accept()
        await websocket.close(code=4500, reason="Auth check failed")
        return

    if not is_admin:
        await websocket.accept()
        await websocket.close(code=4003, reason="Admin access required")
        return

    if not await _check_connection_limits(websocket, token_user_id):
        return

    await showcase_tracker.connect(websocket)
    try:
        while True:
            await _ws_receive_with_timeout(websocket, _IDLE_TIMEOUT_SECONDS)
    except WebSocketDisconnect:
        await showcase_tracker.disconnect(websocket)
        _release_connection(websocket, token_user_id)
