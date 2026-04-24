"""
Standard two-step analysis pipeline (current default).
Phase 1: Vision analysis
Phase 2: Vision + transcript synthesis
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base import AnalysisPipeline

logger = logging.getLogger(__name__)


class StandardTwoStepPipeline(AnalysisPipeline):
    """Standard two-step analysis pipeline (current default)."""
    
    def run(self) -> Dict[str, Any]:
        """Execute standard two-step analysis."""
        logger.info("=== STANDARD TWO-STEP PIPELINE START ===")
        
        # Extract parameters from config
        video_path = Path(self.config["video_path"])
        provider_type = self.config["provider_type"]
        provider_config = self.config["provider_config"]
        model = self.config["model"]
        params = self.config.get("params", {})
        job_id = self.config["job_id"]
        video_frames_dir = self.config.get("video_frames_dir", "")
        
        # Phase 2 (synthesis) configuration
        two_step_enabled = params.get("two_step_enabled", True)
        phase2_provider_type = params.get("phase2_provider_type", "ollama")
        phase2_model = params.get("phase2_model", "qwen3.5:9b-q8-128k")
        phase2_temperature = params.get("phase2_temperature", 0.0)
        phase2_provider_config = params.get("phase2_provider_config", {})
        
        # Update status
        self.update_status({
            "status": "running",
            "stage": "initializing",
            "progress": 0,
            "current_frame": 0,
            "total_frames": 0,
        })
        
        try:
            # Import video_analyzer modules
            logger.info("=== STAGE 0: Importing video_analyzer modules ===")
            from video_analyzer.config import Config
            from video_analyzer.frame import VideoProcessor
            from video_analyzer.analyzer import VideoAnalyzer
            from video_analyzer.prompt import PromptLoader
            
            logger.info("All imports successful")
            
            # Setup paths
            frames_dir = self.output_dir / "frames"
            frames_dir.mkdir(exist_ok=True)
            
            # Create custom config for video_analyzer
            config_data = self._create_video_analyzer_config(
                provider_type, provider_config, model, params,
                phase2_provider_type, phase2_provider_config
            )
            
            # Write temp config
            config_file = self.job_dir / "config.json"
            config_file.write_text(json.dumps(config_data))
            logger.info(f"Wrote config to {config_file}")
            
            # Initialize config
            logger.info("=== STAGE 1: Audio extraction + transcription ===")
            self.update_status({"stage": "extracting_audio", "progress": 5})
            
            # Extract audio and transcribe
            transcript = self._extract_audio_and_transcribe(video_path, config_data)
            
            # Stage 2: Frame extraction
            logger.info("=== STAGE 2: Frame preparation ===")
            self.update_status({"stage": "extracting_frames", "progress": 15})
            
            frames, total_frames = self._extract_frames(
                video_path, video_frames_dir, params, config_data, frames_dir
            )
            
            self.update_status({
                "stage": "analyzing_frames", 
                "progress": 20, 
                "total_frames": total_frames
            })
            
            # Stage 3: Frame analysis
            logger.info("=== STAGE 3: Frame analysis ===")
            frame_analyses = self._analyze_frames(
                frames, total_frames, provider_type, provider_config, model,
                config_data, transcript, params, video_frames_dir
            )
            
            # Stage 4: Video reconstruction
            logger.info("=== STAGE 4: Video reconstruction ===")
            self.update_status({"stage": "reconstructing", "progress": 85})
            
            video_description = self._reconstruct_video(
                frame_analyses, frames, transcript
            )
            
            # Save results
            results = self._save_results(
                job_id, provider_type, model, total_frames, transcript,
                frame_analyses, video_description, params
            )
            
            self.update_status({
                "status": "completed",
                "stage": "complete",
                "progress": 100,
                "results_file": str(self.output_dir / "results.json"),
            })
            
            logger.info("=== STANDARD TWO-STEP PIPELINE COMPLETE ===")
            return results
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            self.update_status({
                "status": "failed",
                "stage": "error",
                "error": str(e),
            })
            raise
    
    def _create_video_analyzer_config(self, provider_type, provider_config, model, params,
                                    phase2_provider_type, phase2_provider_config):
        """Create video_analyzer configuration."""
        config_data = {
            "clients": {
                "default": provider_type if provider_type == "ollama" else "openai_api",
                "temperature": params.get("temperature", 0.0),
            },
            "analysis_pipeline": {
                "two_step_enabled": params.get("two_step_enabled", True),
                "phase2_provider_type": params.get("phase2_provider_type", "ollama"),
                "phase2_model": params.get("phase2_model", "qwen3.5:9b-q8-128k"),
                "phase2_temperature": params.get("phase2_temperature", 0.0),
                "max_concurrent_synthesis": params.get("max_concurrent_synthesis", 3),
            },
            "prompt_dir": "prompts",
            "prompts": [
                {"name": "Frame Analysis", "path": "frame_analysis/frame_analysis.txt"},
                {"name": "Video Reconstruction", "path": "frame_analysis/describe.txt"},
                {"name": "Frame Synthesis", "path": "frame_analysis/synthesis.txt"},
            ],
            "output_dir": str(self.output_dir),
            "frames": {
                "per_minute": params.get("frames_per_minute", 60 / max(params.get("fps", 1), 0.0167)),
                "max_count": params.get("max_frames", 2147483647),
            },
            "audio": {
                "whisper_model": params.get("whisper_model", "large"),
                "language": params.get("language", "en"),
                "device": params.get("device", "gpu"),
            },
            "prompt": params.get("user_prompt", ""),
        }
        
        # Add provider-specific config for Phase 1
        if provider_type == "ollama":
            config_data["clients"]["ollama"] = {
                "url": provider_config.get("url", "http://localhost:11434"),
                "model": model,
            }
        else:  # openrouter
            config_data["clients"]["openai_api"] = {
                "api_key": provider_config["api_key"],
                "api_url": "https://openrouter.ai/api/v1",
                "model": model,
            }
        
        # Add Phase 2 provider config if different from Phase 1
        if phase2_provider_type == "ollama":
            config_data["clients"]["phase2_ollama"] = {
                "url": phase2_provider_config.get("url", "http://localhost:11434"),
                "model": params.get("phase2_model", "qwen3.5:9b-q8-128k"),
            }
        else:  # openrouter
            config_data["clients"]["phase2_openai_api"] = {
                "api_key": phase2_provider_config.get("api_key", ""),
                "api_url": "https://openrouter.ai/api/v1",
                "model": params.get("phase2_model", "meta-llama/llama-3.1-8b-instruct"),
            }
        
        return config_data
    
    def _extract_audio_and_transcribe(self, video_path, config_data):
        """Extract audio and transcribe video."""
        # This is a simplified version - actual implementation would mirror worker.py
        # For now, return None to maintain compatibility
        return None
    
    def _extract_frames(self, video_path, video_frames_dir, params, config_data, frames_dir):
        """Extract frames from video."""
        # This is a simplified version - actual implementation would mirror worker.py
        # Return placeholder for now
        return [], 0
    
    def _analyze_frames(self, frames, total_frames, provider_type, provider_config, model,
                       config_data, transcript, params, video_frames_dir):
        """Analyze frames using LLM."""
        # This is a simplified version - actual implementation would mirror worker.py
        return []
    
    def _reconstruct_video(self, frame_analyses, frames, transcript):
        """Reconstruct video description from frame analyses."""
        # This is a simplified version
        return "Video description placeholder"
    
    def _save_results(self, job_id, provider_type, model, total_frames, transcript,
                     frame_analyses, video_description, params):
        """Save results to file."""
        results = {
            "metadata": {
                "job_id": job_id,
                "provider": provider_type,
                "model": model,
                "frames_processed": total_frames,
                "transcription_successful": transcript is not None,
                "user_prompt": params.get("user_prompt", ""),
            },
            "transcript": transcript if transcript else None,
            "frame_analyses": frame_analyses,
            "video_description": video_description,
        }
        
        results_file = self.output_dir / "results.json"
        results_file.write_text(json.dumps(results, indent=2))
        logger.info(f"Results saved to {results_file}")
        
        return results