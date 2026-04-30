# Video Analyzer Web Test Fixtures

import pytest
import json
import sys
import os
import tempfile
import shutil
import types
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_upload_dir(tmp_path):
    """Create temporary upload directory"""
    upload_dir = tmp_path / "uploads"
    thumbnails_dir = upload_dir / "thumbs"
    upload_dir.mkdir()
    thumbnails_dir.mkdir()
    return upload_dir


@pytest.fixture
def temp_jobs_dir(tmp_path):
    """Create temporary jobs directory"""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    return jobs_dir


@pytest.fixture
def mock_gpu_data():
    """Mock GPU data for VRAM manager testing"""
    return {
        "gpus": [
            {
                "index": 0,
                "name": "NVIDIA GeForce RTX 3080",
                "total_vram": 10 * (1024**3),
                "used_vram": 2 * (1024**3),
                "free_vram": 8 * (1024**3),
            },
            {
                "index": 1,
                "name": "NVIDIA GeForce RTX 3080",
                "total_vram": 10 * (1024**3),
                "used_vram": 4 * (1024**3),
                "free_vram": 6 * (1024**3),
            },
        ]
    }


@pytest.fixture
def sample_job_config():
    """Sample job configuration for testing"""
    return {
        "job_id": "test_job_123",
        "video_path": "/app/uploads/test_video.mp4",
        "provider_type": "litellm",
        "provider_name": "LiteLLM-Proxy",
        "provider_config": {"api_base": "http://172.16.17.3:4000/v1"},
        "model": "qwen3-27b-q8",
        "params": {
            "temperature": 0.0,
            "duration": 0,
            "max_frames": 50,
            "frames_per_minute": 60,
            "whisper_model": "large",
            "language": "en",
            "device": "gpu",
            "keep_frames": False,
            "user_prompt": "Describe this video",
        },
        "created_at": 1234567890.0,
    }


@pytest.fixture
def sample_frame_analysis():
    """Sample frame analysis result"""
    return {
        "frame_number": 1,
        "total_frames": 10,
        "timestamp": 2.5,
        "analysis": "A dog is running in a park",
        "usage": {
            "prompt_tokens": 500,
            "completion_tokens": 250,
            "total_tokens": 750,
        },
    }


@pytest.fixture
def sample_results_file():
    """Sample results JSON structure"""
    return {
        "metadata": {
            "job_id": "test_job_123",
            "provider": "litellm",
            "model": "qwen3-27b-q8",
            "frames_processed": 10,
            "transcription_successful": True,
        },
        "transcript": {
            "text": "This is the full transcript of the video",
            "segments": [{"start": 0, "end": 10, "text": "Hello world"}],
        },
        "frame_analyses": [
            {"frame_number": 1, "analysis": "First frame"},
            {"frame_number": 2, "analysis": "Second frame"},
        ],
        "video_description": {
            "response": "This video shows a dog running in a park",
        },
        "token_usage": {
            "prompt_tokens": 5000,
            "completion_tokens": 2500,
            "total_tokens": 7500,
        },
    }


@pytest.fixture
def mock_nvmlopen():
    """Mock NVML module for testing without actual GPU"""
    with patch.dict("sys.modules", {"pynvml": MagicMock()}):
        import pynvml

        # Configure mock
        pynvml.nvmlInit.return_value = None
        pynvml.nvmlDeviceGetCount.return_value = 2

        mock_handle0 = MagicMock()
        mock_handle1 = MagicMock()

        # GPU 0: 10GB, 2GB used
        memory_info0 = MagicMock()
        memory_info0.total = 10 * (1024**3)
        memory_info0.used = 2 * (1024**3)
        memory_info0.free = 8 * (1024**3)
        pynvml.nvmlDeviceGetMemoryInfo.side_effect = [memory_info0, memory_info0]
        pynvml.nvmlDeviceGetName.side_effect = [
            b"NVIDIA Tesla V100",
            b"NVIDIA Tesla V100",
        ]

        pynvml.nvmlDeviceGetHandleByIndex.side_effect = [mock_handle0, mock_handle1]

        yield pynvml


@pytest.fixture
def mock_chat_job_response():
    """Mock response for LLM chat job"""
    return {
        "job_id": "chat_abc12345",
        "provider_type": "litellm",
        "model_id": "qwen3-27b-q8",
        "status": "pending",
        "queue_position": 1,
        "prompt": "Summarize this",
        "created_at": 1234567890.0,
    }


