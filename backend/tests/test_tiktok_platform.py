"""Tests for TikTok platform detection and URL normalization (Phase 2)."""

import pytest

from app.core.exceptions import DownloadError
from app.services.scraper._platform import Platform, detect_platform, normalize_url


class TestDetectPlatformTikTok:
    def test_www_tiktok(self):
        url = "https://www.tiktok.com/@user/video/7304772554050498849"
        assert detect_platform(url) == Platform.TIKTOK

    def test_tiktok_no_www(self):
        url = "https://tiktok.com/@user/video/7304772554050498849"
        assert detect_platform(url) == Platform.TIKTOK

    def test_vm_tiktok_short_link(self):
        url = "https://vm.tiktok.com/ZMrYbKxQP/"
        assert detect_platform(url) == Platform.TIKTOK

    def test_m_tiktok_mobile(self):
        url = "https://m.tiktok.com/@user/video/7304772554050498849"
        assert detect_platform(url) == Platform.TIKTOK

    def test_vt_tiktok_short_link(self):
        url = "https://vt.tiktok.com/ZSrABC123/"
        assert detect_platform(url) == Platform.TIKTOK

    def test_unsupported_platform_mentions_tiktok(self):
        """Error message for unsupported platforms should list TikTok as supported."""
        with pytest.raises(DownloadError, match="TikTok"):
            detect_platform("https://twitter.com/user/status/123")


class TestNormalizeTikTokUrl:
    def test_strips_tracking_params(self):
        url = "https://www.tiktok.com/@user/video/123?utm_source=copy&utm_medium=share"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "utm_medium" not in result
        assert "@user/video/123" in result

    def test_preserves_path(self):
        url = "https://www.tiktok.com/@user/video/7304772554050498849"
        result = normalize_url(url)
        assert "@user/video/7304772554050498849" in result
