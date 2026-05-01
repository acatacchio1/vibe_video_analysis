"""Fixtures for integration tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from src.schemas import JobConfig
from src.worker.pipelines.native_video import NativeVideoPipeline


@pytest.fixture
def job_dir(tmp_path):
    d = tmp_path / "jobs" / "nv_integration_job"
    d.mkdir(parents=True)
    (d / "output").mkdir()
    return d


@pytest.fixture
def config_dict(job_dir):
    return {
        "job_id": "nv_integration_job",
        "video_path": str(job_dir / "test_video.mp4"),
        "provider_type": "litellm",
        "provider_config": {"url": "http://172.16.17.3:4000/v1"},
        "model": "vision-best",
        "params": {
            "pipeline_type": "native_video",
            "temperature": 0.0,
            "audio": {"whisper_model": "base", "language": "en", "device": "gpu"},
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
def sample_transcript():
    return {
        "text": "Hello world. This is a test video transcript.",
        "segments": [
            {"text": "Hello world.", "start": 0.0, "end": 2.5},
            {"text": "This is a test", "start": 3.0, "end": 6.0},
            {"text": "video transcript.", "start": 6.5, "end": 10.0},
        ],
        "language": "en",
        "whisper_model": "base",
    }


@pytest.fixture
def typed_config(config_dict):
    return JobConfig(**config_dict)


@pytest.fixture
def pipeline(job_dir, typed_config):
    return NativeVideoPipeline(job_dir, typed_config)


@pytest.fixture
def video_file(job_dir):
    vf = job_dir / "test_video.mp4"
    vf.write_bytes(b"fake_mp4_data")
    return vf
