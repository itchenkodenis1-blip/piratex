"""Tests for robust frame extraction with fallback strategies."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.frame_extractor import _extract_single


@pytest.mark.asyncio
async def test_extract_single_success(tmp_path):
    """Successful ffmpeg extraction returns the output path."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * 100)
    output = tmp_path / "frame.jpg"

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.communicate.return_value = (b"", b"frame=1")
        proc.returncode = 0
        mock_exec.return_value = proc

        # Simulate ffmpeg creating the output file
        output.write_bytes(b"\xff\xd8" + b"\x00" * 100)

        result = await _extract_single(video, 1.0, output)
        assert result == output


@pytest.mark.asyncio
async def test_extract_single_fast_seek_fails_accurate_succeeds(tmp_path):
    """When fast seek fails, falls back to accurate seek."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * 100)
    output = tmp_path / "frame.jpg"

    call_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        proc = AsyncMock()
        if call_count == 1:
            # Fast seek fails
            proc.returncode = 1
            proc.communicate.return_value = (b"", b"Error seeking")
        else:
            # Accurate seek succeeds
            proc.returncode = 0
            proc.communicate.return_value = (b"", b"frame=1")
            output.write_bytes(b"\xff\xd8" + b"\x00" * 100)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
        result = await _extract_single(video, 1.0, output)
        assert result == output
        assert call_count == 2


@pytest.mark.asyncio
async def test_extract_single_both_strategies_fail(tmp_path):
    """When both strategies fail, returns None."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * 100)
    output = tmp_path / "frame.jpg"

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.returncode = 1
        proc.communicate.return_value = (b"", b"Error")
        mock_exec.return_value = proc

        result = await _extract_single(video, 1.0, output)
        assert result is None
        # Should have tried 2 strategies
        assert mock_exec.call_count == 2


@pytest.mark.asyncio
async def test_extract_single_timeout(tmp_path):
    """Timeout kills process and returns None."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * 100)
    output = tmp_path / "frame.jpg"

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        proc = AsyncMock()
        proc.communicate.side_effect = asyncio.TimeoutError()
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        mock_exec.return_value = proc

        result = await _extract_single(video, 1.0, output)
        assert result is None


@pytest.mark.asyncio
async def test_extract_single_empty_file(tmp_path):
    """ffmpeg creates empty file — treated as failure, retries with fallback."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * 100)
    output = tmp_path / "frame.jpg"

    call_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate.return_value = (b"", b"")
        # Create empty file on first call
        if call_count == 1:
            output.write_bytes(b"")
        else:
            output.write_bytes(b"\xff\xd8" + b"\x00" * 50)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
        result = await _extract_single(video, 1.0, output)
        assert result == output
        assert call_count == 2
