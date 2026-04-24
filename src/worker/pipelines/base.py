"""
Base analysis pipeline interface.
All pipelines must implement this interface.
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)


class AnalysisPipeline(ABC):
    """Abstract base class for all analysis pipelines."""

    def __init__(self, job_dir: Path, config: Union[Dict[str, Any], "JobConfig"]):
        self.job_dir = job_dir
        self.output_dir = job_dir / "output"
        self.output_dir.mkdir(exist_ok=True)

        # Accept either raw dict or typed JobConfig
        if hasattr(config, "model_dump"):
            # Pydantic model
            self._typed_config = config
            self.config = config.model_dump()
        else:
            # Raw dict
            self._typed_config = None
            self.config = config

    @property
    def typed_config(self) -> Optional["JobConfig"]:
        """Return typed config if available, otherwise None."""
        return self._typed_config

    def _get_param(self, key: str, default: Any = None) -> Any:
        """Safely get a parameter value, preferring typed config."""
        if self._typed_config is not None:
            # Try nested params first
            val = getattr(self._typed_config.params, key, None)
            if val is not None:
                return val
            # Fallback to top-level typed config attributes
            val = getattr(self._typed_config, key, None)
            if val is not None:
                return val
        # Fallback to raw dict
        params = self.config.get("params", {})
        if key in params:
            return params[key]
        return self.config.get(key, default)

    @abstractmethod
    def run(self) -> Dict[str, Any]:
        """Execute the pipeline and return results."""
        pass

    def update_status(self, updates: Dict[str, Any]):
        """Write status update to job directory."""
        status_file = self.job_dir / "status.json"
        try:
            status = {}
            if status_file.exists():
                status = json.loads(status_file.read_text())
            status.update(updates)
            status["last_update"] = time.time()
            status_file.write_text(json.dumps(status))
        except Exception as e:
            logger.error(f"Failed to update status: {e}")

    def load_transcript(self) -> Optional[Dict[str, Any]]:
        """Load transcript from video metadata directory."""
        video_path = Path(self.config.get("video_path", ""))
        video_frames_dir = self.config.get("video_frames_dir", "")

        # Use shared transcript loading utility for consistent path resolution
        try:
            from src.utils import load_transcript
            transcript = load_transcript(video_path, video_frames_dir)
            if transcript:
                logger.info(f"Loaded transcript with {len(transcript.get('segments', []))} segments")
                return transcript
        except ImportError as e:
            logger.warning(f"Failed to import transcript utilities: {e}")

        # Fallback to original logic for backward compatibility
        transcript_candidates = []
        video_stem = video_path.stem
        base_stem = video_stem.replace("_dedup", "")
        transcript_candidates.append(video_path.parent / video_stem / "transcript.json")
        transcript_candidates.append(video_path.parent / base_stem / "transcript.json")
        if video_frames_dir:
            transcript_candidates.append(Path(video_frames_dir).parent / "transcript.json")

        for transcript_file in transcript_candidates:
            if transcript_file.exists():
                try:
                    transcript = json.loads(transcript_file.read_text())
                    segments = transcript.get("segments", [])
                    logger.info(f"Loaded pre-existing transcript from {transcript_file} ({len(segments)} segments)")
                    return transcript
                except Exception as e2:
                    logger.warning(f"Failed to load {transcript_file}: {e2}")

        logger.info("No transcript found")
        return None
