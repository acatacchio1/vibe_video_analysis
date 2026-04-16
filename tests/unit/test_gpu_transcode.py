"""
Unit tests for GPU Transcoding utilities
"""

import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestGetCpuThreadCount:
    """Tests for CPU thread count calculation"""

    def test_high_core_count(self):
        """Test thread count for many CPU cores"""
        from gpu_transcode import get_cpu_thread_count

        with patch("multiprocessing.cpu_count", return_value=40):
            threads = get_cpu_thread_count()
            # Should cap at 30 for very high core counts
            assert threads == 30

    def test_medium_core_count(self):
        """Test thread count for moderate CPU cores"""
        from gpu_transcode import get_cpu_thread_count

        with patch("multiprocessing.cpu_count", return_value=8):
            threads = get_cpu_thread_count()
            # Should be 75% of cores, rounded
            assert threads == 6  # 8 * 0.75 = 6

    def test_low_core_count(self):
        """Test thread count for few CPU cores"""
        from gpu_transcode import get_cpu_thread_count

        with patch("multiprocessing.cpu_count", return_value=2):
            threads = get_cpu_thread_count()
            # Should be 75% of cores, minimum 1
            assert threads == 1  # 2 * 0.75 = 1.5, rounded to 1

    def test_no_cpu_count(self):
        """Test when cpu_count raises (e.g. unsupported platform)"""
        from gpu_transcode import get_cpu_thread_count

        with patch("multiprocessing.cpu_count", side_effect=NotImplementedError):
            threads = get_cpu_thread_count()
            # Falls back to 4
            assert threads == 4


class TestDetectGpuEncoders:
    """Tests for GPU encoder detection"""

    @patch("gpu_transcode.subprocess.run")
    def test_detect_nvenc(self, mock_run):
        """Test detection of NVIDIA NVENC encoder"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = (
            "libx264 (encoders: 48)\nlibnvh264 (encoders: 1)\nnvenc_h264"
        )
        mock_process.stderr = ""
        mock_run.return_value = mock_process

        encoders = None
        from gpu_transcode import detect_gpu_encoders

        encoders = detect_gpu_encoders()

        assert encoders is not None

    @patch("gpu_transcode.subprocess.run")
    def test_detect_qsv(self, mock_run):
        """Test detection of Intel Quick Sync encoder"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "libx264 (encoders: 48)\nivf (encoders: 3)\nqsv"
        mock_process.stderr = ""
        mock_run.return_value = mock_process

        encoders = None
        from gpu_transcode import detect_gpu_encoders

        encoders = detect_gpu_encoders()

        assert encoders is not None


class TestGetCpuThreadCountEdgeCases:
    """Tests for CPU thread count edge cases"""

    def test_zero_cores(self):
        """Test with zero CPU cores"""
        with patch("multiprocessing.cpu_count", return_value=0):
            from gpu_transcode import get_cpu_thread_count

            threads = get_cpu_thread_count()
            assert threads == 1  # Minimum via max(1, ...)

    def test_single_core(self):
        """Test with single CPU core"""
        with patch("multiprocessing.cpu_count", return_value=1):
            from gpu_transcode import get_cpu_thread_count

            threads = get_cpu_thread_count()
            assert threads == 1
