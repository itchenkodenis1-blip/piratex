import logging
import re
from enum import Enum
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from app.core.exceptions import DownloadError

logger = logging.getLogger(__name__)


class Platform(Enum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"


_HOSTNAME_MAP: dict[str, Platform] = {
    "instagram.com": Platform.INSTAGRAM,
    "www.instagram.com": Platform.INSTAGRAM,
    "youtube.com": Platform.YOUTUBE,
    "www.youtube.com": Platform.YOUTUBE,
    "m.youtube.com": Platform.YOUTUBE,
    "youtu.be": Platform.YOUTUBE,
    "tiktok.com": Platform.TIKTOK,
    "www.tiktok.com": Platform.TIKTOK,
    "vm.tiktok.com": Platform.TIKTOK,
    "m.tiktok.com": Platform.TIKTOK,
    "vt.tiktok.com": Platform.TIKTOK,
}


_SUSPICIOUS_KEYWORDS = {"127.0.0.1", "localhost", "169.254", "oast.live", "metadata", "admin", "ssrf", "0.0.0.0"}


_REJECT_MSG = "Неподдерживаемая платформа: {host}. Поддерживаются: Instagram Reels, YouTube Shorts, TikTok."


def validate_video_url(url: str) -> str | None:
    """Validate URL before job creation. Returns error message or None if valid.

    Uses a whitelist approach: only known platform hostnames pass.
    This blocks all SSRF vectors (IPv6, decimal IP, DNS rebinding, etc.)
    without needing to enumerate every bypass technique.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    # Block non-HTTP schemes (redis://, ftp://, file://, etc.)
    if parsed.scheme not in ("http", "https"):
        return _REJECT_MSG.format(host=parsed.scheme)

    # Block @-based host injection (e.g. instagram.com@169.254.169.254)
    # Must check BEFORE hostname — urlparse resolves the real host,
    # but the user intent is to trick us with the username part.
    if parsed.username:
        return _REJECT_MSG.format(host=host)

    # Whitelist: only known platform hostnames pass.
    # This single check blocks ALL SSRF vectors: private IPs, IPv6,
    # decimal/hex/octal IPs, DNS rebinding, internal hostnames.
    if host not in _HOSTNAME_MAP:
        return _REJECT_MSG.format(host=host)

    return None


def detect_platform(url: str) -> Platform:
    """Detect platform from URL hostname."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    # Log suspicious / attack URLs
    url_lower = url.lower()
    if any(kw in url_lower for kw in _SUSPICIOUS_KEYWORDS) or parsed.username:
        logger.warning("SUSPICIOUS_URL url=%s host=%s", url, host)

    platform = _HOSTNAME_MAP.get(host)
    if platform is None:
        raise DownloadError(
            f"Неподдерживаемая платформа: {host}. "
            f"Поддерживаются: Instagram Reels, YouTube Shorts, TikTok."
        )
    return platform


# Tracking params to strip from URLs before sending to Apify
_STRIP_PARAMS = {
    "igsh", "igshid", "ig_rid",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "si", "feature",
}


_YT_ID_PATTERNS = [
    re.compile(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})(?:[?/]|$)"),
    re.compile(r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtu\.be/([a-zA-Z0-9_-]{11})(?:[?/]|$)"),
]


def extract_youtube_video_id(url: str) -> str | None:
    """Extract 11-char video ID from any YouTube URL format."""
    for pattern in _YT_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def normalize_url(url: str) -> str:
    """Strip tracking params and normalize URL for caching and dedup."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    clean_params = {k: v for k, v in params.items() if k not in _STRIP_PARAMS}
    clean_query = urlencode(clean_params, doseq=True)
    path = parsed.path.rstrip("/")
    # Instagram: /reels/CODE → /reel/CODE (reels is feed page, reel is single video)
    path = re.sub(r"/reels/", "/reel/", path)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", clean_query, ""))
