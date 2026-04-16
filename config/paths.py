"""
Path configuration for Video Analyzer Web
Uses environment variables for flexibility
"""

import os
from pathlib import Path

# Base directory (current working directory or APP_ROOT env var)
APP_ROOT = Path(os.environ.get("APP_ROOT", ".")).resolve()

# Directory paths
UPLOAD_DIR = APP_ROOT / "uploads"
JOBS_DIR = APP_ROOT / "jobs"
CACHE_DIR = APP_ROOT / "cache"
CONFIG_DIR = APP_ROOT / "config"
OUTPUT_DIR = APP_ROOT / "output"
THUMBS_DIR = UPLOAD_DIR / "thumbs"

# Ensure directories exist
for directory in [UPLOAD_DIR, JOBS_DIR, CACHE_DIR, CONFIG_DIR, OUTPUT_DIR, THUMBS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


# Validation functions
def is_within_upload_dir(path: Path) -> bool:
    """Check if path is within UPLOAD_DIR"""
    try:
        path.resolve().relative_to(UPLOAD_DIR.resolve())
        return True
    except ValueError:
        return False


def is_within_jobs_dir(path: Path) -> bool:
    """Check if path is within JOBS_DIR"""
    try:
        path.resolve().relative_to(JOBS_DIR.resolve())
        return True
    except ValueError:
        return False
