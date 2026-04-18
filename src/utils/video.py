"""
Video probing and metadata utilities
"""
import subprocess
from pathlib import Path
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


def get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            return float(probe.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 0.0


def probe_video(video_path: str) -> dict:
    """Probe video file and return metadata."""
    path = Path(video_path)
    duration = get_video_duration(video_path)
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "path": str(video_path),
        "name": path.name,
        "duration": duration,
        "duration_formatted": format_duration(duration),
        "size": size,
        "size_human": format_bytes(size),
    }


def probe_all_videos(video_paths: List[str]) -> List[dict]:
    """Probe multiple videos in parallel using ThreadPoolExecutor."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_path = {executor.submit(probe_video, p): p for p in video_paths}
        results = []
        for future in as_completed(future_to_path):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                path = future_to_path[future]
                results.append({
                    "path": path,
                    "error": str(e),
                    "name": Path(path).name,
                })
    return results


def format_duration(seconds: float) -> str:
    """Format duration to human readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
