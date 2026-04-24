#!/usr/bin/env python3
"""
Worker process for video analysis.
Runs as subprocess, communicates via job directory files.

All analysis logic has been moved to pipeline classes in src/worker/pipelines/.
This file is now a thin dispatcher that loads the job config and routes to
the appropriate pipeline via the factory.
"""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, Any

# Setup logging to file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def update_status(job_dir: Path, updates: Dict[str, Any]):
    """Write status update to job directory"""
    status_file = job_dir / "status.json"
    try:
        status = {}
        if status_file.exists():
            status = json.loads(status_file.read_text())
        status.update(updates)
        status["last_update"] = time.time()
        status_file.write_text(json.dumps(status))
    except Exception as e:
        logger.error(f"Failed to update status: {e}")


def run_analysis(job_dir: Path):
    """Run video analysis job by dispatching to the pipeline factory."""
    # Load job config
    input_file = job_dir / "input.json"
    if not input_file.exists():
        logger.error(f"No input.json found at {input_file}")
        raise ValueError("No input.json found")

    logger.info(f"=== JOB START === dir={job_dir}")
    config = json.loads(input_file.read_text())
    logger.info(f"Config keys: {list(config.keys())}")

    params = config.get("params", {})
    pipeline_type = params.get("pipeline_type", "standard_two_step")

    logger.info(f"Using pipeline: {pipeline_type}")

    from src.worker.pipelines import create_pipeline

    pipeline = create_pipeline(pipeline_type, job_dir, config)

    update_status(
        job_dir,
        {
            "status": "running",
            "stage": "initializing",
            "progress": 0,
            "current_frame": 0,
            "total_frames": 0,
            "pipeline": pipeline_type,
        },
    )

    results = pipeline.run()
    logger.info(f"=== JOB COMPLETE === Pipeline: {pipeline_type}")
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: worker.py <job_directory>")
        sys.exit(1)

    job_dir = Path(sys.argv[1])
    run_analysis(job_dir)
