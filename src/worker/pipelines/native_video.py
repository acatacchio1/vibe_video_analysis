"""
Native video analysis pipeline — qwen3-vl native video input.
Single-pass holistic analysis: entire video → structured JSON events.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.worker.transcription import (
    extract_audio,
    load_preexisting_transcript,
    transcribe_audio,
)

from .base import AnalysisPipeline

logger = logging.getLogger(__name__)

# Duration threshold for native video input (7 minutes)
NATIVE_VIDEO_MAX_DURATION = 420

# Prompt parameters: max_tokens=4096, temperature=0.0
VIDEO_ANALYSIS_PROMPT = """Analyze this video and identify all key events, scenes, and visual elements. Return ONLY a valid JSON array covering the entire video chronologically:
[{
  "timestamp": "mm:ss.ff",
  "duration": float,
  "description": "clear visual description with context"
}]
Timestamps in mm:ss.ff format. Duration in seconds. Do not skip significant events."""

# Synthesis prompt template (matches _synthesize_frame pattern in standard_two_step.py)
SYNTHESIS_PROMPT = """Combine the visual analysis with transcript context to create an enhanced description.

VISION ANALYSIS:
{vision_analysis}

TRANSCRIPT CONTEXT:
{transcript_context}

TIMESTAMP: {timestamp:.2f} seconds

Create a comprehensive analysis that integrates what's visually present with what's being said at this moment in the video. Focus on:
1. How the transcript context relates to or explains what's shown visually
2. Connections between audio content and visual elements
3. Any contradictions or confirmations between what's said and what's shown
4. Additional understanding the transcript provides about the visual scene
5. How this moment fits into the broader narrative

