"""
Pipeline factory and registry.
"""

from pathlib import Path
from typing import Dict, Any, Type, Union

from .base import AnalysisPipeline
from .standard_two_step import StandardTwoStepPipeline
from .linkedin_extraction import LinkedInExtractionPipeline
from .native_video import NativeVideoPipeline

# Registry of available pipelines
PIPELINE_REGISTRY = {
    "linkedin_extraction": LinkedInExtractionPipeline,
    "native_video": NativeVideoPipeline,
    "standard_two_step": StandardTwoStepPipeline,
}


def create_pipeline(
    pipeline_type: str,
    job_dir: Path,
    config: Union[Dict[str, Any], "JobConfig"],
    use_typed_config: bool = True,
) -> AnalysisPipeline:
    """Create a pipeline instance based on type.

    Args:
        pipeline_type: The type of pipeline to create.
        job_dir: Directory for job artifacts.
        config: Raw dict or typed JobConfig.
        use_typed_config: If True and config is a dict, build a JobConfig
            and pass both to the pipeline.

    Returns:
        Configured pipeline instance.
    """
    pipeline_class = PIPELINE_REGISTRY.get(pipeline_type)
    if not pipeline_class:
        raise ValueError(
            f"Unknown pipeline type: {pipeline_type}. "
            f"Available: {list(PIPELINE_REGISTRY.keys())}"
        )

    if use_typed_config and isinstance(config, dict):
        try:
            from src.schemas import JobConfig

            typed_config = JobConfig(**config)
            return pipeline_class(job_dir, typed_config)
        except Exception as e:
            # Log but don't fail — raw dict is still supported
            import logging

            logging.getLogger(__name__).warning(
                f"Failed to build typed JobConfig: {e}. Using raw dict."
            )

    return pipeline_class(job_dir, config)


def get_available_pipelines() -> Dict[str, str]:
    """Get available pipeline types and their descriptions."""
    return {
        "linkedin_extraction": "LinkedIn Short-Form Video Extraction",
        "native_video": "Native Video (qwen3-vl) for Temporal Analysis",
        "standard_two_step": "Standard Two-Step Vision + Synthesis Analysis",
    }


__all__ = [
    "AnalysisPipeline",
    "StandardTwoStepPipeline",
    "LinkedInExtractionPipeline",
    "NativeVideoPipeline",
    "create_pipeline",
    "get_available_pipelines",
]
