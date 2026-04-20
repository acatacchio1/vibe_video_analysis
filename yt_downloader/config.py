"""Configuration constants for YouTube download module"""

from pathlib import Path

APP_ROOT = Path(__file__).parent.parent
TEMP_DIR = APP_ROOT / "yt_downloader" / "temp"
UPLOADS_DIR = APP_ROOT / "uploads"

DEFAULT_FORMAT = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"

DEFAULT_FPS = 1.0
DEFAULT_WHISPER_MODEL = "base"
DEFAULT_LANGUAGE = "en"