@pytest.fixture
def mock_litellm_client():
    """Mock LiteLLM client for testing"""
    client = MagicMock()
    client.completion.return_value = {
        "choices": [{"message": {"content": "Test response"}}],
        "usage": {
            "prompt_tokens": 400,
            "completion_tokens": 100,
            "total_tokens": 500,
        },
    }
    return client


@pytest.fixture
def mock_video_file(temp_upload_dir):
    """Create a minimal mock video file"""
    video_path = temp_upload_dir / "test_video.mp4"
    video_path.write_bytes(b"\x00\x01\x02\x03" * 1000)
    return video_path


@pytest.fixture
def mock_ffprobe_output():
    """Mock ffprobe subprocess response"""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "120.5"
    mock_process.stderr = ""
    return mock_process


@pytest.fixture
def setup_vram_manager(temp_jobs_dir):
    """Setup VRAM manager with test directories"""
    with patch("vram_manager.Path") as mock_path:
        mock_path.return_value.mkdir = MagicMock()
        from vram_manager import VRAMManager

        manager = VRAMManager()
        return manager


# NEW FIXTURES FOR API AND WEBSOCKET TESTING

@pytest.fixture
def mock_api_error():
    """Mock api_error function used by blueprints"""
    def _api_error(message, code=400):
        from flask import jsonify
        return jsonify({"error": {"code": code, "message": message}}), code
    return _api_error


@pytest.fixture
def mock_vram_manager():
    """Create a fully mocked VRAM manager"""
    manager = MagicMock()

    # Default return values
    manager.get_all_jobs.return_value = []
    manager.get_running_jobs.return_value = []
    manager.get_queued_jobs.return_value = []
    manager.get_job.return_value = None
    manager.cancel_job.return_value = True
    manager.update_priority.return_value = True

    # Job mock with to_dict
    job = MagicMock()
    job.job_id = "test_job_123"
    job.status = MagicMock()
    job.status.value = "running"
    job.to_dict.return_value = {
        "job_id": "test_job_123",
        "status": "running",
        "provider_type": "litellm",
        "model_id": "qwen3-27b-q8",
    }
    manager.get_job.return_value = job
    manager.get_all_jobs.return_value = [job]

    return manager


@pytest.fixture
def mock_chat_queue_manager():
    """Create a fully mocked chat queue manager"""
    manager = MagicMock()
    manager.submit_job.return_value = "chat_abc12345"
    manager.get_job_status.return_value = {
        "job_id": "chat_abc12345",
        "status": "pending",
        "queue_position": 1,
    }
    manager.cancel_job.return_value = True
    manager.get_queue_stats.return_value = {
        "total_jobs": 5,
        "queued": 3,
        "running": 2,
        "recent_completed": 0,
    }
    return manager


@pytest.fixture
def mock_socketio():
    """Create a mocked SocketIO instance"""
    sio = MagicMock()
    sio.emit = MagicMock()
    sio.start_background_task = MagicMock()
    return sio


@pytest.fixture
def mock_monitor():
    """Create a mocked Monitor instance"""
    monitor = MagicMock()
    monitor.get_latest.return_value = {
        "nvidia_smi": "GPU 0: 10GB",
        "nvidia_gpus": [],
        "timestamp": 1234567890.0,
    }
    return monitor


@pytest.fixture
def mock_providers_dict():
    """Create a mocked providers dictionary"""
    litellm_provider = MagicMock()
    litellm_provider.estimate_vram.return_value = 8 * (1024**3)
    litellm_provider.to_dict.return_value = {
        "name": "LiteLLM-Proxy",
        "type": "litellm",
        "api_base": "http://172.16.17.3:4000/v1",
        "status": "online",
    }

    openrouter_provider = MagicMock()
    openrouter_provider.to_dict.return_value = {
        "name": "OpenRouter",
        "type": "openrouter",
        "status": "online",
    }
    openrouter_provider.status = "online"
    openrouter_provider.pricing_cache = {}
    openrouter_provider.get_models.return_value = []
    openrouter_provider.estimate_cost.return_value = {"total": 0.01}

    return {
        "LiteLLM-Proxy": litellm_provider,
        "OpenRouter": openrouter_provider,
    }


# Build a Flask test app with all blueprints registered against mocked dependencies.
#
# The blueprints import from `app`, `chat_queue`, `vram_manager`, `discovery` at
# module-import time (e.g. 'from chat_queue import chat_queue_manager').  Because
# of that we MUST inject fake modules into sys.modules BEFORE the first blueprint
# import -- patch() on an already-loaded module attribute is NOT enough.

