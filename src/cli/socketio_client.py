"""SocketIO client for start_analysis + job progress events."""
import json
import time
import threading
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
        self._done = False
        self._wait_thread = None

    def connect(self):
        self.sio.on("connect", self._on_connect)
        self.sio.on("disconnect", self._on_disconnect)
        self.sio.connect(self.url, wait_timeout=15)
        # Keep the event loop alive in a background thread so emits don't kill the connection
        self._wait_event = threading.Event()
        self._wait_thread = threading.Thread(target=self._wait_loop, daemon=True)
        self._wait_thread.start()
        return self._connected

    def _wait_loop(self):
        """Background loop to keep the SocketIO event loop alive."""
        while not self._wait_event.is_set():
            try:
                if self.sio.connected:
                    self.sio.wait()
            except Exception:
                break

    def _on_connect(self):
        self._connected = True

    def _on_disconnect(self):
        self._connected = False

    def disconnect(self):
        if self._wait_event is not None:
            self._wait_event.set()
        if self.sio and self.sio.connected:
            self.sio.disconnect()

    def start_analysis(self, payload: dict) -> Optional[str]:
        """Emit start_analysis and return the job_id from job_created event."""
        result = [None]
        got_event = threading.Event()
        job_created_handled = [False]
        error_handled = [False]

        def on_job_created(data):
            if job_created_handled[0]:
                return
            job_created_handled[0] = True
            result[0] = data.get("job_id")
            self.job_id = data.get("job_id")
            self._done = False
            got_event.set()

        def on_error(data):
            if error_handled[0]:
                return
            error_handled[0] = True
            self.formatter.error(data.get("message", "Analysis failed"))
            got_event.set()

        # Register handlers before emitting (python-socketio v5 compat)
        self.sio.on("job_created", on_job_created)
        self.sio.on("error", on_error)
        self._handle_realtime_analysis(payload)
        self.sio.emit("start_analysis", payload)

        # Wait for job_created event (background _wait_thread pumps the event loop)
        max_wait = 60
        deadline = time.time() + max_wait
        while not got_event.is_set() and time.time() < deadline:
            time.sleep(0.2)

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
            self._done = True

    def _is_my_job(self, data) -> bool:
        jid = data.get("job_id")
        return self.job_id is None or jid == self.job_id
