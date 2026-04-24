"""
Worker package.

The active worker entry point is worker.py at the repository root,
which dispatches to pipeline classes in src.worker.pipelines.

src.worker.main is legacy code kept for reference only.
"""

from src.worker.pipelines import (
    AnalysisPipeline,
    create_pipeline,
    get_available_pipelines,
    StandardTwoStepPipeline,
    LinkedInExtractionPipeline,
)

__all__ = [
    "AnalysisPipeline",
    "create_pipeline",
    "get_available_pipelines",
    "StandardTwoStepPipeline",
    "LinkedInExtractionPipeline",
]