@pytest.fixture
def app(
    mock_vram_manager,
    mock_chat_queue_manager,
    mock_socketio,
    mock_monitor,
    mock_providers_dict,
    mock_api_error,
    tmp_path,
):
    """Create a minimal Flask app with blueprints registered for testing"""
    from flask import Flask

    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True
    flask_app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    flask_app.config["MAX_CONTENT_LENGTH"] = None

    (tmp_path / "uploads").mkdir(exist_ok=True)
    (tmp_path / "uploads" / "thumbs").mkdir(exist_ok=True)
    (tmp_path / "jobs").mkdir(exist_ok=True)
    (tmp_path / "VERSION").write_text("0.5.0-test")

    # ----- inject fake modules into sys.modules BEFORE blueprint imports ------
    # Remove any previously cached blueprint / dep modules so they reimport
    for mod_name in list(sys.modules):
        if mod_name.startswith("src.api.") or mod_name in (
            "app",
            "chat_queue",
            "vram_manager",
            "discovery",
        ):
            del sys.modules[mod_name]

    # Fake `app` module (blueprints do `from app import ...`)
    fake_app = types.ModuleType("app")
    fake_app.socketio = mock_socketio
    fake_app.api_error = mock_api_error
    fake_app.providers = mock_providers_dict
    fake_app._process_video_direct = MagicMock()
    fake_app._run_dedup = MagicMock()
    fake_app._renumber_frames = MagicMock()
    fake_app._fix_permissions = MagicMock()
    sys.modules["app"] = fake_app

    # Fake `chat_queue` module (llm.py does `from chat_queue import chat_queue_manager`)
    fake_chat_queue = types.ModuleType("chat_queue")
    fake_chat_queue.chat_queue_manager = mock_chat_queue_manager
    sys.modules["chat_queue"] = fake_chat_queue

    # Fake `vram_manager` module (jobs.py does `from vram_manager import vram_manager`)
    fake_vram = types.ModuleType("vram_manager")
    fake_vram.vram_manager = mock_vram_manager
    fake_vram.JobStatus = MagicMock
    sys.modules["vram_manager"] = fake_vram

    # Fake `discovery` module
    mock_discovery = MagicMock()
    mock_discovery.scan.return_value = []
    mock_discovery.get_known_hosts.return_value = ["http://172.16.17.3:4000/v1"]
    mock_discovery_instance = MagicMock()
    mock_discovery_instance.get_known_hosts.return_value = [
        "http://172.16.17.3:4000/v1",
    ]
    mock_discovery_instance.set_known_hosts = MagicMock()
    mock_discovery_instance.scan.return_value = []
    mock_discovery_instance.manager = MagicMock()
    mock_discovery_instance.manager.get_recent_results.return_value = {
        "nvidia_smi": "",
        "nvidia_gpus": [],
        "timestamp": 0,
    }
    fake_discovery = types.ModuleType("discovery")
    fake_discovery.discovery = mock_discovery_instance
    sys.modules["discovery"] = fake_discovery

    # ----- now import blueprints (they will pick up the fakes) -----
    with patch(
        "thumbnail.get_thumbnail_path",
        return_value=str(tmp_path / "uploads" / "thumbs" / "test.jpg"),
    ):
        with patch("thumbnail.ensure_thumbnail"):
            from src.api.jobs import jobs_bp
            from src.api.videos import videos_bp
            from src.api.llm import llm_bp
            from src.api.providers import providers_bp
            from src.api.system import system_bp
            from src.api.results import results_bp
            from src.api.knowledge import knowledge_bp
            from src.api.transcode import transcode_bp

            flask_app.register_blueprint(jobs_bp)
            flask_app.register_blueprint(videos_bp)
            flask_app.register_blueprint(llm_bp)
            flask_app.register_blueprint(providers_bp)
            flask_app.register_blueprint(system_bp)
            flask_app.register_blueprint(results_bp)
            flask_app.register_blueprint(knowledge_bp)
            flask_app.register_blueprint(transcode_bp)

            flask_app.config["_mock_vram_manager"] = mock_vram_manager
            flask_app.config["_mock_chat_queue_manager"] = mock_chat_queue_manager
            flask_app.config["_mock_socketio"] = mock_socketio
            flask_app.config["_mock_monitor"] = mock_monitor
            flask_app.config["_mock_providers"] = mock_providers_dict
            flask_app.config["_mock_discovery"] = mock_discovery_instance

            yield flask_app


