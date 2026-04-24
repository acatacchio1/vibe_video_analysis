"""
LinkedIn short-form video extraction pipeline - CLEAN VERSION.
Three stages: Frame analysis → Segment fusion → RAG extraction & ranking.
"""

import json
import logging
import subprocess
import time
import types
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .base import AnalysisPipeline
from .linkedin_config import LinkedInConfig, validate_duration
from .linkedin_helpers import (
    load_linkedin_prompt, parse_json_response, safe_get_transcript_text,
    safe_get_transcript_segments, get_transcript_context, format_timestamp
)

logger = logging.getLogger(__name__)


class LinkedInExtractionPipeline(AnalysisPipeline):
    """LinkedIn short-form video extraction pipeline."""
    
    def __init__(self, job_dir: Path, config: Dict[str, Any]):
        super().__init__(job_dir, config)
        # Prefer typed config linkedin settings; fall back to raw dict
        if self.typed_config and self.typed_config.params.linkedin:
            self.linkedin_config = LinkedInConfig(
                self.typed_config.params.linkedin.model_dump()
            )
        else:
            self.linkedin_config = LinkedInConfig(
                config.get("params", {}).get("linkedin_config", {})
            )

    def run(self) -> Dict[str, Any]:
        """Execute LinkedIn extraction pipeline."""
        logger.info("=== LINKEDIN EXTRACTION PIPELINE START ===")
        logger.info(f"LinkedIn config: {json.dumps(self.linkedin_config.to_dict(), indent=2)}")

        # Use typed config when available
        cfg = self.typed_config
        if cfg is None:
            video_path = Path(self.config["video_path"])
            provider_type = self.config["provider_type"]
            provider_config = self.config["provider_config"]
            model = self.config["model"]
            params = self.config.get("params", {})
            job_id = self.config["job_id"]
            video_frames_dir = self.config.get("video_frames_dir", "")
        else:
            video_path = cfg.video_path_obj
            provider_type = cfg.provider_type
            provider_config = cfg.provider_config.model_dump()
            model = cfg.model
            params = cfg.params.model_dump()
            job_id = cfg.job_id
            video_frames_dir = cfg.video_frames_dir
        
        # Update status
        self.update_status({
            "status": "running",
            "stage": "initializing",
            "progress": 0,
            "current_frame": 0,
            "total_frames": 0,
            "pipeline": "linkedin_extraction",
        })
        
        try:
            # Stage 1: Frame analysis with LinkedIn-specific prompt
            logger.info("=== STAGE 1: LinkedIn Frame Analysis ===")
            self.update_status({"stage": "frame_analysis", "progress": 10})
            
            frame_analyses = self._analyze_frames_linkedin(
                video_path, video_frames_dir, provider_type, 
                provider_config, model, params
            )
            
            # Stage 2: Load transcript and fuse with frame analyses
            logger.info("=== STAGE 2: Transcript & Frame Fusion ===")
            self.update_status({"stage": "segment_fusion", "progress": 40})

            transcript = self.load_transcript()
            transcript_text = safe_get_transcript_text(transcript)
            if transcript_text:
                self.update_status({"transcript": transcript_text})

            fused_segments = self._fuse_segments(frame_analyses, transcript)
            
            # Stage 3: RAG extraction and ranking
            logger.info("=== STAGE 3: RAG Extraction & Ranking ===")
            self.update_status({"stage": "rag_extraction", "progress": 70})
            
            ranked_segments = self._extract_and_rank_segments(fused_segments)
            
            # Stage 4: Generate clips and final results
            logger.info("=== STAGE 4: Clip Generation & Results ===")
            self.update_status({"stage": "clip_generation", "progress": 90})
            
            results = self._generate_results(job_id, ranked_segments, video_path, params)

            # Build a human-readable summary for live display
            summary = results.get("summary", {})
            desc_parts = [
                f"LinkedIn Extraction Complete",
                f"Total segments: {summary.get('total_segments', 0)}",
                f"Selected for clips: {summary.get('selected_for_clips', 0)}",
            ]
            if summary.get("top_segments"):
                desc_parts.append("Top segments:")
                for seg in summary["top_segments"][:3]:
                    desc_parts.append(
                        f"  - {seg.get('segment_id', 'unknown')}: score {seg.get('total_score', 0)}, hook {seg.get('hook_strength', 'unknown')}"
                    )
            video_description = "\n".join(desc_parts)

            self.update_status({
                "status": "completed",
                "stage": "complete",
                "progress": 100,
                "results_file": str(self.output_dir / "linkedin_results.json"),
                "video_description": video_description,
            })
            
            logger.info("=== LINKEDIN EXTRACTION PIPELINE COMPLETE ===")
            return results
            
        except Exception as e:
            logger.error(f"LinkedIn pipeline failed: {e}", exc_info=True)
            self.update_status({
                "status": "failed",
                "stage": "error",
                "error": str(e),
            })
            raise
    
    def load_transcript(self) -> Optional[Dict[str, Any]]:
        """Load transcript for the video."""
        video_path = Path(self.config.get("video_path", ""))
        video_frames_dir = self.config.get("video_frames_dir", "")
        
        try:
            # Use shared transcript loading utility for consistent path resolution
            from src.utils import load_transcript
            transcript = load_transcript(str(video_path), video_frames_dir)
            
            if transcript:
                segments = safe_get_transcript_segments(transcript) or []
                logger.info(f"Loaded transcript with {len(segments)} segments")
            else:
                logger.info("No transcript found")
            
            return transcript
            
        except ImportError as e:
            logger.warning(f"Failed to import transcript utilities: {e}")
            # Fallback to manual loading
            video_stem = video_path.stem
            base_stem = video_stem.replace("_dedup", "")
            
            # Try common transcript locations
            transcript_candidates = [
                video_path.parent / video_stem / "transcript.json",
                video_path.parent / base_stem / "transcript.json",
            ]
            
            if video_frames_dir:
                transcript_candidates.append(Path(video_frames_dir).parent / "transcript.json")
            
            for transcript_file in transcript_candidates:
                if transcript_file.exists():
                    try:
                        transcript = json.loads(transcript_file.read_text())
                        segments = safe_get_transcript_segments(transcript) or []
                        logger.info(f"Loaded transcript from {transcript_file} ({len(segments)} segments)")
                        return transcript
                    except Exception as e2:
                        logger.warning(f"Failed to load {transcript_file}: {e2}")
            
            logger.info("No transcript found")
            return None
    
    def _analyze_frames_linkedin(self, video_path: Path, video_frames_dir: str,
                               provider_type: str, provider_config: Dict[str, Any],
                               model: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze frames using LinkedIn-specific prompt (Prompt 1)."""
        logger.info("=== LinkedIn Frame Analysis ===")
        
        # Update status
        self.update_status({"stage": "linkedin_frame_analysis", "progress": 20})
        
        # Load LinkedIn prompt
        frame_prompt = load_linkedin_prompt("frame_analysis")
        logger.info(f"Loaded LinkedIn frame analysis prompt ({len(frame_prompt)} chars)")
        
        # Extract frames
        frames, total_frames = self._extract_frames_linkedin(video_path, video_frames_dir, params)
        
        if total_frames == 0:
            logger.warning("No frames extracted")
            return []
        
        self.update_status({"total_frames": total_frames, "current_frame": 0})
        
        # Load transcript
        transcript = self.load_transcript()
        transcript_segments = safe_get_transcript_segments(transcript) or []
        
        # Initialize client
        client = self._initialize_client(provider_type, provider_config, model, params)
        
        # Analyze each frame
        frame_analyses = []
        
        for i, frame in enumerate(frames):
            self.update_status({"current_frame": i + 1, "progress": 20 + int((i + 1) / total_frames * 30)})
            
            logger.info(f"Analyzing LinkedIn frame {i+1}/{total_frames}: {frame['path']}")
            
            # Get transcript context for this frame
            recent_context, prior_context = get_transcript_context(
                transcript_segments, frame['timestamp']
            )
            
            # Build prompt with frame info and transcript context
            prompt = self._build_linkedin_frame_prompt(
                frame_prompt, frame, recent_context, prior_context
            )
            
            # Send to LLM
            analysis_response = self._call_llm_for_frame(
                client, provider_type, model, prompt, frame['path'], params
            )
            
            # Parse JSON response
            frame_analysis = parse_json_response(analysis_response)
            
            # Add metadata
            frame_analysis.update({
                "frame_number": i + 1,
                "timestamp": frame['timestamp'],
                "timestamp_formatted": format_timestamp(frame['timestamp']),
                "frame_path": str(frame['path']),
                "recent_transcript": recent_context,
                "prior_transcript": prior_context,
            })
            
            frame_analyses.append(frame_analysis)

            # Write to LinkedIn-specific frames log
            frames_file = self.job_dir / "linkedin_frames.jsonl"
            with open(frames_file, "a") as f:
                f.write(json.dumps(frame_analysis) + "\n")

            # Also write to standard frames.jsonl so monitor_job emits live frame_analysis events
            transcript_ctx = ""
            if recent_context:
                transcript_ctx += f"RECENT: {recent_context}"
            if prior_context:
                transcript_ctx += f"\nPRIOR: {prior_context}" if transcript_ctx else f"PRIOR: {prior_context}"

            standard_frame_entry = {
                "frame_number": i + 1,
                "original_frame": frame.get("original_number", i + 1),
                "timestamp": frame["timestamp"],
                "video_ts": frame["timestamp"],
                "corrected_ts": frame["timestamp"],
                "original_ts": frame["timestamp"],
                "analysis": self._format_linkedin_analysis_markdown(frame_analysis),
                "response": self._format_linkedin_analysis_markdown(frame_analysis),
                "transcript_context": transcript_ctx,
            }
            standard_frames_file = self.job_dir / "frames.jsonl"
            with open(standard_frames_file, "a") as f:
                f.write(json.dumps(standard_frame_entry) + "\n")

            logger.info(f"Frame {i+1} analysis complete")
        
        logger.info(f"LinkedIn frame analysis complete: {len(frame_analyses)} frames")
        return frame_analyses
    
    def _extract_frames_linkedin(self, video_path: Path, video_frames_dir: str,
                                params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
        """Extract frames for LinkedIn analysis."""
        logger.info("Extracting frames for LinkedIn analysis...")
        
        pre_extracted_dir = Path(video_frames_dir) if video_frames_dir else None
        use_pre_extracted = (
            pre_extracted_dir
            and pre_extracted_dir.exists()
            and any(pre_extracted_dir.glob("frame_*.jpg"))
        )
        
        frames = []
        
        if use_pre_extracted:
            # Load pre-extracted frames
            all_frame_files = sorted(pre_extracted_dir.glob("frame_*.jpg"))
            total_available = len(all_frame_files)
            
            # Get metadata
            meta_path = pre_extracted_dir.parent / "frames_meta.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                except Exception as e:
                    logger.warning(f"Failed to parse frames_meta.json: {e}")
            
            # Load frames_index for timestamps
            frames_index = {}
            frames_index_path = pre_extracted_dir.parent / "frames_index.json"
            if frames_index_path.exists():
                try:
                    frames_index = json.loads(frames_index_path.read_text())
                except Exception as e:
                    logger.warning(f"Failed to parse frames_index.json: {e}")
            
            video_fps = meta.get("fps", 1)
            
            # Apply frame selection
            start_frame = params.get("start_frame", 0) or 0
            end_frame = params.get("end_frame") or total_available
            
            start_frame = max(0, min(start_frame, total_available - 1))
            end_frame = max(start_frame + 1, min(end_frame, total_available))
            
            selected_files = all_frame_files[start_frame:end_frame]
            
            # Apply frame rate reduction if needed
            fpm = params.get("frames_per_minute", 60)
            step = 1
            if video_fps > 0 and fpm < (video_fps * 60):
                step = max(1, int(video_fps * 60 / fpm))
                selected_files = selected_files[::step]
            
            # Create frame objects
            for i, fp in enumerate(selected_files):
                original_index = start_frame + i * step
                frame_num = original_index + 1
                
                # Get timestamp
                if frames_index and str(frame_num) in frames_index:
                    timestamp = frames_index[str(frame_num)]
                else:
                    timestamp = original_index / video_fps if video_fps > 0 else float(i)
                
                frames.append({
                    "path": fp,
                    "number": i + 1,
                    "original_number": frame_num,
                    "timestamp": timestamp,
                    "score": 0,
                })
            
            logger.info(f"Using {len(frames)} pre-extracted frames")
            
        else:
            # Extract frames using VideoProcessor
            try:
                from video_analyzer.frame import VideoProcessor
                
                frames_dir = self.output_dir / "frames"
                frames_dir.mkdir(exist_ok=True)
                
                processor = VideoProcessor(video_path, frames_dir, "linkedin")
                
                # Extract keyframes
                video_frames = processor.extract_keyframes(
                    frames_per_minute=params.get("frames_per_minute", 60),
                    duration=params.get("duration"),
                    max_frames=params.get("max_frames", 2147483647),
                    similarity_threshold=params.get("similarity_threshold", 10),
                )
                
                # Convert to our format
                for i, frame in enumerate(video_frames):
                    frames.append({
                        "path": Path(frame.path),
                        "number": i + 1,
                        "original_number": i + 1,
                        "timestamp": getattr(frame, 'timestamp', float(i)),
                        "score": getattr(frame, 'score', 0),
                    })
                
                logger.info(f"Extracted {len(frames)} frames with VideoProcessor")
                
            except ImportError as e:
                logger.error(f"Failed to import VideoProcessor: {e}")
                return [], 0
        
        return frames, len(frames)
    
    def _initialize_client(self, provider_type: str, provider_config: Dict[str, Any],
                          model: str, params: Dict[str, Any]):
        """Initialize LLM client."""
        if provider_type == "ollama":
            from video_analyzer.clients.ollama import OllamaClient
            
            ollama_url = provider_config.get("url", "http://localhost:11434")
            client = OllamaClient(ollama_url)
            
            # Patch to use think:false (same as worker.py)
            import functools
            
            _chat_url = f"{ollama_url.rstrip('/')}/api/chat"
            
            @functools.wraps(client.generate)
            def _patched_generate(self_inner, prompt, image_path=None, stream=False, 
                                 model=model, temperature=None, num_predict=2048):
                import requests as _req
                
                msg = {"role": "user", "content": prompt}
                if image_path:
                    msg["images"] = [self_inner.encode_image(image_path)]
                
                data = {
                    "model": model,
                    "messages": [msg],
                    "stream": False,
                    "think": False,
                    "options": {
                        "temperature": params.get("temperature", 0.0),
                        "num_predict": max(num_predict, 2048),
                    },
                }
                
                resp = _req.post(_chat_url, json=data, timeout=300)
                resp.raise_for_status()
                d = resp.json()
                
                return {
                    "response": d.get("message", {}).get("content", ""),
                    "done": d.get("done", True),
                    "eval_count": d.get("eval_count", 0),
                    "prompt_eval_count": d.get("prompt_eval_count", 0),
                }
            
            client.generate = types.MethodType(_patched_generate, client)
            return client
            
        else:  # openrouter
            from video_analyzer.clients.generic_openai_api import GenericOpenAIAPIClient
            
            api_key = provider_config.get("api_key", "")
            client = GenericOpenAIAPIClient(api_key, "https://openrouter.ai/api/v1")
            return client
    
    def _build_linkedin_frame_prompt(self, base_prompt: str, frame: Dict[str, Any],
                                    recent_context: str, prior_context: str) -> str:
        """Build LinkedIn frame analysis prompt with context."""
        prompt = base_prompt
        
        # Add frame metadata
        prompt = prompt.replace("{TIMESTAMP}", f"{frame['timestamp']:.2f}")
        prompt = prompt.replace("{TIMESTAMP_FORMATTED}", format_timestamp(frame['timestamp']))
        prompt = prompt.replace("{FRAME_NUMBER}", str(frame['number']))
        
        # Add transcript context if available
        if recent_context:
            prompt = prompt.replace("{TRANSCRIPT_RECENT}", recent_context)
        else:
            prompt = prompt.replace("{TRANSCRIPT_RECENT}", "No recent transcript available (within 30 seconds)")
        
        if prior_context:
            prompt = prompt.replace("{TRANSCRIPT_PRIOR}", prior_context)
        else:
            prompt = prompt.replace("{TRANSCRIPT_PRIOR}", "No prior transcript context available")
        
        return prompt
    
    def _call_llm_for_frame(self, client, provider_type: str, model: str,
                           prompt: str, image_path: Path, params: Dict[str, Any]) -> str:
        """Call LLM for frame analysis."""
        try:
            if provider_type == "ollama":
                result = client.generate(
                    prompt=prompt,
                    image_path=str(image_path),
                    model=model,
                    temperature=params.get("temperature", 0.0),
                    num_predict=4096,
                )
                return result.get("response", "")
            else:  # openrouter
                # OpenRouter client uses different API
                result = client.generate(
                    prompt=prompt,
                    image_path=str(image_path),
                    model=model,
                    temperature=params.get("temperature", 0.0),
                )
                return result.get("response", "")
                
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return json.dumps({
                "error": str(e),
                "timestamp": time.time(),
                "analysis_failed": True
            })

    def _format_linkedin_analysis_markdown(self, analysis: Dict[str, Any]) -> str:
        """Format LinkedIn frame analysis JSON as markdown for live display."""
        parts = []

        summary = analysis.get("summary", "")
        if summary:
            parts.append(f"**Summary:** {summary}")

        hook = analysis.get("hook_potential", {})
        if hook:
            hp = hook.get("hook_potential", "unknown")
            he = hook.get("hook_explanation", "")
            parts.append(f"**Hook Potential:** {hp}")
            if he:
                parts.append(f"  - {he}")

        vq = analysis.get("visual_quality", {})
        if vq:
            vq_parts = []
            for k, v in vq.items():
                vq_parts.append(f"{k.replace('_', ' ').title()}: {v}")
            parts.append(f"**Visual Quality:** {', '.join(vq_parts)}")

        sa = analysis.get("speaker_analysis", {})
        if sa:
            sa_parts = []
            for k, v in sa.items():
                sa_parts.append(f"{k.replace('_', ' ').title()}: {v}")
            parts.append(f"**Speaker Analysis:** {', '.join(sa_parts)}")

        osc = analysis.get("on_screen_content", {})
        if osc:
            has = osc.get("has_content", False)
            desc = osc.get("content_description", "")
            parts.append(f"**On-Screen Content:** {'Yes' if has else 'No'}")
            if desc:
                parts.append(f"  - {desc}")

        sc = analysis.get("scene_context", {})
        if sc:
            sc_parts = []
            for k, v in sc.items():
                sc_parts.append(f"{k.replace('_', ' ').title()}: {v}")
            parts.append(f"**Scene Context:** {', '.join(sc_parts)}")

        tr = analysis.get("transcript_relationship", {})
        if tr:
            tr_parts = []
            for k, v in tr.items():
                tr_parts.append(f"{k.replace('_', ' ').title()}: {v}")
            parts.append(f"**Transcript Relationship:** {', '.join(tr_parts)}")

        return "\n\n".join(parts) if parts else "No analysis available"

    def _fuse_segments(self, frame_analyses: List[Dict[str, Any]], 
                      transcript: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fuse transcript segments with frame analyses (Prompt 2)."""
        logger.info("=== Segment Fusion ===")
        self.update_status({"stage": "segment_fusion", "progress": 60})
        
        if not frame_analyses:
            logger.warning("No frame analyses available")
            return []
        
        transcript_segments = safe_get_transcript_segments(transcript) or []
        if not transcript_segments:
            logger.warning("No transcript segments available")
            # Create segments from frames only
            return self._create_segments_from_frames(frame_analyses)
        
        # Load segment fusion prompt
        fusion_prompt = load_linkedin_prompt("segment_fusion")
        logger.info(f"Loaded segment fusion prompt ({len(fusion_prompt)} chars)")
        
        # Group frames by transcript segments
        segments = self._group_frames_by_transcript(frame_analyses, transcript_segments)
        
        # For each segment, create fusion data and call LLM
        fused_segments = []
        
        for i, segment in enumerate(segments):
            self.update_status({"progress": 60 + int((i + 1) / len(segments) * 10)})
            
            logger.info(f"Fusing segment {i+1}/{len(segments)}: {segment['start_time']} - {segment['end_time']}")
            
            # Build fusion input
            fusion_input = self._build_fusion_input(segment, transcript_segments)
            
            # Call LLM for fusion
            fused_result = self._call_llm_for_fusion(fusion_prompt, fusion_input)
            
            # Parse result
            fused_segment = parse_json_response(fused_result)
            
            # Add metadata
            fused_segment.update({
                "segment_id": f"SEG_{i+1:03d}",
                "frame_count": len(segment['frames']),
                "transcript_segment_count": len(segment['transcript_segments']),
            })
            
            fused_segments.append(fused_segment)

            # Write to segments log
            segments_file = self.job_dir / "linkedin_segments_raw.jsonl"
            with open(segments_file, "a") as f:
                f.write(json.dumps(fused_segment) + "\n")

            # Live status update for segment fusion
            self.update_status({
                "current_fused_segment": i + 1,
                "total_fused_segments": len(segments),
                "last_fused_segment": {
                    "segment_id": fused_segment.get("segment_id"),
                    "start_time": fused_segment.get("start_time"),
                    "end_time": fused_segment.get("end_time"),
                    "visual_summary": (fused_segment.get("visual_summary", "") or "")[:200],
                },
            })

        logger.info(f"Segment fusion complete: {len(fused_segments)} segments")
        return fused_segments
    
    def _create_segments_from_frames(self, frame_analyses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create segments from frames only (no transcript)."""
        segments = []
        
        # Group frames by time intervals (e.g., 30-second segments)
        frame_groups = []
        current_group = []
        group_start_time = 0
        
        for frame in frame_analyses:
            timestamp = frame.get("timestamp", 0)
            
            if not current_group or timestamp - group_start_time <= 30:
                current_group.append(frame)
                if not current_group:
                    group_start_time = timestamp
            else:
                # Start new group
                frame_groups.append(current_group)
                current_group = [frame]
                group_start_time = timestamp
        
        if current_group:
            frame_groups.append(current_group)
        
        # Create segments from groups
        for i, group in enumerate(frame_groups):
            if group:
                start_time = group[0].get("timestamp", 0)
                end_time = group[-1].get("timestamp", start_time + 30)
                
                # Create simple segment
                segments.append({
                    "segment_id": f"SEG_{i+1:03d}",
                    "start_time": format_timestamp(start_time),
                    "end_time": format_timestamp(end_time),
                    "duration_seconds": end_time - start_time,
                    "frames": group,
                    "transcript_segments": [],
                    "transcript": "",
                    "visual_summary": "No transcript available",
                    "self_contained": True,
                    "has_cta": False,
                    "on_screen_reinforcement": False,
                })
        
        return segments
    
    def _group_frames_by_transcript(self, frame_analyses: List[Dict[str, Any]],
                                   transcript_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group frames by overlapping transcript segments."""
        segments = []
        
        for i, transcript_seg in enumerate(transcript_segments):
            seg_start = transcript_seg.get("start", 0)
            seg_end = transcript_seg.get("end", seg_start + 5)
            seg_text = transcript_seg.get("text", "")
            
            # Find frames within this transcript segment
            frames_in_segment = []
            for frame in frame_analyses:
                timestamp = frame.get("timestamp", 0)
                if seg_start <= timestamp <= seg_end:
                    frames_in_segment.append(frame)
            
            if frames_in_segment:
                # Also include frames from adjacent transcript segments for context
                adjacent_frames = []
                for j in range(max(0, i-2), min(len(transcript_segments), i+3)):
                    if j != i:
                        adj_seg = transcript_segments[j]
                        adj_start = adj_seg.get("start", 0)
                        adj_end = adj_seg.get("end", adj_start + 5)
                        
                        for frame in frame_analyses:
                            timestamp = frame.get("timestamp", 0)
                            if adj_start <= timestamp <= adj_end:
                                adjacent_frames.append(frame)
                
                segments.append({
                    "start_time": format_timestamp(seg_start),
                    "end_time": format_timestamp(seg_end),
                    "duration_seconds": seg_end - seg_start,
                    "frames": frames_in_segment,
                    "adjacent_frames": adjacent_frames,
                    "transcript_segments": [transcript_seg],
                    "transcript_text": seg_text,
                })
        
        # Merge adjacent segments if they're close together
        merged_segments = []
        for i, segment in enumerate(segments):
            if i == 0:
                merged_segments.append(segment)
            else:
                prev_segment = merged_segments[-1]
                prev_end = float(prev_segment["duration_seconds"]) + float(
                    self._parse_timestamp(prev_segment["start_time"])
                )
                curr_start = float(self._parse_timestamp(segment["start_time"]))
                
                # Merge if gap is less than 10 seconds
                if curr_start - prev_end < 10:
                    # Merge segments
                    prev_segment["frames"].extend(segment["frames"])
                    prev_segment["adjacent_frames"].extend(segment["adjacent_frames"])
                    prev_segment["transcript_segments"].extend(segment["transcript_segments"])
                    prev_segment["transcript_text"] += " " + segment["transcript_text"]
                    prev_segment["end_time"] = segment["end_time"]
                    prev_segment["duration_seconds"] = curr_start + segment["duration_seconds"] - float(
                        self._parse_timestamp(prev_segment["start_time"])
                    )
                else:
                    merged_segments.append(segment)
        
        return merged_segments
    
    def _parse_timestamp(self, timestamp_str: str) -> float:
        """Parse HH:MM:SS timestamp to seconds."""
        parts = timestamp_str.split(":")
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    
    def _build_fusion_input(self, segment: Dict[str, Any],
                           transcript_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build input for segment fusion."""
        # Extract frame analyses summaries
        frame_descriptions = []
        for frame in segment["frames"]:
            analysis = frame.get("analysis", {})
            summary = analysis.get("summary", "No analysis available")
            hook_potential = analysis.get("hook_potential", {}).get("hook_potential", "unknown")
            
            frame_descriptions.append({
                "timestamp": frame.get("timestamp", 0),
                "summary": summary,
                "hook_potential": hook_potential,
                "visual_quality": analysis.get("visual_quality", {}),
                "speaker_analysis": analysis.get("speaker_analysis", {}),
            })
        
        # Build fusion input structure
        return {
            "segment_info": {
                "start_time": segment["start_time"],
                "end_time": segment["end_time"],
                "duration_seconds": segment["duration_seconds"],
            },
            "transcript_segments": segment["transcript_segments"],
            "frame_descriptions": frame_descriptions,
            "transcript_text": segment["transcript_text"],
        }
    
    def _call_llm_for_fusion(self, fusion_prompt: str, fusion_input: Dict[str, Any]) -> str:
        """Call LLM for segment fusion."""
        # Convert input to JSON string for the prompt
        input_json = json.dumps(fusion_input, indent=2)
        
        # Build prompt
        prompt = f"{fusion_prompt}\n\nINPUT DATA:\n{input_json}"
        
        try:
            # Try to use the provider's LLM for text-only fusion
            # For simplicity, we'll use the same provider config as the main analysis
            provider_type = self.config.get("provider_type", "ollama")
            provider_config = self.config.get("provider_config", {})
            model = self.config.get("model", "")
            params = self.config.get("params", {})
            
            if provider_type == "ollama":
                import requests
                
                ollama_url = provider_config.get("url", "http://localhost:11434")
                
                response = requests.post(
                    f"{ollama_url.rstrip('/')}/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "think": False,
                        "options": {
                            "temperature": params.get("temperature", 0.0),
                            "num_predict": 4096,
                        },
                    },
                    timeout=300,
                )
                response.raise_for_status()
                result = response.json().get("message", {}).get("content", "")
                
                logger.info(f"Segment fusion LLM call successful")
                return result
                
            else:  # openrouter
                import requests
                
                api_key = provider_config.get("api_key", "")
                
                response = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": params.get("temperature", 0.0),
                        "max_tokens": 4096,
                    },
                    timeout=300,
                )
                response.raise_for_status()
                result = response.json()["choices"][0]["message"]["content"]
                
                logger.info(f"Segment fusion LLM call successful")
                return result
                
        except Exception as e:
            logger.error(f"Segment fusion LLM call failed: {e}")
            
            # Fallback to simple fusion
            segment_id = f"SEG_{int(time.time() % 1000):03d}"
            start_time = fusion_input["segment_info"]["start_time"]
            end_time = fusion_input["segment_info"]["end_time"]
            duration = fusion_input["segment_info"]["duration_seconds"]
            
            # Create simple fused segment based on frame analyses
            visual_summary_parts = []
            for frame_desc in fusion_input.get("frame_descriptions", []):
                summary = frame_desc.get("summary", "")
                if summary and summary not in visual_summary_parts:
                    visual_summary_parts.append(summary)
            
            visual_summary = " ".join(visual_summary_parts[:2])  # Take first 2 summaries
            
            # Determine speaker energy from frame analyses
            speaker_energies = []
            for frame_desc in fusion_input.get("frame_descriptions", []):
                speaker = frame_desc.get("speaker_analysis", {})
                energy = speaker.get("energy_level", "")
                if energy:
                    speaker_energies.append(energy)
            
            speaker_energy = "medium"
            if speaker_energies:
                # Use most common energy level
                from collections import Counter
                energy_counts = Counter(speaker_energies)
                speaker_energy = energy_counts.most_common(1)[0][0]
            
            # Create fallback fusion result
            fusion_result = [{
                "segment_id": segment_id,
                "start_time": start_time,
                "end_time": end_time,
                "duration_seconds": duration,
                "transcript": fusion_input.get("transcript_text", ""),
                "visual_summary": visual_summary or "Visual analysis unavailable",
                "opening_line": fusion_input.get("transcript_text", "").split(". ")[0] if fusion_input.get("transcript_text", "") else "",
                "closing_line": fusion_input.get("transcript_text", "").split(". ")[-1] if fusion_input.get("transcript_text", "") else "",
                "key_topics": ["professional content", "video analysis"],
                "speaker_energy": speaker_energy,
                "visual_quality_score": "medium",
                "self_contained": len(fusion_input.get("transcript_segments", [])) > 0,
                "hook_strength": "moderate",
                "has_cta": "?" in (fusion_input.get("transcript_text", "") or ""),
                "on_screen_reinforcement": any(
                    frame_desc.get("on_screen_content", {}).get("has_content", False)
                    for frame_desc in fusion_input.get("frame_descriptions", [])
                ),
                "notes": f"Auto-generated due to LLM failure: {str(e)[:100]}",
            }]
            
            return json.dumps(fusion_result)
    
    def _extract_and_rank_segments(self, fused_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Stage 3: RAG extraction and ranking using OpenWebUI or local scoring."""
        logger.info("=== RAG Extraction & Ranking ===")
        self.update_status({"stage": "rag_extraction", "progress": 80})
        
        if not fused_segments:
            logger.warning("No fused segments to rank")
            return []
        
        logger.info(f"Ranking {len(fused_segments)} segments...")
        
        # Try to use OpenWebUI RAG service if available
        use_openwebui = self.linkedin_config.edit_preferences.get("use_openwebui_rag", True)
        rag_service = None
        
        if use_openwebui:
            try:
                from src.services.linkedin_rag import LinkedInRAGService
                rag_service = LinkedInRAGService()
                logger.info("Using OpenWebUI RAG service")
            except ImportError as e:
                logger.warning(f"OpenWebUI RAG service not available: {e}")
                use_openwebui = False
        
        ranked_segments = []
        
        for i, segment in enumerate(fused_segments):
            self.update_status({"progress": 80 + int((i + 1) / len(fused_segments) * 15)})
            
            # Score the segment
            score_data = self._score_segment(segment)
            
            # Add RAG context if available
            if use_openwebui and rag_service:
                try:
                    rag_context = rag_service.get_segment_context(segment)
                    if rag_context:
                        segment["rag_context"] = rag_context
                        segment["similar_content_found"] = rag_context.get("has_similar_content", False)
                        logger.info(f"Segment {i+1}: Added RAG context")
                except Exception as e:
                    logger.warning(f"Failed to get RAG context for segment {i+1}: {e}")
            
            # Create ranked segment
            ranked_segment = {
                **segment,
                **score_data,
                "overall_score": score_data["total_score"],
                "rank": i + 1,  # Will be sorted later
                "selected_for_clips": False,  # Will be determined by thresholds
            }
            
            ranked_segments.append(ranked_segment)

            # Write to ranking log
            ranking_file = self.job_dir / "linkedin_segments_ranked.jsonl"
            with open(ranking_file, "a") as f:
                f.write(json.dumps(ranked_segment) + "\n")

            # Live status update for RAG ranking
            self.update_status({
                "current_ranked_segment": i + 1,
                "total_ranked_segments": len(fused_segments),
                "last_ranked_segment": {
                    "segment_id": ranked_segment.get("segment_id"),
                    "rank": ranked_segment.get("rank"),
                    "overall_score": ranked_segment.get("overall_score"),
                },
            })

        # Sort by overall score
        ranked_segments.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
        
        # Update ranks
        for i, segment in enumerate(ranked_segments):
            segment["rank"] = i + 1
            
            # Check if segment meets thresholds for clip generation
            hook_strength = segment.get("hook_strength_score", 0)
            total_score = segment.get("total_score", 0)
            
            hook_threshold = self.linkedin_config.targets.get("hook_strength_threshold", 18)
            total_threshold = self.linkedin_config.targets.get("total_score_threshold", 70)
            
            if hook_strength >= hook_threshold and total_score >= total_threshold:
                segment["selected_for_clips"] = True
                logger.info(f"Segment {segment.get('segment_id', 'unknown')} selected for clip generation "
                          f"(hook: {hook_strength}/{hook_threshold}, total: {total_score}/{total_threshold})")
        
        logger.info(f"RAG extraction and ranking complete: {len(ranked_segments)} segments ranked")
        return ranked_segments
    
    def _score_segment(self, segment: Dict[str, Any]) -> Dict[str, Any]:
        """Score a segment using LinkedIn scoring weights."""
        scores = {}
        
        # Hook strength scoring
        hook_strength = segment.get("hook_strength", "weak")
        if hook_strength == "strong":
            scores["hook_strength_score"] = 25
        elif hook_strength == "moderate":
            scores["hook_strength_score"] = 15
        else:
            scores["hook_strength_score"] = 5
        
        # Self-contained value
        is_self_contained = segment.get("self_contained", False)
        scores["self_contained_score"] = 20 if is_self_contained else 0
        
        # Clarity and focus (from visual summary and transcript)
        visual_quality = segment.get("visual_quality_score", "medium")
        if visual_quality == "high":
            scores["clarity_score"] = 15
        elif visual_quality == "medium":
            scores["clarity_score"] = 10
        else:
            scores["clarity_score"] = 5
        
        # Speaker energy
        speaker_energy = segment.get("speaker_energy", "medium")
        if speaker_energy == "high":
            scores["speaker_energy_score"] = 15
        elif speaker_energy == "medium":
            scores["speaker_energy_score"] = 10
        else:
            scores["speaker_energy_score"] = 5
        
        # Visual quality
        if visual_quality == "high":
            scores["visual_quality_score_points"] = 10
        elif visual_quality == "medium":
            scores["visual_quality_score_points"] = 7
        else:
            scores["visual_quality_score_points"] = 3
        
        # CTA potential
        has_cta = segment.get("has_cta", False)
        scores["cta_score"] = 10 if has_cta else 0
        
        # Duration fit
        duration = segment.get("duration_seconds", 0)
        ideal_min = self.linkedin_config.targets.get("ideal_duration_min", 30)
        ideal_max = self.linkedin_config.targets.get("ideal_duration_max", 60)
        min_duration = self.linkedin_config.targets.get("min_duration", 15)
        max_duration = self.linkedin_config.targets.get("max_duration", 90)
        
        if ideal_min <= duration <= ideal_max:
            scores["duration_score"] = 5  # Perfect duration
        elif min_duration <= duration <= max_duration:
            scores["duration_score"] = 3  # Acceptable duration
        else:
            scores["duration_score"] = 0  # Outside acceptable range
        
        # On-screen reinforcement bonus
        has_reinforcement = segment.get("on_screen_reinforcement", False)
        if has_reinforcement:
            scores["reinforcement_bonus"] = 5
        else:
            scores["reinforcement_bonus"] = 0
        
        # Calculate total score
        total_score = sum(scores.values())
        scores["total_score"] = total_score
        
        # Add scoring breakdown
        scores["scoring_breakdown"] = {
            "hook_strength": scores["hook_strength_score"],
            "self_contained": scores["self_contained_score"],
            "clarity_and_focus": scores["clarity_score"],
            "speaker_energy": scores["speaker_energy_score"],
            "visual_quality": scores["visual_quality_score_points"],
            "cta_potential": scores["cta_score"],
            "duration_fit": scores["duration_score"],
            "reinforcement_bonus": scores.get("reinforcement_bonus", 0),
        }
        
        return scores
    
    def _generate_results(self, job_id: str, ranked_segments: List[Dict[str, Any]],
                         video_path: Path, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate final results with optional clip generation."""
        logger.info("=== Generating Final Results ===")
        
        # Filter segments selected for clips
        selected_segments = [s for s in ranked_segments if s.get("selected_for_clips", False)]
        
        # Generate clips if enabled
        clips = []
        generate_clips = self.linkedin_config.edit_preferences.get("generate_clips", False)
        
        if generate_clips and selected_segments:
            logger.info(f"Generating clips for {len(selected_segments)} selected segments")
            clips = self._generate_clips(selected_segments, video_path)
        else:
            logger.info(f"Clip generation {'disabled' if not generate_clips else 'skipped - no selected segments'}")
        
        # Create final results structure
        results = {
            "job_id": job_id,
            "pipeline": "linkedin_extraction",
            "video_path": str(video_path),
            "linkedin_config": self.linkedin_config.to_dict(),
            "summary": {
                "total_segments": len(ranked_segments),
                "selected_for_clips": len(selected_segments),
                "clips_generated": len([c for c in clips if c.get("status") == "generated"]),
                "clips_failed": len([c for c in clips if c.get("status") == "failed"]),
                "top_segments": [
                    {
                        "segment_id": s.get("segment_id"),
                        "rank": s.get("rank"),
                        "total_score": s.get("total_score", 0),
                        "duration": s.get("duration_seconds", 0),
                        "hook_strength": s.get("hook_strength", "unknown"),
                    }
                    for s in ranked_segments[:5]  # Top 5 segments
                ],
            },
            "segments": ranked_segments,
            "clips": clips,
            "metadata": {
                "generated_at": time.time(),
                "generated_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "processing_time_seconds": time.time() - self.start_time,
            },
        }
        
        # Save results to file
        results_file = self.output_dir / "linkedin_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Results saved to {results_file}")
        return results
    
    def _generate_clips(self, segments: List[Dict[str, Any]], video_path: Path) -> List[Dict[str, Any]]:
        """Generate video clips using ffmpeg."""
        logger.info("Generating video clips...")
        
        # Check if video file exists
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return [{"error": f"Video file not found: {video_path}", "status": "failed"}]
        
        clips = []
        clips_dir = self.output_dir / "clips"
        clips_dir.mkdir(exist_ok=True)
        
        # Check if ffmpeg is available
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("ffmpeg not found or not working")
            return [{"error": "ffmpeg not available", "status": "failed"}]
        
        # Determine output format
        prefer_vertical = self.linkedin_config.edit_preferences.get("prefer_vertical", True)
        allow_square = self.linkedin_config.edit_preferences.get("allow_square", True)
        
        # Generate clips for each segment
        for segment in segments:
            segment_id = segment.get("segment_id", "unknown")
            start_time = segment.get("start_time", "00:00:00")
            end_time = segment.get("end_time", "00:00:30")
            duration = segment.get("duration_seconds", 30)
            
            # Skip if too short or too long
            min_duration = self.linkedin_config.targets.get("min_duration", 15)
            max_duration = self.linkedin_config.targets.get("max_duration", 90)
            
            if duration < min_duration or duration > max_duration:
                logger.warning(f"Segment {segment_id} duration {duration}s outside acceptable range [{min_duration}, {max_duration}], skipping")
                continue
            
            # Create clip filename
            clip_filename = f"clip_{segment_id}_{int(time.time())}.mp4"
            clip_path = clips_dir / clip_filename
            
            try:
                # Build ffmpeg command
                cmd = [
                    "ffmpeg",
                    "-y",  # Overwrite output
                    "-ss", start_time,  # Start time
                    "-to", end_time,  # End time
                    "-i", str(video_path),  # Input file
                    "-c:v", "libx264",  # Video codec
                    "-c:a", "aac",  # Audio codec
                    "-b:a", "128k",  # Audio bitrate
                    "-preset", "medium",  # Encoding speed
                    "-crf", "23",  # Quality (lower = better)
                ]
                
                # Add format-specific options
                if prefer_vertical:
                    # Vertical format (9:16) - crop or pad
                    cmd.extend([
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                    ])
                elif allow_square:
                    # Square format (1:1)
                    cmd.extend([
                        "-vf", "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2",
                    ])
                else:
                    # Keep original aspect ratio, scale to 1080p width
                    cmd.extend([
                        "-vf", "scale=1080:-2",
                    ])
                
                cmd.append(str(clip_path))
                
                logger.info(f"Generating clip {segment_id}: {start_time} to {end_time}")
                logger.debug(f"ffmpeg command: {' '.join(cmd)}")
                
                # Run ffmpeg command
                result = subprocess.run(
                    cmd, 
                    check=True, 
                    capture_output=True, 
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if clip_path.exists() and clip_path.stat().st_size > 0:
                    clips.append({
                        "segment_id": segment_id,
                        "clip_path": str(clip_path),
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration_seconds": duration,
                        "file_size": clip_path.stat().st_size,
                        "ffmpeg_command": " ".join(cmd),
                        "status": "generated"
                    })
                    logger.info(f"Clip generated successfully: {clip_path} ({clip_path.stat().st_size} bytes)")
                else:
                    raise Exception("Clip file not created or empty")
                
            except subprocess.CalledProcessError as e:
                logger.error(f"ffmpeg failed for clip {segment_id}: {e}")
                logger.error(f"ffmpeg stderr: {e.stderr[:500]}")
                clips.append({
                    "segment_id": segment_id,
                    "error": f"ffmpeg error: {e.stderr[:200]}",
                    "status": "failed"
                })
            except subprocess.TimeoutExpired:
                logger.error(f"ffmpeg timeout for clip {segment_id}")
                clips.append({
                    "segment_id": segment_id,
                    "error": "ffmpeg timeout after 5 minutes",
                    "status": "failed"
                })
            except Exception as e:
                logger.error(f"Failed to generate clip {segment_id}: {e}")
                clips.append({
                    "segment_id": segment_id,
                    "error": str(e),
                    "status": "failed"
                })
        
        logger.info(f"Generated {len([c for c in clips if c['status'] == 'generated'])} clips")
        return clips