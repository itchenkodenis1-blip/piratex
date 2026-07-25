from slowapi import Limiter

from app.config import settings


def _get_real_ip(request) -> str:
    """Extract real client IP behind Railway / Cloudflare proxy."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(
    key_func=_get_real_ip,
    storage_uri=settings.redis_url,
    in_memory_fallback_enabled=True,
)
