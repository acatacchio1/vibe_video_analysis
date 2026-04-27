"""
Unit tests for file utility functions
"""

import pytest
from unittest.mock import patch
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.security import (
    allowed_file,
    secure_filename,
    verify_path,
    validate_upload_size,
    validate_file_exists,
)


class TestAllowedFile:
    """Tests for allowed_file function"""

    def test_allowed_mp4(self):
        """Test .mp4 is allowed"""
        assert allowed_file("video.mp4") is True

    def test_allowed_avi(self):
        """Test .avi is allowed"""
        assert allowed_file("movie.avi") is True

    def test_allowed_mov(self):
        """Test .mov is allowed"""
        assert allowed_file("clip.mov") is True

    def test_allowed_mkv(self):
        """Test .mkv is allowed"""
        assert allowed_file("film.mkv") is True

    def test_allowed_webm(self):
        """Test .webm is allowed"""
        assert allowed_file("animation.webm") is True

    def test_allowed_mixed_case(self):
        """Test upper case extensions are allowed"""
        assert allowed_file("VIDEO.MP4") is True
        assert allowed_file("movie.AVI") is True

    def test_disallowed_txt(self):
        """Test .txt is not allowed"""
        assert allowed_file("file.txt") is False

    def test_disallowed_sh(self):
        """Test .sh is not allowed"""
        assert allowed_file("script.sh") is False

    def test_disallowed_py(self):
        """Test .py is not allowed"""
        assert allowed_file("script.py") is False

    def test_no_extension(self):
        """Test file without extension is not allowed"""
        assert allowed_file("video") is False

    def test_empty_filename(self):
        """Test empty filename returns False"""
        assert allowed_file("") is False

    def test_null_filename(self):
        """Test None filename returns False"""
        assert allowed_file(None) is False


class TestSecureFilename:
    """Tests for secure_filename function"""

    def test_normal_filename(self):
        """Test normal filename passes through"""
        result = secure_filename("video.mp4")
        assert result == "video.mp4"

    def test_special_characters_removed(self):
        """Test special characters are removed"""
        result = secure_filename("video<script>?.mp4")
        assert "<" not in result
        assert ">" not in result
        assert "?" not in result
        assert result == "videoscript.mp4"

    def test_path_traversal_blocked(self):
        """Test path traversal attempts are blocked"""
        result = secure_filename("../../etc/passwd")
        assert ".." not in result
        assert result == "____etc_passwd"

    def test_forward_slash_blocked(self):
        """Test forward slashes are replaced"""
        result = secure_filename("folder/video.mp4")
        assert "/" not in result

    def test_backslash_blocked(self):
        """Test backslashes are replaced"""
        result = secure_filename("folder\\video.mp4")
        assert "\\" not in result

    def test_empty_after_sanitization(self):
        """Test filename that becomes degenerate gets default name"""
        result = secure_filename("...")
        assert result != ""
        assert result == "unnamed_file"

    def test_starts_with_dot(self):
        """Test hidden file gets default name"""
        result = secure_filename(".hidden.mp4")
        # Should not start with dot
        assert not result.startswith(".")
        assert result == "unnamed_file"

    def test_long_filename_truncated(self):
        """Test long filename is truncated"""
        long_name = "a" * 300 + ".mp4"
        result = secure_filename(long_name)
        assert len(result) <= 255

    def test_unicode_characters(self):
        """Test unicode characters outside ASCII are stripped, resulting in fallback name"""
        result = secure_filename("视频视频.mp4")
        # Non-ASCII chars are stripped; no word chars remain -> fallback name
        assert result == "unnamed_file"

    def test_spaces_preserved(self):
        """Test spaces are preserved"""
        result = secure_filename("my video file.mp4")
        assert " " in result


class TestVerifyPath:
    """Tests for verify_path function"""

    def test_path_within_base(self, tmp_path):
        """Test path within base directory returns True"""
        base = tmp_path / "uploads"
        base.mkdir()
        user_path = "video.mp4"

        result = verify_path(base, user_path)
        assert result is True

    def test_path_escapes_base(self, tmp_path):
        """Test path escaping base directory returns False"""
        base = tmp_path / "uploads"
        base.mkdir()
        user_path = "../../../etc/passwd"

        result = verify_path(base, user_path)
        assert result is False

    def test_absolute_path_outside_base(self, tmp_path):
        """Test absolute path to /etc/passwd is blocked"""
        base = tmp_path / "uploads"
        base.mkdir()
        # Pass an absolute path that resolves outside base
        result = verify_path(base, "/etc/passwd")
        assert result is False

    def test_nested_path_within_base(self, tmp_path):
        """Test deeply nested path within base returns True"""
        base = tmp_path / "uploads"
        base.mkdir(parents=True)
        user_path = "a/b/c/video.mp4"

        result = verify_path(base, user_path)
        assert result is True


class TestValidateUploadSize:
    """Tests for validate_upload_size function"""

    def test_valid_small_file(self):
        """Test small file is valid"""
        is_valid, msg = validate_upload_size(1024)
        assert is_valid is True
        assert msg == ""

    def test_valid_large_file(self):
        """Test large but valid file is valid"""
        is_valid, msg = validate_upload_size(500 * 1024 * 1024)  # 500MB
        assert is_valid is True
        assert msg == ""

    def test_file_too_large(self):
        """Test file exceeding limit returns invalid"""
        is_valid, msg = validate_upload_size(2 * 1024 * 1024 * 1024)  # 2GB
        assert is_valid is False
        assert "too large" in msg.lower()

    def test_zero_size(self):
        """Test zero size file is invalid"""
        is_valid, msg = validate_upload_size(0)
        assert is_valid is False
        assert "greater than 0" in msg.lower()

    def test_negative_size(self):
        """Test negative size is invalid"""
        is_valid, msg = validate_upload_size(-100)
        assert is_valid is False


class TestValidateFileExists:
    """Tests for validate_file_exists function"""

    def test_existing_file(self, temp_upload_dir):
        """Test existing file returns valid"""
        test_file = temp_upload_dir / "test.txt"
        test_file.write_text("content")

        is_valid, msg = validate_file_exists(str(test_file))
        assert is_valid is True

    def test_nonexistent_file(self):
        """Test non-existent file returns invalid"""
        is_valid, msg = validate_file_exists("/nonexistent/path/file.txt")
        assert is_valid is False
        assert "does not exist" in msg.lower()

    def test_directory_instead_of_file(self, temp_upload_dir):
        """Test directory instead of file returns invalid"""
        is_valid, msg = validate_file_exists(str(temp_upload_dir))
        assert is_valid is False
        assert "not a file" in msg.lower()


class TestValidateUploadSizeEdgeCases:
    def test_exactly_max_size(self):
        """Test file at exact max size is valid"""
        from src.utils.security import MAX_FILE_SIZE

        is_valid, msg = validate_upload_size(MAX_FILE_SIZE)
        assert is_valid is True

    def test_one_byte_over_max(self):
        """Test file 1 byte over max is invalid"""
        from src.utils.security import MAX_FILE_SIZE

        is_valid, msg = validate_upload_size(MAX_FILE_SIZE + 1)
        assert is_valid is False