@pytest.fixture
def client(app):
    """Create a test client for the Flask app"""
    return app.test_client()


@pytest.fixture
def temp_video_with_frames(tmp_path):
    """Create a temporary video directory with frames and metadata"""
    video_dir = tmp_path / "uploads" / "test_video"
    frames_dir = video_dir / "frames"
    thumbs_dir = frames_dir / "thumbs"

    video_dir.mkdir(parents=True)
    frames_dir.mkdir()
    thumbs_dir.mkdir()

    # Create mock frames
    for i in range(1, 6):
        (frames_dir / f"frame_{i:06d}.jpg").write_bytes(b"fake_image_data")
        (thumbs_dir / f"thumb_{i:06d}.jpg").write_bytes(b"fake_thumb_data")

    # Create metadata
    meta = {"frame_count": 5, "fps": 1.0, "duration": 5.0}
    (video_dir / "frames_meta.json").write_text(json.dumps(meta))

    # Create frames_index
    index = {str(i): float(i - 1) for i in range(1, 6)}
    (video_dir / "frames_index.json").write_text(json.dumps(index))

    # Create transcript
    transcript = {
        "text": "Hello world test transcript",
        "segments": [
            {"start": 0, "end": 2, "text": "Hello"},
            {"start": 2, "end": 5, "text": "world"},
        ],
        "language": "en",
        "whisper_model": "base",
    }
    (video_dir / "transcript.json").write_text(json.dumps(transcript))

    # Create the video file
    video_file = tmp_path / "uploads" / "test_video.mp4"
    video_file.write_bytes(b"\x00\x01\x02\x03" * 1000)

    return {
        "video_dir": video_dir,
        "frames_dir": frames_dir,
        "thumbs_dir": thumbs_dir,
        "video_file": video_file,
        "meta": meta,
        "transcript": transcript,
    }


@pytest.fixture
def temp_job_with_results(tmp_path, sample_results_file):
    """Create a temporary job directory with status, frames, and results"""
    job_dir = tmp_path / "jobs" / "test_job_123"
    output_dir = job_dir / "output"
    job_dir.mkdir(parents=True)
    output_dir.mkdir()

    # Write input.json
    input_config = {
        "job_id": "test_job_123",
        "video_path": str(tmp_path / "uploads" / "test_video.mp4"),
        "provider_type": "litellm",
        "provider_name": "LiteLLM-Proxy",
        "model": "qwen3-27b-q8",
        "params": {"temperature": 0.0},
    }
    (job_dir / "input.json").write_text(json.dumps(input_config))

    # Write status.json
    status = {"status": "running", "stage": "analyzing_frames", "progress": 50}
    (job_dir / "status.json").write_text(json.dumps(status))

    # Write frames.jsonl
    frames_file = job_dir / "frames.jsonl"
    with open(frames_file, "w") as f:
        for i in range(1, 4):
            f.write(
                json.dumps(
                    {
                        "frame_number": i,
                        "total_frames": 10,
                        "timestamp": i * 2.0,
                        "analysis": f"Frame {i} analysis",
                    }
                )
                + "\n"
            )

    # Write synthesis.jsonl
    synthesis_file = job_dir / "synthesis.jsonl"
    with open(synthesis_file, "w") as f:
        for i in range(1, 4):
            f.write(
                json.dumps({"frame_number": i, "combined_analysis": f"Combined frame {i}"})
                + "\n"
            )

    # Write results.json
    (output_dir / "results.json").write_text(json.dumps(sample_results_file))

    return {
        "job_dir": job_dir,
        "output_dir": output_dir,
        "input_config": input_config,
        "status": status,
    }


@pytest.fixture
def mock_openwebui_responses():
    """Mock responses for OpenWebUI API calls"""
    return {
        "test_connection_ok": {
            "status_code": 200,
            "json": {"total": 3, "items": [{"id": "kb1", "name": "Test KB"}]},
        },
        "test_connection_401": {
            "status_code": 401,
            "json": {},
        },
        "list_kbs": {
            "status_code": 200,
            "json": {
                "items": [
                    {"id": "kb1", "name": "Test KB"},
                    {"id": "kb2", "name": "Another KB"},
                ]
            },
        },
        "create_kb": {
            "status_code": 200,
            "json": {"id": "kb_new", "name": "New KB"},
        },
        "upload_file": {
            "status_code": 200,
            "json": {"id": "file_123", "name": "test.txt"},
        },
        "add_file_to_kb": {
            "status_code": 200,
            "json": {"success": True},
        },
    }
