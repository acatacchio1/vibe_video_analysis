"""
Shared helper utilities for Video Analyzer Web
"""


def format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


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


def map_exit_code_to_status(returncode: int) -> tuple[str, str]:
    """Map process exit code to status and message"""
    if returncode == 0:
        return "completed", "Job completed successfully"
    elif returncode == 1:
        return "failed", "Job failed due to error"
    elif returncode == 130:
        return "cancelled", "Job cancelled by user"
    elif returncode == 137:
        return "failed", "Job terminated due to out of memory"
    elif returncode == 139:
        return "failed", "Job crashed (segmentation fault)"
    else:
        return "failed", f"Job failed with exit code {returncode}"
