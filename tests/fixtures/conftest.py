# Video Analyzer Web Test Fixtures

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import sys
import os

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
                "total_vram": 10 * (1024**3),  # 10GB
                "used_vram": 2 * (1024**3),  # 2GB used
                "free_vram": 8 * (1024**3),  # 8GB free
            },
            {
                "index": 1,
                "name": "NVIDIA GeForce RTX 3080",
                "total_vram": 10 * (1024**3),  # 10GB
                "used_vram": 4 * (1024**3),  # 4GB used
                "free_vram": 6 * (1024**3),  # 6GB free
            },
        ]
    }


@pytest.fixture
def sample_job_config():
    """Sample job configuration for testing"""
    return {
        "job_id": "test_job_123",
        "video_path": "/app/uploads/test_video.mp4",
        "provider_type": "ollama",
        "provider_name": "Ollama-Local",
        "provider_config": {"url": "http://localhost:11434"},
        "model": "llava:7b",
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
            "provider": "ollama",
            "model": "llava:7b",
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
        "provider_type": "ollama",
        "model_id": "llama3:8b",
        "status": "pending",
        "queue_position": 1,
        "prompt": "Summarize this",
        "created_at": 1234567890.0,
    }


@pytest.fixture
def mock_ollama_client():
    """Mock Ollama client for testing"""
    client = MagicMock()
    client.generate.return_value = {
        "response": "Test response",
        "done": True,
        "eval_count": 100,
        "prompt_eval_count": 400,
    }
    return client


@pytest.fixture
def mock_video_file(temp_upload_dir):
    """Create a minimal mock video file"""
    video_path = temp_upload_dir / "test_video.mp4"
    # Create a small binary file (not a real video, but works for path testing)
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
