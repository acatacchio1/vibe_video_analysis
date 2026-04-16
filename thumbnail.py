import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def extract_thumbnail(
    video_path: str, output_path: str, time_percent: float = 0.1
) -> bool:
    """Extract thumbnail from video at specified percentage of duration

    Args:
        video_path: Path to video file
        output_path: Path for thumbnail output (.jpg)
        time_percent: Position in video (0.0-1.0, default 10%)

    Returns:
        True if successful
    """
    try:
        # Get video duration first
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if probe.returncode != 0:
            logger.warning(f"Failed to probe video: {probe.stderr}")
            return False

        duration = float(probe.stdout.strip())
        position = duration * time_percent

        # Extract frame
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(position),
                "-i",
                video_path,
                "-vframes",
                "1",
                "-q:v",
                "2",
                "-vf",
                "scale=320:-1",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            logger.info(f"Thumbnail extracted: {output_path}")
            return True
        else:
            logger.warning(f"FFmpeg failed: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Thumbnail extraction error: {e}")
        return False


def get_thumbnail_path(video_path: str, thumbs_dir: str = "uploads/thumbs") -> str:
    """Get expected thumbnail path for a video"""
    video_name = Path(video_path).stem
    return str(Path(thumbs_dir) / f"{video_name}.jpg")


def ensure_thumbnail(video_path: str) -> Optional[str]:
    """Ensure thumbnail exists, create if not"""
    thumb_path = get_thumbnail_path(video_path)

    if Path(thumb_path).exists():
        return thumb_path

    # Create thumbnail
    Path(thumb_path).parent.mkdir(parents=True, exist_ok=True)
    if extract_thumbnail(video_path, thumb_path):
        return thumb_path

    return None
