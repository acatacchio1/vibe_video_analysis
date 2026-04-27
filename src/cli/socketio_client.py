"""SocketIO client for start_analysis + job progress events."""
import json
import time
import sys
from typing import Callable, Optional

try:
    from socketio import Client as SocketIOClient
    _HAVE_SOCKETIO = True
except ImportError:
    _HAVE_SOCKETIO = False

from src.cli.output import Formatter


class SocketIOAnalyzer:
    """Connects to video-analyzer-web and subscribes to analysis events."""

    def __init__(self, url: str, formatter: Formatter):
        if not _HAVE_SOCKETIO:
            raise ImportError("python-socketio is required for socket operations")
        self.url = url.rstrip("/")
        self.sio = SocketIOClient(
            reconnection=True,
            reconnection_attempts=3,
            reconnection_delay=2,
        )
        self.formatter = formatter
        self.job_id = None
        self._connected = False
        self._handlers = {}
        self._wait_event = None

    def connect(self):
        self.sio.on("connect", self._on_connect)
        self.sio.on("disconnect", self._on_disconnect)
        self.sio.connect(self.url, wait_timeout=15)
        return self._connected

    def _on_connect(self):
        self._connected = True

    def _on_disconnect(self):
        self._connected = False

    def disconnect(self):
        if self.sio and self.sio.connected:
            self.sio.disconnect()

    def start_analysis(self, payload: dict) -> Optional[str]:
        """Emit start_analysis and return the job_id from job_created event."""
        import threading
        result = [None]
        got_event = threading.Event()

        def on_job_created(data):
            result[0] = data.get("job_id")
            got_event.set()

        def on_error(data):
            self.formatter.error(data.get("message", "Analysis failed"))
            got_event.set()

        self.sio.once("job_created", on_job_created)
        self.sio.once("error", on_error)
        self._handle_realtime_analysis(payload)
        self.sio.emit("start_analysis", payload)

        max_wait = 30
        deadline = time.time() + max_wait
        while not got_event.is_set() and time.time() < deadline:
            if self.sio.connected:
                self.sio.wait(seconds=0.5)
            else:
                time.sleep(0.5)

        if not got_event.is_set():
            self.formatter.error("Timed out waiting for job creation response")
            return None

        return result[0]

    def _handle_realtime_analysis(self, payload: dict):
        self.sio.on("job_status", self._on_job_status)
        self.sio.on("frame_analysis", self._on_frame_analysis)
        self.sio.on("frame_synthesis", self._on_frame_synthesis)
        self.sio.on("job_transcript", self._on_job_transcript)
        self.sio.on("job_description", self._on_job_description)
        self.sio.on("job_complete", self._on_job_complete)

    def _on_job_status(self, data):
        if self._is_my_job(data):
            self.formatter.print_job_status(data, end="\n")

    def _on_frame_analysis(self, data):
        if self._is_my_job(data):
            self.formatter.print_frame_update(data)

    def _on_frame_synthesis(self, data):
        if self._is_my_job(data):
            self.formatter.print_synthesis_update(data)

    def _on_job_transcript(self, data):
        if self._is_my_job(data):
            self.formatter.print_transcript(data)

    def _on_job_description(self, data):
        if self._is_my_job(data):
            self.formatter.print_description(data)

    def _on_job_complete(self, data):
        if self._is_my_job(data):
            self.formatter.print_job_complete(data, data.get("success", False))

    def _is_my_job(self, data) -> bool:
        jid = data.get("job_id")
        return self.job_id is None or jid == self.job_id
