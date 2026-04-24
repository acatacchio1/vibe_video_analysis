"""
Pipeline factory and registry.
"""

from pathlib import Path
from typing import Dict, Any, Type

from .base import AnalysisPipeline
from .standard_two_step import StandardTwoStepPipeline
from .linkedin_extraction import LinkedInExtractionPipeline

# Registry of available pipelines
PIPELINE_REGISTRY = {
    "linkedin_extraction": LinkedInExtractionPipeline,
}


def create_pipeline(pipeline_type: str, job_dir: Path, config: Dict[str, Any]) -> AnalysisPipeline:
    """Create a pipeline instance based on type."""
    pipeline_class = PIPELINE_REGISTRY.get(pipeline_type)
    if not pipeline_class:
        raise ValueError(f"Unknown pipeline type: {pipeline_type}. "
                       f"Available: {list(PIPELINE_REGISTRY.keys())}")
    
    return pipeline_class(job_dir, config)


def get_available_pipelines() -> Dict[str, str]:
    """Get available pipeline types and their descriptions."""
    return {
        "linkedin_extraction": "LinkedIn Short-Form Video Extraction",
    }


__all__ = [
    "AnalysisPipeline",
    "StandardTwoStepPipeline", 
    "LinkedInExtractionPipeline",
    "create_pipeline",
    "get_available_pipelines",
]