"""
Unit tests for WebSocket handlers in src/websocket/handlers.py
"""
import sys
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

sys.modules['pynvml'] = Mock()

from flask import Flask
from src.websocket.handlers import get_openrouter_api_key, register_socket_handlers


class MockSocketIO:
    def __init__(self):
        self.handlers = {}
        self.on_calls = []
        
    def on(self, event):
        def decorator(fn):
            self.handlers[event] = fn
            self.on_calls.append(event)
            return fn
        return decorator


def create_test_app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    return app


@pytest.fixture
def app():
    return create_test_app()


@pytest.fixture
def mock_sio():
    return MockSocketIO()


@pytest.fixture
def flask_request_context(app):
    with app.app_context():
        with app.test_request_context('/'):
            yield


@pytest.fixture(autouse=True)
def patch_constants():
    with patch("config.constants.DEBUG", False):
        yield


@pytest.mark.unit
@pytest.mark.websocket
class TestHandleConnect:
    def test_connect_handler_registered(self, mock_sio):
        register_socket_handlers(mock_sio)
        assert "connect" in mock_sio.handlers

    def test_connect_emits_connected_event(self, flask_request_context, mock_sio):
        with patch("monitor.monitor") as mock_mon:
            mock_mon.get_latest.return_value = {
                "nvidia_smi": "", "litellm_ps": "", "nvidia_gpus": [], "timestamp": 0
            }
            mock_socket_request = Mock(sid="test_sid_123")

            register_socket_handlers(mock_sio)
            handler = mock_sio.handlers["connect"]

            with patch("flask_socketio.emit") as mock_emit, \
                 patch("flask.request", mock_socket_request):
                handler()
                emit_events = [c[0][0] for c in mock_emit.call_args_list]
                assert "connected" in emit_events

    def test_connect_emits_system_status_when_monitor_has_data(self, flask_request_context, mock_sio):
        with patch("monitor.monitor") as mock_mon:
            mock_mon.get_latest.return_value = {
                "nvidia_smi": "GPU 0: 8GB used",
                "litellm_ps": "",
                "nvidia_gpus": [{"index": 0, "name": "RTX 3080"}],
                "timestamp": 1234567890.0,
            }
            mock_socket_request = Mock(sid="test_sid_123")

            register_socket_handlers(mock_sio)
            handler = mock_sio.handlers["connect"]

            with patch("flask_socketio.emit") as mock_emit, \
                 patch("flask.request", mock_socket_request):
                handler()
                emit_events = [c[0][0] for c in mock_emit.call_args_list]
                assert "connected" in emit_events
                assert "system_status" in emit_events
                status_data = [c for c in mock_emit.call_args_list if c[0][0] == "system_status"][0]
                assert status_data[0][1]["type"] == "nvidia_smi"

    def test_connect_skips_system_status_when_empty(self, flask_request_context, mock_sio):
        with patch("monitor.monitor") as mock_mon:
            mock_mon.get_latest.return_value = {
                "nvidia_smi": "", "litellm_ps": "", "nvidia_gpus": [], "timestamp": 0
            }
            mock_socket_request = Mock(sid="test_sid_123")

            register_socket_handlers(mock_sio)
            handler = mock_sio.handlers["connect"]

            with patch("flask_socketio.emit") as mock_emit, \
                 patch("flask.request", mock_socket_request):
                handler()
                emit_events = [c[0][0] for c in mock_emit.call_args_list]
                assert "connected" in emit_events
                assert "system_status" not in emit_events


@pytest.mark.unit
@pytest.mark.websocket
class TestHandleDisconnect:
    def test_disconnect_handler_registered(self, mock_sio):
        register_socket_handlers(mock_sio)
        assert "disconnect" in mock_sio.handlers

    def test_disconnect_logs_sid(self, flask_request_context, mock_sio):
        mock_socket_request = Mock(sid="disc_sid")
        register_socket_handlers(mock_sio)
        handler = mock_sio.handlers["disconnect"]

        with patch("flask.request", mock_socket_request), \
             patch("src.websocket.handlers.logger") as mock_log:
            handler()
            mock_log.info.assert_called()
            assert "disc_sid" in str(mock_log.info.call_args)


