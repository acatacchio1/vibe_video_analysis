"""
Pydantic schemas for video analysis configuration.

Provides typed, validated configuration models for pipelines,
replacing raw dict access with structured data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class ProviderConfig(BaseModel):
    """Base provider configuration."""

    url: Optional[str] = None
    api_key: Optional[str] = None

    @field_validator("api_key", mode="before")
    @classmethod
    def _blank_to_none(cls, v: Any) -> Any:
        if v == "":
            return None
        return v


class LiteLLMProviderConfig(ProviderConfig):
    """LiteLLM-specific provider configuration."""

    type: Literal["litellm"] = "litellm"
    model: str = ""


class OpenRouterProviderConfig(ProviderConfig):
    """OpenRouter-specific provider configuration."""

    type: Literal["openrouter"] = "openrouter"
    model: str = ""


ProviderConfigUnion = Union[LiteLLMProviderConfig, OpenRouterProviderConfig]


class AudioConfig(BaseModel):
    """Audio extraction and transcription configuration."""

    whisper_model: str = "large"
    language: str = "en"
    device: Literal["gpu", "cpu"] = "gpu"
    compute_type: Optional[str] = None

    @model_validator(mode="after")
    def _default_compute_type(self) -> "AudioConfig":
        if self.compute_type is None:
            self.compute_type = "float16" if self.device == "gpu" else "int8"
        return self


class FrameConfig(BaseModel):
    """Frame extraction and sampling configuration."""

    fps: float = Field(default=1.0, gt=0)
    frames_per_minute: float = Field(default=60.0, gt=0)
    max_frames: int = Field(default=2147483647, gt=0)
    start_frame: int = Field(default=0, ge=0)
    end_frame: Optional[int] = None
    similarity_threshold: float = Field(default=10.0, ge=0)


class Phase2Config(BaseModel):
    """Phase 2 synthesis configuration."""

    enabled: bool = Field(default=True, alias="two_step_enabled")
    provider_type: Literal["litellm", "openrouter"] = "litellm"
    model: str = "qwen3.5:9b-q8-128k"
    temperature: float = Field(default=0.0, ge=0, le=2)
    provider_config: ProviderConfig = Field(default_factory=ProviderConfig)
    max_concurrent_synthesis: int = Field(default=3, ge=1)

    model_config = {"populate_by_name": True}

    @field_validator("provider_config", mode="before")
    @classmethod
    def _coerce_dict(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return ProviderConfig(**v)
        return v


class LinkedInConfig(BaseModel):
    """LinkedIn short-form video extraction configuration."""

    scoring_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "hook_strength": 0.25,
            "engagement_potential": 0.20,
            "visual_clarity": 0.20,
            "audio_quality": 0.15,
            "text_readability": 0.15,
            "trending_potential": 0.05,
        }
    )
    extraction_targets: List[str] = Field(
        default_factory=lambda: [
            "hook_text",
            "key_message",
            "call_to_action",
            "visual_elements",
            "audio_transcript",
            "engagement_hooks",
        ]
    )


class AnalysisParams(BaseModel):
    """Analysis parameters passed in job config."""

    temperature: float = Field(default=0.0, ge=0, le=2)
    user_prompt: str = ""
    pipeline_type: Literal["standard_two_step", "linkedin_extraction"] = "standard_two_step"

    # Nested configs
    audio: AudioConfig = Field(default_factory=AudioConfig)
    frames: FrameConfig = Field(default_factory=FrameConfig)
    phase2: Phase2Config = Field(default_factory=Phase2Config)
    linkedin: Optional[LinkedInConfig] = None

    # Legacy flat fields (for backward compatibility with frontend)
    # These are kept so Pydantic accepts them, but they're mapped into nested configs
    # by the model_validator below.
    whisper_model: Optional[str] = None
    language: Optional[str] = None
    device: Optional[Literal["gpu", "cpu"]] = None
    fps: Optional[float] = None
    frames_per_minute: Optional[float] = None
    max_frames: Optional[int] = None
    start_frame: Optional[int] = None
    end_frame: Optional[int] = None
    similarity_threshold: Optional[float] = None
    two_step_enabled: Optional[bool] = None
    phase2_provider_type: Optional[str] = None
    phase2_model: Optional[str] = None
    phase2_temperature: Optional[float] = None
    phase2_provider_config: Optional[Dict[str, Any]] = None
    linkedin_config: Optional[Dict[str, Any]] = None
    duration: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_to_nested(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        data = dict(data)  # shallow copy so we don't mutate the caller's dict

        # Build audio config from legacy fields
        if "audio" not in data or data["audio"] is None:
            audio_kwargs: Dict[str, Any] = {}
            for key in ("whisper_model", "language", "device"):
                if key in data and data[key] is not None:
                    audio_kwargs[key] = data[key]
            if audio_kwargs:
                data["audio"] = AudioConfig(**audio_kwargs)

        # Build frames config from legacy fields
        if "frames" not in data or data["frames"] is None:
            frame_kwargs: Dict[str, Any] = {}
            for key in ("fps", "frames_per_minute", "max_frames", "start_frame", "end_frame", "similarity_threshold"):
                if key in data and data[key] is not None:
                    frame_kwargs[key] = data[key]
            if frame_kwargs:
                data["frames"] = FrameConfig(**frame_kwargs)

        # Build phase2 config from legacy fields
        if "phase2" not in data or data["phase2"] is None:
            p2_kwargs: Dict[str, Any] = {}
            if "two_step_enabled" in data and data["two_step_enabled"] is not None:
                p2_kwargs["enabled"] = data["two_step_enabled"]
            if "phase2_provider_type" in data and data["phase2_provider_type"] is not None:
                p2_kwargs["provider_type"] = data["phase2_provider_type"]
            if "phase2_model" in data and data["phase2_model"] is not None:
                p2_kwargs["model"] = data["phase2_model"]
            if "phase2_temperature" in data and data["phase2_temperature"] is not None:
                p2_kwargs["temperature"] = data["phase2_temperature"]
            if "phase2_provider_config" in data and data["phase2_provider_config"] is not None:
                p2_kwargs["provider_config"] = data["phase2_provider_config"]
            if p2_kwargs:
                data["phase2"] = Phase2Config(**p2_kwargs)

        # Build linkedin config from legacy fields
        if "linkedin" not in data or data["linkedin"] is None:
            if "linkedin_config" in data and data["linkedin_config"] is not None:
                data["linkedin"] = LinkedInConfig(**data["linkedin_config"])
            elif data.get("pipeline_type") == "linkedin_extraction":
                data["linkedin"] = LinkedInConfig()

        return data


class JobConfig(BaseModel):
    """Top-level job configuration passed to the worker."""

    job_id: str
    video_path: str
    provider_type: Literal["litellm", "openrouter"]
    provider_name: str = ""
    provider_config: ProviderConfig = Field(default_factory=ProviderConfig)
    model: str
    video_frames_dir: str = ""
    params: AnalysisParams = Field(default_factory=AnalysisParams)
    app_url: Optional[str] = None

    @field_validator("provider_config", mode="before")
    @classmethod
    def _coerce_provider_config(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return ProviderConfig(**v)
        return v

    @field_validator("params", mode="before")
    @classmethod
    def _coerce_params(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return AnalysisParams(**v)
        return v

    # Convenience properties
    @property
    def video_path_obj(self) -> Path:
        return Path(self.video_path)

    @property
    def frames_dir_obj(self) -> Optional[Path]:
        if self.video_frames_dir:
            return Path(self.video_frames_dir)
        return None


__all__ = [
    "AudioConfig",
    "FrameConfig",
    "Phase2Config",
    "LinkedInConfig",
    "AnalysisParams",
    "JobConfig",
    "ProviderConfig",
    "LiteLLMProviderConfig",
    "OpenRouterProviderConfig",
    "ProviderConfigUnion",
]
