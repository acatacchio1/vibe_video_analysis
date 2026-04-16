"""
Unit tests for transcode utility functions
"""

import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.transcode import (
    get_video_duration,
    probe_video,
    probe_all_videos,
    format_duration,
    format_bytes,
)


class TestGetVideoDuration:
    """Tests for get_video_duration function"""

    @patch("src.utils.transcode.subprocess.run")
    def test_valid_video_duration(self, mock_run):
        """Test valid video duration is returned"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "120.5"
        mock_process.stderr = ""
        mock_run.return_value = mock_process

        duration = get_video_duration("/test/video.mp4")

        assert duration == 120.5
        mock_run.assert_called_once()

    @patch("src.utils.transcode.subprocess.run")
    def test_failed_probe_returns_zero(self, mock_run):
        """Test failed ffprobe returns 0"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = ""
        mock_process.stderr = "error"
        mock_run.return_value = mock_process

        duration = get_video_duration("/test/video.mp4")

        assert duration == 0.0

    @patch("src.utils.transcode.subprocess.run")
    def test_timeout_returns_zero(self, mock_run):
        """Test timeout exception returns 0"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)

        duration = get_video_duration("/test/video.mp4")

        assert duration == 0.0

    @patch("src.utils.transcode.subprocess.run")
    def test_empty_output_returns_zero(self, mock_run):
        """Test empty ffprobe output returns 0"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = ""
        mock_process.stderr = ""
        mock_run.return_value = mock_process

        duration = get_video_duration("/test/video.mp4")

        assert duration == 0.0


class TestFormatDuration:
    """Tests for format_duration function"""

    def test_less_than_one_minute(self):
        """Test duration under 1 minute"""
        result = format_duration(30)
        assert result == "30s"

    def test_under_one_hour(self):
        """Test duration under 1 hour"""
        result = format_duration(120)
        assert result == "2m 0s"
        result = format_duration(125)
        assert result == "2m 5s"

    def test_one_hour_plus(self):
        """Test duration over 1 hour"""
        result = format_duration(3661)
        assert result == "1h 1m"

    def test_full_day(self):
        """Test duration over 24 hours"""
        result = format_duration(90061)  # 25 hours
        assert "25h" in result

    def test_exact_hours(self):
        """Test exact hour durations"""
        result = format_duration(3600)
        assert result == "1h 0m"
        result = format_duration(7200)
        assert result == "2h 0m"


class TestFormatBytes:
    """Tests for format_bytes function"""

    def test_bytes(self):
        """Test bytes are formatted correctly"""
        result = format_bytes(500)
        assert result == "500.0 B"

    def test_kilobytes(self):
        """Test kilobytes are formatted correctly"""
        result = format_bytes(1500)
        assert result == "1.5 KB"

    def test_megabytes(self):
        """Test megabytes are formatted correctly"""
        result = format_bytes(1500000)
        assert "MB" in result

    def test_gigabytes(self):
        """Test gigabytes are formatted correctly"""
        result = format_bytes(1500000000)
        assert "GB" in result

    def test_terabytes(self):
        """Test terabytes are formatted correctly"""
        result = format_bytes(1500000000000)
        assert "TB" in result

    def test_terminabytes(self):
        """Test petabytes are formatted correctly"""
        result = format_bytes(1500000000000000)
        assert "PB" in result


class TestProbeVideo:
    """Tests for probe_video function"""

    @patch("src.utils.transcode.get_video_duration")
    def test_probe_video_success(self, mock_duration):
        """Test successful video probing"""
        mock_duration.return_value = 120.5

        result = probe_video("/test/video.mp4")

        assert "name" in result
        assert "path" in result
        assert "duration" in result
        assert result["name"] == "video.mp4"
        assert result["duration"] == 120.5
        assert "duration_formatted" in result

    @patch("src.utils.transcode.get_video_duration")
    def test_probe_video_no_size(self, mock_duration):
        """Test probing when size cannot be determined"""
        mock_duration.return_value = 120.5

        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = probe_video("/test/video.mp4")

            assert result["size"] == 0
            assert result["size_human"] == "0.0 B"


class TestProbeAllVideos:
    """Tests for probe_all_videos function"""

    @patch("concurrent.futures.ThreadPoolExecutor")
    def test_probe_all_videos_parallel(self, mock_executor_cls):
        """Test multiple videos are probed in parallel"""
        # Build mock futures that return probe results
        video_paths = [
            "/test/video1.mp4",
            "/test/video2.mp4",
            "/test/video3.mp4",
        ]
        mock_futures = []
        for p in video_paths:
            f = MagicMock()
            f.result.return_value = {"name": Path(p).name, "duration": 120.0, "path": p}
            mock_futures.append(f)

        mock_executor = MagicMock()
        mock_executor.__enter__ = lambda s: s
        mock_executor.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.side_effect = mock_futures

        mock_executor_cls.return_value = mock_executor

        # as_completed returns futures in some order
        with patch("concurrent.futures.as_completed", return_value=iter(mock_futures)):
            results = probe_all_videos(video_paths)

        assert len(results) == 3

    @patch("src.utils.transcode.subprocess.run")
    def test_probe_all_videos_different_durations(self, mock_run):
        """Test different durations are captured"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="120.5", stderr=""),
            MagicMock(returncode=0, stdout="180.0", stderr=""),
            MagicMock(returncode=0, stdout="60.0", stderr=""),
        ]

        videos = [
            "/test/video1.mp4",
            "/test/video2.mp4",
            "/test/video3.mp4",
        ]

        results = probe_all_videos(videos)

        durations = [r["duration"] for r in results]
        assert 120.5 in durations
        assert 180.0 in durations
        assert 60.0 in durations
