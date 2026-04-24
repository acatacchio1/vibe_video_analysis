"""
Basic tests for pipeline factory and Pydantic schemas.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.schemas import JobConfig, AnalysisParams, AudioConfig, FrameConfig, Phase2Config
from src.worker.pipelines import create_pipeline, get_available_pipelines


def test_get_available_pipelines():
    pipelines = get_available_pipelines()
    assert "standard_two_step" in pipelines
    assert "linkedin_extraction" in pipelines


def test_job_config_defaults():
    cfg = JobConfig(
        job_id="test",
        video_path="/tmp/test.mp4",
        provider_type="ollama",
        model="llama3",
    )
    assert cfg.params.pipeline_type == "standard_two_step"
    assert cfg.params.audio.whisper_model == "large"
    assert cfg.params.audio.compute_type == "float16"
    assert cfg.params.frames.frames_per_minute == 60.0
    assert cfg.params.linkedin is None


def test_job_config_cpu_compute_type():
    cfg = JobConfig(
        job_id="test",
        video_path="/tmp/test.mp4",
        provider_type="ollama",
        model="llama3",
        params={"device": "cpu"},
    )
    assert cfg.params.audio.compute_type == "int8"


def test_legacy_field_mapping():
    cfg = JobConfig(
        job_id="test",
        video_path="/tmp/test.mp4",
        provider_type="ollama",
        model="llama3",
        params={
            "whisper_model": "base",
            "language": "es",
            "two_step_enabled": False,
            "phase2_model": "qwen2",
        },
    )
    assert cfg.params.audio.whisper_model == "base"
    assert cfg.params.audio.language == "es"
    assert cfg.params.phase2.enabled is False
    assert cfg.params.phase2.model == "qwen2"


def test_explicit_nested_override():
    cfg = JobConfig(
        job_id="test",
        video_path="/tmp/test.mp4",
        provider_type="ollama",
        model="llama3",
        params={
            "audio": {"whisper_model": "large"},
            "whisper_model": "base",  # should be ignored
        },
    )
    assert cfg.params.audio.whisper_model == "large"


def test_linkedin_auto_created():
    cfg = JobConfig(
        job_id="test",
        video_path="/tmp/test.mp4",
        provider_type="ollama",
        model="llama3",
        params={"pipeline_type": "linkedin_extraction"},
    )
    assert cfg.params.linkedin is not None
    assert "hook_text" in cfg.params.linkedin.extraction_targets


def test_create_standard_pipeline():
    job_dir = Path("/tmp/test_std_pipeline")
    job_dir.mkdir(exist_ok=True)
    config = {
        "job_id": "test",
        "video_path": "/tmp/test.mp4",
        "provider_type": "ollama",
        "model": "llama3",
        "provider_config": {"url": "http://localhost:11434"},
        "params": {"whisper_model": "base"},
    }
    p = create_pipeline("standard_two_step", job_dir, config)
    assert p.typed_config is not None
    assert p.typed_config.params.audio.whisper_model == "base"


def test_create_linkedin_pipeline():
    job_dir = Path("/tmp/test_li_pipeline")
    job_dir.mkdir(exist_ok=True)
    config = {
        "job_id": "test",
        "video_path": "/tmp/test.mp4",
        "provider_type": "ollama",
        "model": "llama3",
        "provider_config": {"url": "http://localhost:11434"},
        "params": {"pipeline_type": "linkedin_extraction"},
    }
    p = create_pipeline("linkedin_extraction", job_dir, config)
    assert p.typed_config is not None
    assert p.typed_config.params.linkedin is not None


if __name__ == "__main__":
    test_get_available_pipelines()
    test_job_config_defaults()
    test_job_config_cpu_compute_type()
    test_legacy_field_mapping()
    test_explicit_nested_override()
    test_linkedin_auto_created()
    test_create_standard_pipeline()
    test_create_linkedin_pipeline()
    print("All tests passed!")