ENHANCED ANALYSIS:"""


class NativeVideoPipeline(AnalysisPipeline):
    """Native video analysis pipeline using qwen3-vl direct video input."""

    def __init__(self, job_dir: Path, config: Any):
        super().__init__(job_dir, config)

    def _get_video_path(self) -> Path:
        if self.typed_config is not None:
            return self.typed_config.video_path_obj
        return Path(self.config.get("video_path", ""))

    def _get_job_id(self) -> str:
        if self.typed_config is not None:
            return str(self.typed_config.job_id)
        return str(self.config.get("job_id", ""))

    def _get_audio_config(self) -> Dict[str, Any]:
        if self.typed_config is not None:
            tc = self.typed_config
            return {
                "whisper_model": tc.params.audio.whisper_model,
                "language": tc.params.audio.language,
                "device": tc.params.audio.device,
            }
        return self.config.get("params", {}).get("audio", {
            "whisper_model": "large",
            "language": "en",
            "device": "gpu",
        })

    def _get_phase2_config(self) -> Tuple[bool, str, str, float, Dict[str, Any]]:
        """Resolve Phase 2 synthesis config from typed config or fallback dict.

        Returns:
            Tuple of (enabled, provider_type, model, temperature, provider_config).
        """
        if self.typed_config is not None:
            phase2_cfg = self.typed_config.params.phase2
            enabled = phase2_cfg.enabled
            provider_type = phase2_cfg.provider_type
            model = phase2_cfg.model
            temperature = phase2_cfg.temperature
            provider_config = phase2_cfg.provider_config.model_dump()
        else:
            phase2_params = self.config.get("params", {}).get("phase2", {})
            enabled = phase2_params.get("enabled", True)
            provider_type = phase2_params.get("provider_type", "litellm")
            model = phase2_params.get("model", "qwen3-27b-q8")
            temperature = phase2_params.get("temperature", 0.0)
            provider_config = phase2_params.get("provider_config", {})

        if provider_type == "litellm" and not provider_config.get("url"):
            provider_config["url"] = "http://172.16.17.3:4000/v1"

        return enabled, provider_type, model, temperature, provider_config

    def _get_provider_config(self) -> Tuple[str, str, Dict[str, Any]]:
        """Resolve primary provider config from typed config or fallback dict.

        Returns:
            Tuple of (provider_type, model, provider_config).
        """
        if self.typed_config is not None:
            provider_type = self.typed_config.provider_type
            model = self.typed_config.model
            provider_config = self.typed_config.provider_config.model_dump()
        else:
            provider_type = self.config.get("provider_type", "litellm")
            model = self.config.get("model", "qwen3-27b-q8")
            provider_config = self.config.get("provider_config", {})

        return provider_type, model, provider_config

    def _extract_audio_and_transcribe(
        self, video_path: Path
    ) -> Dict[str, Any]:
        """Extract audio and transcribe with Whisper.

        Writes transcript text to status.json via update_status() so that
        app.py's monitor_job() picks it up and emits job_transcript SocketIO.

        Falls back to pre-existing transcript if audio extraction fails.
        """
        self.update_status({"stage": "extracting_audio", "progress": 5})

        audio_cfg = self._get_audio_config()
        whisper_model = audio_cfg.get("whisper_model", "large")
        language = audio_cfg.get("language", "en")
        device = audio_cfg.get("device", "gpu")

        wav_path = extract_audio(
            str(video_path),
            str(self.job_dir),
        )

        transcript = None

        if wav_path:
            try:
                self.update_status({"stage": "transcribing", "progress": 10})
                transcript = transcribe_audio(wav_path, whisper_model, language, device)
                logger.info(
                    f"Transcription complete: {len(transcript['segments'])} segments, "
                    f"text length={len(transcript['text'])}"
                )
            except Exception as e:
                logger.warning(f"Transcription failed: {e}")

        if transcript is None:
            video_stem = video_path.stem
            uploads_dir = str(video_path.parent)
            transcript = load_preexisting_transcript(video_stem, uploads_dir)
            if transcript is None:
                transcript = self.load_transcript()

        if transcript is None:
            transcript = {
                "text": "",
                "segments": [],
                "language": language,
                "whisper_model": whisper_model,
            }
            logger.info("No transcript available; proceeding with empty transcript")

        # Emit transcript via status.json (monitor_job() in app.py picks this up
        # and emits job_transcript SocketIO event — same pattern as standard_two_step)
        transcript_text = transcript.get("text", "")
        if transcript_text:
            self.update_status({"transcript": transcript_text})

        return transcript

    def _check_video_duration(self, video_path) -> Tuple[bool, float]:
        """Check if video duration is within the native video limit.

        Args:
            video_path: Path to the video file.

        Returns:
            Tuple of (within_limit, duration_seconds).
            within_limit is True if duration <= 420s, False otherwise.
        """
        from src.utils.video import get_video_duration

        duration = get_video_duration(video_path)
        within_limit = duration <= NATIVE_VIDEO_MAX_DURATION
        logger.info(
            f"Video {video_path} duration check: {duration:.1f}s "
            f"{'within' if within_limit else 'EXCEEDS'} {NATIVE_VIDEO_MAX_DURATION}s limit"
        )
        return within_limit, duration

    def _get_transcript_segments_with_end_times(
        self, transcript: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build transcript segments list with end times for timestamp lookups.

        Mirrors the logic in standard_two_step.py's analyze_frames loop.
        """
        if not transcript:
            return []
        segments = transcript.get("segments", [])
        if not segments:
            return []

        result = []
        for seg in segments:
            entry = {
                "text": seg.get("text", ""),
                "start": seg.get("start", 0),
                "end": seg.get("end", seg.get("start", 0) + 5),
            }
            result.append(entry)
        return result

    def _get_transcript_context_for_timestamp(
        self, current_ts: float,
        transcript_segments: List[Dict[str, Any]],
    ) -> str:
        """Build transcript context string for a given timestamp.

        Finds the most relevant transcript segment(s) around current_ts
        and returns a formatted string for synthesis prompts.
        """
        if not transcript_segments:
            return ""

        first_seg_start = transcript_segments[0]["start"]
        last_seg = transcript_segments[-1]
        last_seg_end = last_seg["end"]
        time_buffer = 15.0

        is_near_transcript = (
            (first_seg_start - time_buffer) <= current_ts <= (last_seg_end + time_buffer)
        )

        if not is_near_transcript:
            if current_ts < first_seg_start:
                return f"[Transcript begins {abs(current_ts - first_seg_start):.0f}s later in video]"
            else:
                return f"[Transcript ended {current_ts - last_seg_end:.0f}s ago, may not be relevant]"

        recent = ""
        prior = ""
        current_seg_idx = -1

        for idx, seg in enumerate(transcript_segments):
            seg_end = seg["end"]
            if seg["start"] <= current_ts <= seg_end:
                current_seg_idx = idx
                break
            elif seg["start"] < current_ts:
                current_seg_idx = idx

        if current_seg_idx >= 0:
            seg = transcript_segments[current_seg_idx]
            seg_start = seg["start"]
            seg_end = seg["end"]

            if seg_start <= current_ts <= seg_end:
                recent = seg["text"]
                prior_start = max(0, current_seg_idx - 2)
                if current_seg_idx > prior_start:
                    prior_segs = transcript_segments[prior_start:current_seg_idx]
                    prior = " ".join(s["text"] for s in prior_segs)
            elif current_ts < first_seg_start:
                return "[Transcript begins later in video]"
            elif current_ts > last_seg_end:
                gap = current_ts - last_seg_end
                if gap < 30:
                    recent = last_seg["text"]
                    return f"[Transcript ended {gap:.0f}s ago]\n{recent}"
                else:
                    return f"[Transcript ended {gap:.0f}s ago, may not be relevant]"
        else:
            return f"[No transcript near timestamp {current_ts:.1f}s]"

        context = ""
        if recent:
            context = f"{recent}"
        if prior:
            context = f"PRIOR: {prior}\n\nRECENT: {recent}" if prior else context
        return context if context else ""

    def _analyze_video(self) -> list:
        """Send full video to qwen3-vl via requests.post() and parse JSON events.

        Returns:
            List of event dicts with parsed float timestamps.
        """
        video_path = self._get_video_path()
        job_id = self._get_job_id()

        import requests

        provider_type, model, provider_config = self._get_provider_config()

        # Determine model for video analysis — use qwen3-vl variant
        video_model = model
        if "vision" not in video_model.lower() and "vl" not in video_model.lower():
            # Default to qwen3-vl if model doesn't look vision-capable
            video_model = "qwen3-vl-2b-instruct"

        if provider_type == "litellm":
            url = f"{provider_config.get('url', 'http://172.16.17.3:4000/v1')}/chat/completions"
            auth_header = "Bearer "
        else:
            url = "https://openrouter.ai/api/v1/chat/completions"
            auth_header = f"Bearer {provider_config.get('api_key', '')}"

        content = [
            {"type": "text", "text": VIDEO_ANALYSIS_PROMPT},
            {"type": "video_url", "video_url": {"url": f"file://{video_path}"}},
        ]

        logger.info(f"Submitting video analysis request to {url}")

        resp = requests.post(
            url,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={
                "model": video_model,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 4096,
                "temperature": 0.0,
            },
            timeout=600,  # 10 minutes
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]

        # Strip markdown code fences: ```json ... ```
        raw = re.sub(r'^```json\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw.strip())

        events = []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                events = parsed
            else:
                # Single JSON object — wrap in array
                events = [parsed]
        except json.JSONDecodeError:
            # Fallback: single event with raw text
            from src.utils.video import get_video_duration
            duration = get_video_duration(str(video_path))
            events = [{"timestamp": 0.0, "duration": duration, "description": raw}]

        # Convert mm:ss.ff timestamps to float seconds
        for event in events:
            ts = event.get("timestamp")
            if isinstance(ts, str):
                parts = ts.split(":")
                event["timestamp"] = int(parts[0]) * 60 + float(parts[1])

        self.update_status({
            "stage": "video_analysis",
            "progress": 50,
            "current_frame": len(events),
            "total_frames": len(events),
        })

        # Write events to events.jsonl for real-time emission
        events_file = self.job_dir / "events.jsonl"
        with open(events_file, "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

        logger.info(f"Video analysis complete: {len(events)} events")
        return events

    def _synthesize_events(
        self,
        events: List[Dict[str, Any]],
        transcript: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Combine vision events with transcript via Phase 2 LLM.

        For each event, calls Phase 2 LLM to synthesize vision description
        with transcript context. Stores result in event['combined_analysis'].

        Writes synthesis results to synthesis.jsonl for monitor_job() emission.

        Returns:
            Modified events list with combined_analysis field.
        """
        (enabled, phase2_provider_type, phase2_model,
         phase2_temperature, phase2_provider_config) = self._get_phase2_config()

        if not enabled:
            logger.info("Phase 2 synthesis disabled, skipping")
            for event in events:
                event["combined_analysis"] = event.get("description", "")
                event["vision_only"] = True
            return events

        import requests

        transcript_segments = self._get_transcript_segments_with_end_times(transcript)

        synthesis_file = self.job_dir / "synthesis.jsonl"

        self.update_status({
            "stage": "synthesis",
            "progress": 55,
        })

        for i, event in enumerate(events):
            current_ts = event.get("timestamp", 0.0)
            transcript_context = self._get_transcript_context_for_timestamp(
                current_ts, transcript_segments
            )

            vision_analysis = event.get("description", "")

            synthesis_prompt = SYNTHESIS_PROMPT.format(
                vision_analysis=vision_analysis,
                transcript_context=transcript_context or "No transcript available for this timestamp",
                timestamp=current_ts,
            )

            try:
                if phase2_provider_type == "litellm":
                    litellm_url = phase2_provider_config.get("url", "http://172.16.17.3:4000/v1")
                    resp = requests.post(
                        f"{litellm_url.rstrip('/')}/chat/completions",
                        headers={
                            "Authorization": "Bearer ",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": phase2_model,
                            "messages": [{"role": "user", "content": synthesis_prompt}],
                            "temperature": phase2_temperature,
                            "max_tokens": 4096,
                        },
                        timeout=300,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    result = data["choices"][0]["message"]["content"]
                    tokens = data.get("usage", {})
                else:
                    api_key = phase2_provider_config.get("api_key", "")
                    resp = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": phase2_model,
                            "messages": [{"role": "user", "content": synthesis_prompt}],
                            "temperature": phase2_temperature,
                            "max_tokens": 4096,
                        },
                        timeout=300,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    result = data["choices"][0]["message"]["content"]
                    tokens = data.get("usage", {})

                event["combined_analysis"] = result
                event["vision_analysis"] = vision_analysis
                event["transcript_context"] = transcript_context
                event["vision_only"] = False
                event["tokens"] = tokens
                event["phase2_provider_type"] = phase2_provider_type
                event["phase2_model"] = phase2_model

                # Write to synthesis.jsonl for monitor_job() frame_synthesis emission
                synthesis_entry = {
                    "frame_number": i + 1,
                    "timestamp": current_ts,
                    "vision_analysis": vision_analysis,
                    "transcript_context": transcript_context,
                    "combined_analysis": result,
                    "tokens": tokens,
                }
                with open(synthesis_file, "a") as f:
                    f.write(json.dumps(synthesis_entry) + "\n")

                progress = 55 + int((i + 1) / len(events) * 25)
                self.update_status({
                    "stage": "synthesis",
                    "progress": progress,
                    "current_frame": i + 1,
                    "total_frames": len(events),
                })

            except Exception as e:
                logger.error(f"Event {i+1} synthesis failed: {e}")
                event["combined_analysis"] = vision_analysis
                event["vision_only"] = True

        logger.info(f"Synthesis complete: {len(events)} events")
        return events

    def _reconstruct_video(
        self,
        events: List[Dict[str, Any]],
        transcript: Dict[str, Any],
    ) -> str:
        """Generate video description via text-only LLM from events + transcript.

        Returns:
            Plain text video description.
        """
        provider_type, model, provider_config = self._get_provider_config()

        # Build event text summary
        events_text = "\n".join([
            f"- [{e['timestamp']:.1f}s] {e.get('combined_analysis', e.get('description', ''))}"
            for e in events
        ])

        transcript_text = ""
        if isinstance(transcript, dict):
            transcript_text = transcript.get("text", "")

        prompt_text = f"""Based on the following event analyses and transcript, write a comprehensive video description.

EVENTS:
{events_text}

TRANSCRIPT:
{transcript_text}

VIDEO DESCRIPTION:"""

        import requests

        if provider_type == "litellm":
            url = f"{provider_config.get('url', 'http://172.16.17.3:4000/v1')}/chat/completions"
            auth_header = "Bearer "
        else:
            url = "https://openrouter.ai/api/v1/chat/completions"
            auth_header = f"Bearer {provider_config.get('api_key', '')}"

        logger.info("Submitting video reconstruction request")

        resp = requests.post(
            url,
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt_text}],
                "max_tokens": 2048,
                "temperature": 0.0,
            },
            timeout=120,
        )
        resp.raise_for_status()
        desc = resp.json()["choices"][0]["message"]["content"]

        self.update_status({
            "video_description": desc,
            "stage": "reconstructing",
            "progress": 90,
        })

        logger.info(f"Video description generated: {len(desc)} chars")
        return desc

    def _save_results(
        self,
        events: List[Dict[str, Any]],
        transcript: Dict[str, Any],
        video_description: str,
        token_usage: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Save results to output/results.json and update status to completed.

        Returns:
            Results dict (same content written to results.json).
        """
        transcript_data = transcript if isinstance(transcript, dict) else {
            "text": "", "segments": []
        }

        # Collect token usage from synthesis events
        total_prompt_tokens = 0
        total_completion_tokens = 0
        for event in events:
            tokens = event.get("tokens", {})
            if tokens:
                total_prompt_tokens += tokens.get("prompt_tokens", 0)
                total_completion_tokens += tokens.get("completion_tokens", 0)

        results = {
            "pipeline_type": "native_video",
            "metadata": {
                "job_id": self._get_job_id(),
                "pipeline_type": "native_video",
                "provider": self.config.get("provider_type", "litellm"),
                "model": self.config.get("model", ""),
                "frames_processed": len(events),
                "transcription_successful": bool(transcript_data.get("text", "")),
            },
            "video_analysis": {
                "events_count": len(events),
                "model": self.config.get("model", ""),
            },
            "events": events,
            "frames": events,  # Keep events in frames field for compatibility
            "transcript": transcript_data,
            "video_description": video_description,
            "token_usage": token_usage or {
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
            },
        }

        results_file = self.output_dir / "results.json"
        results_file.write_text(json.dumps(results, indent=2))
        logger.info(f"Results saved to {results_file}")

        self.update_status({
            "status": "completed",
            "stage": "complete",
            "progress": 100,
            "video_description": video_description,
            "results_file": str(results_file),
        })

        return results

    def run(self) -> Dict[str, Any]:
        logger.info("=== NATIVE VIDEO PIPELINE START ===")

        video_path = self._get_video_path()
        job_id = self._get_job_id()

        self.update_status({
            "status": "running",
            "stage": "initializing",
            "progress": 0,
            "current_frame": 0,
            "total_frames": 0,
            "pipeline": "native_video",
        })

        try:
            # Step 1: Duration check
            within_limit, duration = self._check_video_duration(str(video_path))

            if not within_limit:
                logger.info(
                    f"Video {video_path} duration {duration:.0f}s exceeds "
                    f"{NATIVE_VIDEO_MAX_DURATION}s limit — falling back to standard_two_step"
                )
                self.update_status({
                    "stage": "fallback",
                    "progress": 0,
                    "message": (
                        f"Video exceeds native video duration limit "
                        f"({duration:.0f}s > {NATIVE_VIDEO_MAX_DURATION}s), "
                        f"using standard pipeline"
                    ),
                })

                from .standard_two_step import StandardTwoStepPipeline

                fallback = StandardTwoStepPipeline(self.job_dir, self.config)
                results = fallback.run()
                logger.info("=== NATIVE VIDEO PIPELINE: FALLBACK COMPLETE ===")
                return results

            self.update_status({
                "stage": "duration_check",
                "progress": 5,
                "duration": duration,
            })

            # Step 2: Transcription
            transcript = self._extract_audio_and_transcribe(video_path)
            assert transcript is not None

            # Step 3: Video analysis (native video input to vision model)
            self.update_status({"stage": "analyzing_video", "progress": 30})
            events = self._analyze_video()

            # Step 4: Synthesis (combine vision + transcript via Phase 2 LLM)
            events = self._synthesize_events(events, transcript)

            # Step 5: Video description reconstruction
            self.update_status({"stage": "reconstructing", "progress": 85})
            video_description = self._reconstruct_video(events, transcript)

            # Step 6: Save results
            results = self._save_results(events, transcript, video_description)

            logger.info(f"Job {job_id} completed successfully")
            logger.info("=== NATIVE VIDEO PIPELINE COMPLETE ===")
            return results

        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            self.update_status({
                "status": "failed",
                "stage": "error",
                "error": str(e),
            })
            raise
