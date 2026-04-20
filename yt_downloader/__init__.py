"""
YouTube Video Download Module for Video Analyzer Web

Downloads videos from YouTube and prepares them for analysis via the
same pipeline as direct uploads.

Usage:
    from yt_downloader import download_video

    video_path, info = download_video(
        url="https://youtube.com/watch?v=...",
        socketio=socketio,
        fps=1.0,
        whisper_model="base",
        language="en"
    )
"""

from .downloader import YoutubeDownloader, download_video, DownloadError

__all__ = ["YoutubeDownloader", "download_video", "DownloadError"]
