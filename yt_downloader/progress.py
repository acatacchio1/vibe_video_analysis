"""SocketIO progress hook for yt-dlp download events"""


class SocketIOProgressHook:
    def __init__(self, socketio, source_name):
        self.socketio = socketio
        self.source_name = source_name

    def __call__(self, d):
        if d["status"] == "downloading":
            self._emit_download_progress(d)
        elif d["status"] == "finished":
            self._emit_download_complete(d)
        elif d["status"] == "error":
            self._emit_download_error(d)

    def _emit_download_progress(self, d):
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes", 0)
        progress = int((downloaded / total) * 100) if total else 0
        speed = d.get("speed")
        speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "N/A"

        self.socketio.emit("youtube_download_progress", {
            "source": self.source_name,
            "progress": progress,
            "speed": speed_str,
            "eta": d.get("eta", 0),
        })

    def _emit_download_complete(self, d):
        self.socketio.emit("youtube_download_complete", {
            "source": self.source_name,
            "filename": d.get("filename"),
        })

    def _emit_download_error(self, d):
        self.socketio.emit("youtube_download_error", {
            "source": self.source_name,
            "error": d.get("error", "Unknown download error"),
        })
