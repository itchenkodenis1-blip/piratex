"""Tests for YouTube Shorts-only filtering (Phase 1).

Tests:
- extract_youtube_video_id() — parses all YouTube URL formats
- _is_youtube_short() — HEAD request to /shorts/{id}
- YouTubeScraper.scrape() — rejects non-Shorts, rejects long videos, fallback
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.exceptions import DownloadError, NotYouTubeShortsError
from app.services.scraper._platform import extract_youtube_video_id
from app.services.scraper._youtube import _is_youtube_short, _parse_duration_str, _MAX_SHORTS_DURATION


# ---------------------------------------------------------------------------
# extract_youtube_video_id
# ---------------------------------------------------------------------------

class TestExtractYoutubeVideoId:
    def test_shorts_url(self):
        url = "https://www.youtube.com/shorts/abc12345678"
        assert extract_youtube_video_id(url) == "abc12345678"

    def test_shorts_url_with_query(self):
        url = "https://www.youtube.com/shorts/abc12345678?si=xyz"
        assert extract_youtube_video_id(url) == "abc12345678"

    def test_watch_url(self):
        url = "https://www.youtube.com/watch?v=abc12345678"
        assert extract_youtube_video_id(url) == "abc12345678"

    def test_watch_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=abc12345678&t=10s"
        assert extract_youtube_video_id(url) == "abc12345678"

    def test_short_youtu_be(self):
        url = "https://youtu.be/abc12345678"
        assert extract_youtube_video_id(url) == "abc12345678"

    def test_mobile_url(self):
        url = "https://m.youtube.com/shorts/abc12345678"
        assert extract_youtube_video_id(url) == "abc12345678"

    def test_mobile_watch_url(self):
        url = "https://m.youtube.com/watch?v=abc12345678"
        assert extract_youtube_video_id(url) == "abc12345678"

    def test_invalid_url(self):
        assert extract_youtube_video_id("https://instagram.com/reel/xyz") is None

    def test_no_video_id(self):
        assert extract_youtube_video_id("https://youtube.com/") is None

    def test_short_id_rejected(self):
        """YouTube video IDs are exactly 11 characters."""
        assert extract_youtube_video_id("https://youtube.com/shorts/short") is None

    def test_id_with_dash_underscore(self):
        url = "https://youtube.com/shorts/a-b_c1234-5"
        assert extract_youtube_video_id(url) == "a-b_c1234-5"


# ---------------------------------------------------------------------------
# _is_youtube_short (HEAD check)
# ---------------------------------------------------------------------------

class TestIsYoutubeShort:
    async def test_returns_true_for_shorts(self):
        """HEAD /shorts/{id} returns 200 → is a Short."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200

        with patch("app.services.scraper._youtube.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.head = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await _is_youtube_short("abc12345678")
            assert result is True

    async def test_returns_false_for_non_shorts(self):
        """HEAD /shorts/{id} returns 303 → NOT a Short."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 303

        with patch("app.services.scraper._youtube.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.head = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await _is_youtube_short("abc12345678")
            assert result is False

    async def test_network_error_returns_true(self):
        """On network error, fail-open (let duration check handle it)."""
        with patch("app.services.scraper._youtube.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.head = AsyncMock(side_effect=httpx.ConnectError("timeout"))
            mock_client_cls.return_value = mock_client

            result = await _is_youtube_short("abc12345678")
            assert result is True


# ---------------------------------------------------------------------------
# YouTubeScraper.scrape — Shorts validation
# ---------------------------------------------------------------------------

def _dc_response(duration="0:45", title="My Short", **overrides):
    """Build a mock dc_solutions actor response."""
    item = {
        "success": True,
        "downloadUrl": "https://cdn.example.com/video.mp4",
        "title": title,
        "duration": duration,
        "author": "creator",
        "thumbnail": "https://img.youtube.com/thumb.jpg",
    }
    item.update(overrides)
    return [item]


def _marielise_response(duration="0:45", title="My Short", **overrides):
    """Build a mock marielise actor response."""
    item = {
        "status": "success",
        "downloadUrl": "https://cdn.example.com/video.mp4",
        "title": title,
        "duration": duration,
        "uploader": "creator",
        "viewCount": 1000,
        "likeCount": 50,
        "commentCount": 5,
        "thumbnailUrl": "https://img.youtube.com/thumb.jpg",
    }
    item.update(overrides)
    return [item]


class TestYouTubeScraperShortsValidation:
    async def test_rejects_non_shorts_url(self):
        """Non-Shorts YouTube URL → NotYouTubeShortsError before Apify call."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=False):
            with pytest.raises(NotYouTubeShortsError, match="только YouTube Shorts"):
                await scraper.scrape("https://www.youtube.com/watch?v=abc12345678")

    async def test_rejects_long_duration_after_apify(self):
        """Video with duration > 190s → NotYouTubeShortsError after Apify returns."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", return_value=_dc_response(duration="4:00")):
            with pytest.raises(NotYouTubeShortsError, match="240 сек"):
                await scraper.scrape("https://youtube.com/shorts/abc12345678")

    async def test_allows_valid_short(self):
        """Valid Short (< 90s) passes through."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", return_value=_dc_response()):
            result = await scraper.scrape("https://youtube.com/shorts/abc12345678")
            assert result.title == "My Short"
            assert result.duration == 45.0
            assert result.video_url == "https://cdn.example.com/video.mp4"

    async def test_allows_short_at_boundary(self):
        """Video at exactly 190s is allowed (boundary)."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", return_value=_dc_response(duration="3:10")):
            result = await scraper.scrape("https://youtube.com/shorts/abc12345678")
            assert result.duration == 190.0

    async def test_no_apify_call_for_non_shorts(self):
        """Apify run_actor must NOT be called if HEAD check says not a Short."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()
        mock_run = AsyncMock()

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=False), \
             patch("app.services.scraper._youtube.run_actor", mock_run):
            with pytest.raises(NotYouTubeShortsError):
                await scraper.scrape("https://www.youtube.com/watch?v=abc12345678")

            mock_run.assert_not_called()

    async def test_rejects_unparseable_url(self):
        """URL with no extractable video ID → NotYouTubeShortsError."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()
        mock_run = AsyncMock()

        with patch("app.services.scraper._youtube.run_actor", mock_run):
            with pytest.raises(NotYouTubeShortsError, match="Не удалось распознать"):
                await scraper.scrape("https://youtube.com/channel/something")

            mock_run.assert_not_called()

    async def test_rejects_long_duration_numeric(self):
        """Apify returns duration as int (not string) > 190s → rejected."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", return_value=_dc_response(duration=250)):
            with pytest.raises(NotYouTubeShortsError, match="250 сек"):
                await scraper.scrape("https://youtube.com/shorts/abc12345678")

    async def test_allows_numeric_duration_short(self):
        """Apify returns duration as float < 190s → allowed."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", return_value=_dc_response(duration=120.5)):
            result = await scraper.scrape("https://youtube.com/shorts/abc12345678")
            assert result.duration == 120.5


# ---------------------------------------------------------------------------
# Fallback: primary fails → fallback actor succeeds
# ---------------------------------------------------------------------------

class TestYouTubeFallback:
    async def test_fallback_on_primary_failure(self):
        """When primary actor raises twice, fallback actor is tried."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()
        call_count = 0

        async def mock_run_actor(actor_id, input_data, timeout=None):
            nonlocal call_count
            call_count += 1
            # Primary retries twice (attempts 1 & 2), then fallback (attempt 3)
            if call_count <= 2:
                raise Exception("Primary actor network error")
            return _marielise_response()

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", side_effect=mock_run_actor), \
             patch("app.services.scraper._youtube.asyncio.sleep", return_value=None):
            result = await scraper.scrape("https://youtube.com/shorts/abc12345678")
            assert result.title == "My Short"
            assert call_count == 3  # 2 primary retries + 1 fallback

    async def test_download_error_retried_then_fallbacks(self):
        """DownloadError from primary is retried, then fallback + yt-dlp tried."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()
        call_count = 0

        async def mock_run_actor(actor_id, input_data, timeout=None):
            nonlocal call_count
            call_count += 1
            return _dc_response(success=False)

        async def mock_ytdlp(video_id):
            raise DownloadError("yt-dlp also failed")

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", side_effect=mock_run_actor), \
             patch("app.services.scraper._youtube._ytdlp_fallback", side_effect=mock_ytdlp), \
             patch("app.services.scraper._youtube.asyncio.sleep", return_value=None):
            with pytest.raises(DownloadError):
                await scraper.scrape("https://youtube.com/shorts/abc12345678")
            assert call_count == 3  # 2 primary + 1 fallback

    async def test_all_fallbacks_fail_raises_download_error(self):
        """When all 3 fallbacks fail, user gets a friendly error."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()

        async def mock_run_actor(actor_id, input_data, timeout=None):
            raise Exception(f"Actor {actor_id} exploded")

        async def mock_ytdlp(video_id):
            raise DownloadError("yt-dlp also failed")

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", side_effect=mock_run_actor), \
             patch("app.services.scraper._youtube._ytdlp_fallback", side_effect=mock_ytdlp), \
             patch("app.services.scraper._youtube.asyncio.sleep", return_value=None):
            with pytest.raises(DownloadError, match="Не удалось скачать"):
                await scraper.scrape("https://youtube.com/shorts/abc12345678")

    async def test_duration_gate_still_works_on_fallback(self):
        """Fallback result still checked for duration > 190s."""
        from app.services.scraper._youtube import YouTubeScraper

        scraper = YouTubeScraper()
        call_count = 0

        async def mock_run_actor(actor_id, input_data, timeout=None):
            nonlocal call_count
            call_count += 1
            # Primary retries twice, then fallback returns long video
            if call_count <= 2:
                raise Exception("Primary down")
            return _marielise_response(duration=250)

        with patch("app.services.scraper._youtube._is_youtube_short", return_value=True), \
             patch("app.services.scraper._youtube.run_actor", side_effect=mock_run_actor), \
             patch("app.services.scraper._youtube.asyncio.sleep", return_value=None):
            with pytest.raises(NotYouTubeShortsError, match="250 сек"):
                await scraper.scrape("https://youtube.com/shorts/abc12345678")


# ---------------------------------------------------------------------------
# _parse_duration_str — numeric input support
# ---------------------------------------------------------------------------

class TestParseDuration:
    def test_string_mm_ss(self):
        assert _parse_duration_str("1:30") == 90.0

    def test_string_seconds(self):
        assert _parse_duration_str("45") == 45.0

    def test_int_input(self):
        assert _parse_duration_str(45) == 45.0

    def test_float_input(self):
        assert _parse_duration_str(30.5) == 30.5

    def test_none_input(self):
        assert _parse_duration_str(None) is None

    def test_zero_int(self):
        assert _parse_duration_str(0) == 0.0
