"""Tests for video validation after download."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import DownloadError
from app.services.scraper._download import _validate_video, download_video_to_local, ensure_video_local
from app.services.scraper._platform import validate_video_url


# ---------------------------------------------------------------------------
# validate_video_url — SSRF and platform validation
# ---------------------------------------------------------------------------


def test_valid_urls_pass():
    assert validate_video_url("https://www.instagram.com/reel/DVa9-VJDLa5") is None
    assert validate_video_url("https://www.youtube.com/shorts/abc12345678") is None
    assert validate_video_url("https://www.tiktok.com/@user/video/123456") is None
    assert validate_video_url("https://vm.tiktok.com/abc123") is None


def test_ssrf_urls_blocked():
    assert validate_video_url("http://127.0.0.1:8080") is not None
    assert validate_video_url("http://localhost:8080/api/admin") is not None
    assert validate_video_url("http://169.254.169.254/latest/meta-data") is not None
    assert validate_video_url("http://0.0.0.0:8080/health") is not None
    assert validate_video_url("http://host.docker.internal:8080") is not None
    assert validate_video_url("redis://redis:6379") is not None


def test_unknown_platform_blocked():
    assert validate_video_url("https://evil.com/reel/abc") is not None
    assert validate_video_url("https://example.com/video.mp4") is not None


def test_at_sign_host_injection_blocked():
    # instagram.com@169.254.169.254 — the real host is 169.254.169.254
    assert validate_video_url("https://www.instagram.com@169.254.169.254/reel/test") is not None


def test_ssrf_bypass_vectors_blocked():
    """All known SSRF bypass techniques are blocked by hostname whitelist."""
    assert validate_video_url("http://[::1]:8080/admin") is not None          # IPv6 loopback
    assert validate_video_url("http://2130706433/admin") is not None           # decimal IP
    assert validate_video_url("http://0x7f000001/admin") is not None           # hex IP
    assert validate_video_url("http://127.0.0.1.nip.io/admin") is not None    # DNS rebinding
    assert validate_video_url("http://192.168.1.1/admin") is not None         # private RFC1918
    assert validate_video_url("http://172.16.0.1/admin") is not None          # private RFC1918
    assert validate_video_url("file:///etc/passwd") is not None               # file scheme
    assert validate_video_url("ftp://instagram.com/reel/abc") is not None     # non-HTTP scheme


def test_all_known_platform_hosts_accepted():
    """All supported platform hostnames pass validation."""
    valid_hosts = [
        "https://instagram.com/reel/abc123def45",
        "https://www.instagram.com/reel/abc123def45",
        "https://youtube.com/shorts/abc12345678",
        "https://www.youtube.com/shorts/abc12345678",
        "https://m.youtube.com/shorts/abc12345678",
        "https://youtu.be/abc12345678",
        "https://tiktok.com/@user/video/123",
        "https://www.tiktok.com/@user/video/123",
        "https://vm.tiktok.com/abc123def",
        "https://m.tiktok.com/@user/video/123",
        "https://vt.tiktok.com/abc123def",
    ]
    for url in valid_hosts:
        assert validate_video_url(url) is None, f"Valid URL rejected: {url}"


# ---------------------------------------------------------------------------
# _validate_video
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_video_valid(tmp_path):
    """Valid video file passes validation."""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"\x00" * 1000)

    ffprobe_output = b'{"streams":[{"codec_type":"video","codec_name":"h264","width":1080,"height":1920}],"format":{"duration":"57.0"}}'

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (ffprobe_output, b"")
        proc.returncode = 0
        mock_exec.return_value = proc

        result = await _validate_video(video)
        assert result is True


@pytest.mark.asyncio
async def test_validate_video_no_video_stream(tmp_path):
    """File with no video stream fails validation."""
    video = tmp_path / "audio_only.mp4"
    video.write_bytes(b"\x00" * 1000)

    ffprobe_output = b'{"streams":[{"codec_type":"audio","codec_name":"aac"}],"format":{"duration":"57.0"}}'

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (ffprobe_output, b"")
        proc.returncode = 0
        mock_exec.return_value = proc

        result = await _validate_video(video)
        assert result is False


@pytest.mark.asyncio
async def test_validate_video_zero_duration(tmp_path):
    """File with duration=0 fails validation."""
    video = tmp_path / "zero.mp4"
    video.write_bytes(b"\x00" * 1000)

    ffprobe_output = b'{"streams":[{"codec_type":"video","codec_name":"h264","width":1080,"height":1920}],"format":{"duration":"0.0"}}'

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (ffprobe_output, b"")
        proc.returncode = 0
        mock_exec.return_value = proc

        result = await _validate_video(video)
        assert result is False


@pytest.mark.asyncio
async def test_validate_video_ffprobe_fails(tmp_path):
    """ffprobe non-zero exit code fails validation."""
    video = tmp_path / "corrupt.mp4"
    video.write_bytes(b"\x00" * 100)

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"Invalid data found")
        proc.returncode = 1
        mock_exec.return_value = proc

        result = await _validate_video(video)
        assert result is False


@pytest.mark.asyncio
async def test_validate_video_ffprobe_timeout(tmp_path):
    """ffprobe timeout returns False (fail-safe)."""
    video = tmp_path / "hang.mp4"
    video.write_bytes(b"\x00" * 100)

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.communicate.side_effect = asyncio.TimeoutError()
        proc.kill = MagicMock()
        mock_exec.return_value = proc

        result = await _validate_video(video)
        assert result is False


# ---------------------------------------------------------------------------
# download_video_to_local — cache invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_id_creates_unique_filename(tmp_path):
    """Each job_id produces a unique filename to prevent race conditions."""
    with (
        patch("app.services.scraper._download.get_videos_dir", return_value=tmp_path),
        patch("app.services.scraper._download._download_file") as mock_dl,
        patch("app.services.scraper._download._validate_video", return_value=True),
        patch("app.services.scraper._download.storage") as mock_storage,
    ):
        mock_storage.write_from_path = AsyncMock()

        async def create_file(url, path):
            path.write_bytes(b"\x00" * 500)

        mock_dl.side_effect = create_file

        url = "https://example.com/video.mp4"
        r1 = await download_video_to_local(url, job_id="aaaa-1111")
        r2 = await download_video_to_local(url, job_id="bbbb-2222")

        # Different job_ids must produce different files
        assert r1 != r2
        assert "aaaa-111" in r1.name
        assert "bbbb-222" in r2.name


@pytest.mark.asyncio
async def test_fresh_download_invalid_raises(tmp_path):
    """Fresh download that fails validation raises DownloadError."""
    with (
        patch("app.services.scraper._download.get_videos_dir", return_value=tmp_path),
        patch("app.services.scraper._download._download_file") as mock_dl,
        patch("app.services.scraper._download._validate_video", return_value=False),
        patch("app.services.scraper._download.storage") as mock_storage,
    ):
        mock_storage.write_from_path = AsyncMock()

        # _download_file creates the file
        async def create_file(url, path):
            path.write_bytes(b"\x00" * 500)

        mock_dl.side_effect = create_file

        with pytest.raises(DownloadError, match="Video file is corrupt"):
            await download_video_to_local("https://example.com/video.mp4")


# ---------------------------------------------------------------------------
# ensure_video_local — S3 fallback for stateless workers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_video_local_file_exists(tmp_path):
    """If video exists locally, return immediately without touching S3."""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"\x00" * 1000)
    result = await ensure_video_local(video)
    assert result == video


@pytest.mark.asyncio
async def test_ensure_video_local_downloads_from_s3(tmp_path):
    """If video missing locally, download from S3 via streaming."""
    video = tmp_path / "abc123_12345678.mp4"
    # File does NOT exist locally

    with (
        patch("app.services.scraper._download.storage") as mock_storage,
        patch("app.services.scraper._download._validate_video", return_value=True),
    ):
        mock_storage.file_exists = AsyncMock(return_value=True)

        async def fake_download(key, path):
            path.write_bytes(b"\x00" * 1000)

        mock_storage.download_to_path = AsyncMock(side_effect=fake_download)

        result = await ensure_video_local(video)

    assert result.exists()
    mock_storage.file_exists.assert_called_once_with("videos/abc123_12345678.mp4")
    mock_storage.download_to_path.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_video_local_not_in_s3_raises(tmp_path):
    """If video missing both locally and in S3, raise DownloadError."""
    video = tmp_path / "missing.mp4"

    with patch("app.services.scraper._download.storage") as mock_storage:
        mock_storage.file_exists = AsyncMock(return_value=False)

        with pytest.raises(DownloadError, match="not found"):
            await ensure_video_local(video)


@pytest.mark.asyncio
async def test_ensure_video_local_invalid_from_s3_raises(tmp_path):
    """If video from S3 fails validation, raise and cleanup."""
    video = tmp_path / "bad.mp4"

    with (
        patch("app.services.scraper._download.storage") as mock_storage,
        patch("app.services.scraper._download._validate_video", return_value=False),
    ):
        mock_storage.file_exists = AsyncMock(return_value=True)

        async def fake_download(key, path):
            path.write_bytes(b"\x00" * 100)

        mock_storage.download_to_path = AsyncMock(side_effect=fake_download)

        with pytest.raises(DownloadError, match="failed validation"):
            await ensure_video_local(video)

    # File should be cleaned up
    assert not video.exists()
