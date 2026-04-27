"""
Unit tests for helper utility functions
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.utils.helpers import (
    format_bytes,
    format_duration,
    map_exit_code_to_status,
)


class TestFormatBytes:
    """Tests for format_bytes function"""

    def test_format_bytes_bytes(self):
        """Test 500 -> '500.0 B'"""
        result = format_bytes(500)
        assert result == "500.0 B"

    def test_format_bytes_kilobytes(self):
        """Test 1500 -> '1.5 KB'"""
        result = format_bytes(1500)
        assert result == "1.5 KB"

    def test_format_bytes_megabytes(self):
        """Test 1500000 -> contains 'MB'"""
        result = format_bytes(1500000)
        assert "MB" in result
        # Should be approximately 1.4 MB
        assert result.startswith("1.4") or result.startswith("1.5")

    def test_format_bytes_gigabytes(self):
        """Test 1500000000 -> contains 'GB'"""
        result = format_bytes(1500000000)
        assert "GB" in result
        # Should be approximately 1.4 GB
        assert result.startswith("1.4") or result.startswith("1.5")

    def test_format_bytes_terabytes(self):
        """Test 1500000000000 -> contains 'TB'"""
        result = format_bytes(1500000000000)
        assert "TB" in result
        # Should be approximately 1.4 TB
        assert result.startswith("1.4") or result.startswith("1.5")

    def test_format_bytes_petabytes(self):
        """Test huge number -> contains 'PB'"""
        # 2^60 bytes = 1 exabyte, but function only goes to petabytes
        huge_number = 10**18  # 1 exabyte
        result = format_bytes(huge_number)
        assert "PB" in result
        # Should be approximately 888.2 PB
        assert "PB" in result

    def test_format_bytes_zero(self):
        """Test 0 bytes"""
        result = format_bytes(0)
        assert result == "0.0 B"

    def test_format_bytes_exact_kilobyte(self):
        """Test exactly 1024 bytes -> 1.0 KB"""
        result = format_bytes(1024)
        assert result == "1.0 KB"

    def test_format_bytes_just_below_kilobyte(self):
        """Test 1023 bytes -> 1023.0 B"""
        result = format_bytes(1023)
        assert result == "1023.0 B"

    def test_format_bytes_just_above_kilobyte(self):
        """Test 1025 bytes -> 1.0 KB"""
        result = format_bytes(1025)
        assert result == "1.0 KB"


class TestFormatDuration:
    """Tests for format_duration function"""

    def test_format_duration_seconds(self):
        """Test 30 -> '30s'"""
        result = format_duration(30)
        assert result == "30s"

    def test_format_duration_seconds_float(self):
        """Test 30.5 -> '30s' (truncated)"""
        result = format_duration(30.5)
        assert result == "30s"

    def test_format_duration_seconds_zero(self):
        """Test 0 -> '0s'"""
        result = format_duration(0)
        assert result == "0s"

    def test_format_duration_minutes(self):
        """Test 125 -> '2m 5s'"""
        result = format_duration(125)
        assert result == "2m 5s"

    def test_format_duration_minutes_exact(self):
        """Test 120 -> '2m 0s'"""
        result = format_duration(120)
        assert result == "2m 0s"

    def test_format_duration_minutes_float(self):
        """Test 125.7 -> '2m 5s' (truncated)"""
        result = format_duration(125.7)
        assert result == "2m 5s"

    def test_format_duration_hours(self):
        """Test 3661 -> '1h 1m'"""
        result = format_duration(3661)
        assert result == "1h 1m"

    def test_format_duration_hours_exact(self):
        """Test 3600 -> '1h 0m'"""
        result = format_duration(3600)
        assert result == "1h 0m"

    def test_format_duration_hours_large(self):
        """Test 7500 -> '2h 5m'"""
        result = format_duration(7500)
        assert result == "2h 5m"

    def test_format_duration_just_under_minute(self):
        """Test 59 -> '59s'"""
        result = format_duration(59)
        assert result == "59s"

    def test_format_duration_just_under_hour(self):
        """Test 3599 -> '59m 59s'"""
        result = format_duration(3599)
        assert result == "59m 59s"


class TestMapExitCodeToStatus:
    """Tests for map_exit_code_to_status function"""

    def test_map_exit_code_success(self):
        """Test exit code 0"""
        status, message = map_exit_code_to_status(0)
        assert status == "completed"
        assert message == "Job completed successfully"

    def test_map_exit_code_error(self):
        """Test exit code 1"""
        status, message = map_exit_code_to_status(1)
        assert status == "failed"
        assert message == "Job failed due to error"

    def test_map_exit_code_cancelled(self):
        """Test exit code 130"""
        status, message = map_exit_code_to_status(130)
        assert status == "cancelled"
        assert message == "Job cancelled by user"

    def test_map_exit_code_oom(self):
        """Test exit code 137"""
        status, message = map_exit_code_to_status(137)
        assert status == "failed"
        assert message == "Job terminated due to out of memory"

    def test_map_exit_code_segfault(self):
        """Test exit code 139"""
        status, message = map_exit_code_to_status(139)
        assert status == "failed"
        assert message == "Job crashed (segmentation fault)"

    def test_map_exit_code_unknown(self):
        """Test unknown exit code 999"""
        status, message = map_exit_code_to_status(999)
        assert status == "failed"
        assert message == "Job failed with exit code 999"

    def test_map_exit_code_negative(self):
        """Test negative exit code"""
        status, message = map_exit_code_to_status(-1)
        assert status == "failed"
        assert message == "Job failed with exit code -1"

    def test_map_exit_code_common_unix_signals(self):
        """Test other common Unix signal exit codes"""
        # SIGTERM (15)
        status, message = map_exit_code_to_status(143)  # 128 + 15
        assert status == "failed"
        assert message == "Job failed with exit code 143"
        
        # SIGKILL (9)
        status, message = map_exit_code_to_status(137)  # Already tested as OOM
        assert status == "failed"
        assert message == "Job terminated due to out of memory"