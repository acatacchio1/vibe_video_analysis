"""Core YouTube download logic using yt-dlp"""

import shutil
import logging
from pathlib import Path

from yt_dlp import YoutubeDL

from .config import TEMP_DIR, UPLOADS_DIR, DEFAULT_FORMAT
from .progress import SocketIOProgressHook

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Raised when download fails"""
    pass


class YoutubeDownloader:
    def __init__(self, socketio=None, temp_dir=TEMP_DIR, uploads_dir=UPLOADS_DIR):
        self.socketio = socketio
        self.temp_dir = Path(temp_dir)
        self.uploads_dir = Path(uploads_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def download(self, url, quality=DEFAULT_FORMAT):
        ydl_opts = {
            "format": quality,
            "outtmpl": str(self.temp_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }

        if self.socketio:
            progress_hook = SocketIOProgressHook(self.socketio, "youtube_download")
            ydl_opts["progress_hooks"] = [progress_hook]

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                temp_path = Path(filename)

                if not temp_path.exists():
                    raise DownloadError(f"Download completed but file not found: {filename}")

                logger.info(f"Downloaded: {temp_path} ({info.get('title', 'unknown')})")
                return temp_path, info

        except DownloadError:
            raise
        except Exception as e:
            if self.socketio:
                self.socketio.emit("youtube_download_error", {
                    "source": "youtube_download",
                    "error": str(e),
                })
            raise DownloadError(f"Download failed: {e}") from e

    def move_to_uploads(self, temp_path, info):
        title = info.get("title", "youtube_video")
        ext = temp_path.suffix or ".mp4"

        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        safe_title = safe_title[:100]

        dest_path = self.uploads_dir / f"{safe_title}{ext}"

        counter = 1
        while dest_path.exists():
            dest_path = self.uploads_dir / f"{safe_title}_{counter}{ext}"
            counter += 1

        shutil.move(str(temp_path), str(dest_path))
        logger.info(f"Moved to uploads: {dest_path}")
        return dest_path

    def cleanup_temp(self, temp_path):
        try:
            if temp_path and temp_path.exists():
                temp_path.unlink()
                logger.info(f"Cleaned up temp file: {temp_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file: {e}")


def download_video(url, socketio=None, quality=DEFAULT_FORMAT, **kwargs):
    downloader = YoutubeDownloader(socketio=socketio)
    temp_path = None

    try:
        temp_path, info = downloader.download(url, quality=quality)
        video_path = downloader.move_to_uploads(temp_path, info)
        return video_path, info

    except Exception as e:
        if temp_path:
            downloader.cleanup_temp(temp_path)
        raise
