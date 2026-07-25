"""Tests for TikTok scraper: apidojo primary + clockworks fallback (Apify-only)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import DownloadError
from app.services.scraper._tiktok import TikTokScraper


# --- Realistic apidojo/tiktok-scraper response ---
APIDOJO_RESPONSE = [{
    "id": "7524124293039426871",
    "title": "Test video #fyp #viral",
    "views": 133_900_000,
    "likes": 14_600_000,
    "comments": 28_600,
    "shares": 1_600_000,
    "bookmarks": 837_000,
    "uploadedAt": 1751846731,
    "video": {
        "width": 576,
        "height": 1024,
        "ratio": "540p",
        "duration": 7.334,
        "url": "https://v16m.tiktokcdn-eu.com/video/test.mp4",
        "cover": "https://p16-sign.tiktokcdn.com/cover.jpg",
        "thumbnail": "https://p16-sign.tiktokcdn.com/thumb.jpg",
    },
    "channel": {
        "id": "123",
        "name": "Test User",
        "username": "testuser",
        "verified": False,
    },
    "postPage": "https://www.tiktok.com/@testuser/video/7524124293039426871",
}]

# --- Realistic clockworks/tiktok-scraper response (no video URL) ---
CLOCKWORKS_RESPONSE = [{
    "id": "7524124293039426871",
    "text": "Clockworks fallback video #test",
    "authorMeta": {"name": "fallback_user", "nickName": "Fallback User"},
    "videoMeta": {"height": 1024, "width": 576, "duration": 7, "coverUrl": "https://cover.jpg"},
    "webVideoUrl": "https://www.tiktok.com/@fallback_user/video/7524124293039426871",
    "diggCount": 100,
    "playCount": 5000,
    "commentCount": 10,
    "isSlideshow": False,
}]


class TestTikTokScraperPrimary:
    """apidojo primary path."""

    async def test_successful_scrape(self):
        scraper = TikTokScraper()
        with patch("app.services.scraper._tiktok.run_actor", return_value=APIDOJO_RESPONSE):
            result = await scraper.scrape("https://www.tiktok.com/@testuser/video/123")

        assert result.video_url == "https://v16m.tiktokcdn-eu.com/video/test.mp4"
        assert result.title == "Test video #fyp #viral"
        assert result.duration == 7.334
        assert result.uploader == "testuser"
        assert result.platform == "tiktok"
        assert result.view_count == 133_900_000
        assert result.like_count == 14_600_000
        assert result.comment_count == 28_600
        assert result.thumbnail == "https://p16-sign.tiktokcdn.com/cover.jpg"

    async def test_no_video_url_raises(self):
        """apidojo returns item but video.url is missing → DownloadError."""
        scraper = TikTokScraper()
        no_video = [{"title": "test", "video": {"width": 576}, "channel": {}}]
        with patch("app.services.scraper._tiktok.run_actor", return_value=no_video):
            with pytest.raises(DownloadError, match="video URL"):
                await scraper.scrape("https://www.tiktok.com/@testuser/video/123")

    async def test_no_video_object_raises(self):
        """apidojo returns item without video object → DownloadError."""
        scraper = TikTokScraper()
        no_video = [{"title": "test", "channel": {}}]
        with patch("app.services.scraper._tiktok.run_actor", return_value=no_video):
            with pytest.raises(DownloadError, match="video URL"):
                await scraper.scrape("https://www.tiktok.com/@testuser/video/456")


class TestTikTokScraperFallback:
    """Cascade: apidojo fails → clockworks fallback."""

    async def test_fallback_called_on_apidojo_error(self):
        """When apidojo raises non-DownloadError, clockworks is called."""
        scraper = TikTokScraper()
        call_count = 0

        async def mock_run_actor(actor_id, input_data, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("apidojo network error")
            return CLOCKWORKS_RESPONSE

        with patch("app.services.scraper._tiktok.run_actor", side_effect=mock_run_actor):
            # clockworks has no video URL → should raise
            with pytest.raises(DownloadError, match="ссылку на видео"):
                await scraper.scrape("https://www.tiktok.com/@testuser/video/123")
            assert call_count == 2  # apidojo + clockworks

    async def test_no_fallback_on_success(self):
        """When apidojo succeeds, clockworks is NOT called."""
        scraper = TikTokScraper()
        with patch("app.services.scraper._tiktok.run_actor", return_value=APIDOJO_RESPONSE) as mock:
            result = await scraper.scrape("https://www.tiktok.com/@testuser/video/123")
            mock.assert_called_once()
            assert result.video_url is not None

    async def test_no_fallback_on_download_error(self):
        """DownloadError from apidojo (slideshow) → NOT retried with clockworks."""
        scraper = TikTokScraper()
        no_video = [{"title": "slideshow", "video": {}, "channel": {}}]
        with patch("app.services.scraper._tiktok.run_actor", return_value=no_video) as mock:
            with pytest.raises(DownloadError):
                await scraper.scrape("https://www.tiktok.com/@testuser/video/789")
            mock.assert_called_once()  # only apidojo, no clockworks

    async def test_clockworks_slideshow_rejected(self):
        """Clockworks fallback with isSlideshow=True → rejected."""
        scraper = TikTokScraper()
        slideshow = [{"isSlideshow": True, "text": "photo"}]
        call_count = 0

        async def mock_run_actor(actor_id, input_data, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("apidojo failed")
            return slideshow

        with patch("app.services.scraper._tiktok.run_actor", side_effect=mock_run_actor):
            with pytest.raises(DownloadError, match="[Сс]лайдшоу|slideshow|фото"):
                await scraper.scrape("https://www.tiktok.com/@user/video/789")

    async def test_both_fail_gives_clear_error(self):
        """Both actors fail → clear error message."""
        scraper = TikTokScraper()

        async def mock_run_actor(actor_id, input_data, **kwargs):
            raise Exception("actor unavailable")

        with patch("app.services.scraper._tiktok.run_actor", side_effect=mock_run_actor):
            with pytest.raises(DownloadError, match="не удалось получить данные"):
                await scraper.scrape("https://www.tiktok.com/@user/video/000")


class TestTikTokScraperComments:
    async def test_comments_return_empty(self):
        scraper = TikTokScraper()
        result = await scraper.scrape_comments("https://www.tiktok.com/@user/video/123")
        assert result == []
