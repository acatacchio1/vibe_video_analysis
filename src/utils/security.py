"""
Security utilities for Video Analyzer Web
"""
import re
from pathlib import Path
from typing import Set


# Whitelist of allowed video file extensions
ALLOWED_VIDEO_EXTENSIONS: Set[str] = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

# Maximum file size (1GB)
MAX_FILE_SIZE: int = 1024 * 1024 * 1024


def allowed_file(filename: str) -> bool:
    """Check if filename has an allowed video extension."""
    if not filename or "." not in filename:
        return False
    ext = "." + filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_VIDEO_EXTENSIONS


def secure_filename(filename: str) -> str:
    """Sanitize filename by removing special characters and controlling chars."""
    filename = "".join(c for c in filename if 32 <= ord(c) < 127)
    filename = filename.replace("/", "_").replace("\\", "_")
    filename = filename.replace("..", "_")
    filename = re.sub(r"[^\w\s.-]", "", filename).strip()
    stem = Path(filename).stem if "." in filename else filename
    if not filename or filename[0] == "." or not re.search(r"[a-zA-Z0-9]", stem):
        filename = "unnamed_file"
    max_length = 255 - len(Path(filename).suffix)
    if len(filename) > max_length:
        base, ext = Path(filename).stem, Path(filename).suffix
        filename = base[: max_length - len(ext)] + ext
    return filename


def verify_path(base_dir: Path, user_path: str) -> bool:
    """Verify that user_path resolves within base_dir to prevent path traversal."""
    try:
        resolved = (base_dir / user_path).resolve()
        base_resolved = base_dir.resolve()
        try:
            resolved.relative_to(base_resolved)
            return True
        except ValueError:
            return False
    except (OSError, ValueError):
        return False


def validate_upload_size(file_size: int) -> tuple[bool, str]:
    """Check if file size is within allowed limits."""
    if file_size > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size is {format_bytes(MAX_FILE_SIZE)}"
    if file_size <= 0:
        return False, "File size must be greater than 0"
    return True, ""


def validate_file_exists(file_path: str) -> tuple[bool, str]:
    """Check if file exists and is accessible."""
    try:
        path = Path(file_path)
        if not path.exists():
            return False, "File does not exist"
        if not path.is_file():
            return False, "Path is not a file"
        if not path.is_file():
            return False, "File is not accessible"
        return True, ""
    except (OSError, PermissionError) as e:
        return False, f"Cannot access file: {e}"


def create_directory_safe(dir_path: str, permissions: int = 0o755) -> bool:
    """Create directory safely with proper permissions."""
    try:
        path = Path(dir_path)
        path.mkdir(parents=True, exist_ok=True)
        return True
    except (OSError, PermissionError):
        return False