@pytest.mark.unit
@pytest.mark.websocket
class TestHandleSubscribeJob:
    def test_subscribe_job_handler_registered(self, mock_sio):
        register_socket_handlers(mock_sio)
        assert "subscribe_job" in mock_sio.handlers

    def test_subscribe_job_no_job_id_returns_early(self, flask_request_context, mock_sio):
        register_socket_handlers(mock_sio)
        handler = mock_sio.handlers["subscribe_job"]

        with patch("flask_socketio.emit") as mock_emit, \
             patch("flask_socketio.join_room") as mock_join, \
             patch("flask.request", Mock(sid="test")):
            handler({})
            mock_emit.assert_not_called()
            mock_join.assert_not_called()

    def test_subscribe_job_joins_room(self, flask_request_context, mock_sio, tmp_path):
        job_id = "test_sub_jr"
        job_dir = tmp_path / "jobs" / job_id
        job_dir.mkdir(parents=True)

        mock_socket_request = Mock(sid="test_sid")
        register_socket_handlers(mock_sio)
        handler = mock_sio.handlers["subscribe_job"]

        orig_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with patch("flask_socketio.join_room") as mock_join, \
                 patch("flask_socketio.emit"), \
                 patch("flask.request", mock_socket_request):
                handler({"job_id": job_id})
            mock_join.assert_called_once_with(f"job_{job_id}")
        finally:
            os.chdir(orig_cwd)

    def test_subscribe_job_replays_status(self, flask_request_context, mock_sio, tmp_path):
        job_id = "test_sub_status"
        job_dir = tmp_path / "jobs" / job_id
        job_dir.mkdir(parents=True)

        status_data = {"stage": "analyzing_frames", "progress": 50}
        (job_dir / "status.json").write_text(json.dumps(status_data))

        mock_socket_request = Mock(sid="test_sid")
        register_socket_handlers(mock_sio)
        handler = mock_sio.handlers["subscribe_job"]

        orig_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with patch("flask_socketio.emit") as mock_emit, \
                 patch("flask_socketio.join_room"), \
                 patch("flask.request", mock_socket_request):
                handler({"job_id": job_id})
            emit_events = [c[0][0] for c in mock_emit.call_args_list]
            assert "job_status" in emit_events
            status_call = [c for c in mock_emit.call_args_list if c[0][0] == "job_status"][0]
            assert status_call[0][1]["stage"] == "analyzing_frames"
            assert status_call[0][1]["progress"] == 50
        finally:
            os.chdir(orig_cwd)

    def test_subscribe_job_replays_frames(self, flask_request_context, mock_sio, tmp_path):
        job_id = "test_sub_frames"
        job_dir = tmp_path / "jobs" / job_id
        job_dir.mkdir(parents=True)

        frames = [
            {"frame_number": 1, "timestamp": 2.5, "analysis": "Frame 1"},
            {"frame_number": 2, "timestamp": 5.0, "analysis": "Frame 2"},
        ]
        (job_dir / "frames.jsonl").write_text(
            json.dumps(frames[0]) + "\n" + json.dumps(frames[1]) + "\n"
        )

        mock_socket_request = Mock(sid="test_sid")
        register_socket_handlers(mock_sio)
        handler = mock_sio.handlers["subscribe_job"]

        orig_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with patch("flask_socketio.emit") as mock_emit, \
                 patch("flask_socketio.join_room"), \
                 patch("flask.request", mock_socket_request):
                handler({"job_id": job_id})
            frame_emits = [c for c in mock_emit.call_args_list if c[0][0] == "frame_analysis"]
            assert len(frame_emits) == 2
            assert frame_emits[0][0][1]["frame_number"] == 1
            assert frame_emits[1][0][1]["frame_number"] == 2
        finally:
            os.chdir(orig_cwd)

    def test_subscribe_job_replays_transcript(self, flask_request_context, mock_sio, tmp_path):
        job_id = "test_sub_trans"
        job_dir = tmp_path / "jobs" / job_id
        job_dir.mkdir(parents=True)

        uploads_dir = tmp_path / "uploads"
        video_dir = uploads_dir / "test_video"
        video_dir.mkdir(parents=True)
        video_file = uploads_dir / "test_video.mp4"
        video_file.write_bytes(b"fake")

        (job_dir / "input.json").write_text(json.dumps({
            "job_id": job_id,
            "video_path": str(video_file),
        }))
        (video_dir / "transcript.json").write_text(json.dumps({
            "text": "Hello world transcript",
            "segments": [{"start": 0, "end": 5, "text": "Hello world"}],
        }))

        mock_socket_request = Mock(sid="test_sid")
        register_socket_handlers(mock_sio)
        handler = mock_sio.handlers["subscribe_job"]

        orig_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with patch("flask_socketio.emit") as mock_emit, \
                 patch("flask_socketio.join_room"), \
                 patch("flask.request", mock_socket_request):
                handler({"job_id": job_id})
            transcript_emits = [c for c in mock_emit.call_args_list if c[0][0] == "job_transcript"]
            assert len(transcript_emits) == 1
            assert "Hello world" in transcript_emits[0][0][1]["transcript"]
        finally:
            os.chdir(orig_cwd)

    def test_subscribe_job_replays_complete_results(self, flask_request_context, mock_sio, tmp_path):
        job_id = "test_sub_complete"
        job_dir = tmp_path / "jobs" / job_id
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True)

        (job_dir / "status.json").write_text(json.dumps({"stage": "complete", "progress": 100}))
        (output_dir / "results.json").write_text(json.dumps({
            "transcript": {"text": ""},
            "video_description": {"response": "Final description text"},
        }))

        mock_socket_request = Mock(sid="test_sid")
        register_socket_handlers(mock_sio)
        handler = mock_sio.handlers["subscribe_job"]

        orig_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            with patch("flask_socketio.emit") as mock_emit, \
                 patch("flask_socketio.join_room"), \
                 patch("flask.request", mock_socket_request):
                handler({"job_id": job_id})
            emit_events = [c[0][0] for c in mock_emit.call_args_list]
            assert "job_description" in emit_events
            assert "job_complete" in emit_events

            desc_call = [c for c in mock_emit.call_args_list if c[0][0] == "job_description"][0]
            assert "Final description text" in desc_call[0][1]["description"]
        finally:
            os.chdir(orig_cwd)


