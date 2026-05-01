"""Fixtures for NativeVideoPipeline unit tests."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def native_video_job_dir(tmp_path):
    """Create a temporary job directory for NativeVideoPipeline testing."""
    job_dir = tmp_path / "jobs" / "nv_test_job"
    job_dir.mkdir(parents=True)
    (job_dir / "output").mkdir()
    return job_dir


@pytest.fixture
def native_video_config(native_video_job_dir):
    """Create a raw dict config for NativeVideoPipeline."""
    return {
        "job_id": "nv_test_job",
        "video_path": str(native_video_job_dir / "test_video.mp4"),
        "provider_type": "litellm",
        "provider_name": "LiteLLM-Proxy",
        "provider_config": {"url": "http://172.16.17.3:4000/v1"},
        "model": "vision-best",
        "params": {
            "temperature": 0.0,
            "pipeline_type": "native_video",
            "audio": {
                "whisper_model": "large",
                "language": "en",
                "device": "gpu",
            },
            "phase2": {
                "enabled": True,
                "provider_type": "litellm",
                "model": "qwen3-27b-q8",
                "temperature": 0.0,
                "provider_config": {"url": "http://172.16.17.3:4000/v1"},
            },
        },
    }


@pytest.fixture
def native_video_pipeline(native_video_job_dir, native_video_config):
    """Create a NativeVideoPipeline instance with typed config."""
    from src.worker.pipelines.native_video import NativeVideoPipeline
    from src.schemas import JobConfig

    typed_config = JobConfig(**native_video_config)
    pipeline = NativeVideoPipeline(native_video_job_dir, typed_config)
    return pipeline


@pytest.fixture
def sample_transcript():
    """Sample transcript with segments having start/end times."""
    return {
        "text": "Hello world. This is a test video.",
        "segments": [
            {"start": 0.0, "end": 3.0, "text": "Hello world"},
            {"start": 3.5, "end": 8.0, "text": "This is a test"},
            {"start": 8.5, "end": 12.0, "text": "video"},
        ],
        "language": "en",
        "whisper_model": "large",
    }