@pytest.mark.unit
@pytest.mark.websocket
class TestHandleUnsubscribeJob:
    def test_unsubscribe_job_registered(self, mock_sio):
        register_socket_handlers(mock_sio)
        assert "unsubscribe_job" in mock_sio.handlers

    def test_unsubscribe_job_calls_leave_room(self, flask_request_context, mock_sio):
        register_socket_handlers(mock_sio)
        handler = mock_sio.handlers["unsubscribe_job"]

        with patch("flask_socketio.leave_room") as mock_leave:
            handler({"job_id": "test_unsub_123"})
            mock_leave.assert_called_once_with("job_test_unsub_123")


@pytest.mark.unit
@pytest.mark.websocket
class TestHandleStartAnalysis:
    def test_start_analysis_registered(self, mock_sio):
        register_socket_handlers(mock_sio)
        assert "start_analysis" in mock_sio.handlers

    def test_start_analysis_openrouter_no_key(self, flask_request_context, mock_sio):
        with patch.dict("sys.modules", {"app": Mock()}):
            with patch("src.websocket.handlers.get_openrouter_api_key", return_value=""):
                register_socket_handlers(mock_sio)
                handler = mock_sio.handlers["start_analysis"]

                mock_socket_request = Mock(sid="test_sid")
                with patch("flask_socketio.emit") as mock_emit, \
                     patch("flask.request", mock_socket_request):
                    handler({
                        "video_path": "/test.mp4",
                        "provider_type": "openrouter",
                        "provider_name": "OpenRouter",
                        "model": "test-model",
                    })
                    emit_events = [c[0][0] for c in mock_emit.call_args_list]
                    assert "error" in emit_events
                    err_call = [c for c in mock_emit.call_args_list if c[0][0] == "error"][0]
                    assert "not configured" in err_call[0][1]["message"]

    def test_start_analysis_creates_job(self, flask_request_context, mock_sio, tmp_path):
        from vram_manager import JobStatus
        mock_vm = Mock()
        mock_job = Mock()
        mock_job.status = Mock()
        mock_job.status.value = "running"
        mock_vm.submit_job.return_value = mock_job

        mock_socket_request = Mock(sid="test_sid")
        video_path = str(tmp_path / "uploads" / "test_video.mp4")
        (tmp_path / "uploads").mkdir(exist_ok=True)

        mock_job_dir = MagicMock()
        mock_job_dir.__truediv__ = MagicMock(return_value=mock_job_dir)
        mock_job_dir.mkdir = MagicMock()

        with patch.dict("sys.modules", {"app": Mock()}), \
             patch("vram_manager.vram_manager", mock_vm), \
             patch("flask_socketio.emit") as mock_emit, \
             patch("flask.request", mock_socket_request), \
             patch("src.websocket.handlers.Path") as mock_path_cls:

            def path_side_effect(*args, **kwargs):
                if str(args[0]) == video_path or (len(args) > 0 and str(args[0]).endswith("test_video.mp4")):
                    p = MagicMock(spec=Path)
                    p.stem = "test_video"
                    p.parent = tmp_path / "uploads"
                    return p
                if len(args) == 2 and "jobs" in str(args):
                    return mock_job_dir
                return MagicMock(spec=Path)

            mock_path_cls.side_effect = path_side_effect

            register_socket_handlers(mock_sio)
            handler = mock_sio.handlers["start_analysis"]

            handler({
                "video_path": video_path,
                "provider_type": "litellm",
                "provider_name": "LiteLLM-Proxy",
                "model": "llava:7b",
                "priority": 5,
            })

            mock_vm.submit_job.assert_called_once()
            call_kwargs = mock_vm.submit_job.call_args[1]
            assert call_kwargs["provider_type"] == "litellm"
            assert call_kwargs["priority"] == 5
            emit_events = [c[0][0] for c in mock_emit.call_args_list]
            assert "job_created" in emit_events


@pytest.mark.unit
class TestGetOpenrouterApiKey:
    def test_returns_env_key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")
        assert get_openrouter_api_key() == "test-key-123"

    def test_returns_empty_when_not_set(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert get_openrouter_api_key() == ""
