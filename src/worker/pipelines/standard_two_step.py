"""
Standard two-step analysis pipeline.
Phase 1: Vision analysis per frame
Phase 2: Vision + transcript synthesis using secondary LLM
"""

import json
import logging
import os
import subprocess
import types
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, TYPE_CHECKING

from .base import AnalysisPipeline

if TYPE_CHECKING:
    from src.schemas import AnalysisParams

logger = logging.getLogger(__name__)

LLM_TIMEOUT = 300
MIN_NUM_PREDICT = 2048


def _synthesize_frame(
    frame_result: Dict[str, Any],
    phase2_provider_type: str,
    phase2_model: str,
    phase2_temperature: float,
    phase2_provider_config: Dict[str, Any],
    job_dir: Path,
) -> Optional[Dict[str, Any]]:
    """Synthesize frame analysis with transcript using secondary LLM"""
    try:
        import requests

        synthesis_prompt = f"""Combine the visual analysis with transcript context to create an enhanced description.

VISION ANALYSIS:
{frame_result.get('analysis', '')}

TRANSCRIPT CONTEXT:
{frame_result.get('transcript_context', '')}

TIMESTAMP: {frame_result.get('corrected_ts', frame_result.get('timestamp', 0)):.2f} seconds (original: {frame_result.get('original_ts', frame_result.get('timestamp', 0)):.2f}s)

Create a comprehensive analysis that integrates what's visually present with what's being said at this moment in the video. Focus on:
1. How the transcript context relates to or explains what's shown visually
2. Connections between audio content and visual elements
3. Any contradictions or confirmations between what's said and what's shown
4. Additional understanding the transcript provides about the visual scene
5. How this moment fits into the broader narrative

ENHANCED ANALYSIS:"""

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

        synthesis_result = {
            "frame_number": frame_result["frame_number"],
            "original_frame": frame_result.get("original_frame", frame_result["frame_number"]),
            "timestamp": frame_result.get("timestamp", 0),
            "original_ts": frame_result.get("original_ts", frame_result.get("timestamp", 0)),
            "corrected_ts": frame_result.get("corrected_ts", frame_result.get("timestamp", 0)),
            "vision_analysis": frame_result.get("analysis", ""),
            "transcript_context": frame_result.get("transcript_context", ""),
            "combined_analysis": result,
            "tokens": tokens,
            "phase2_provider_type": phase2_provider_type,
            "phase2_model": phase2_model,
            "phase2_temperature": phase2_temperature,
        }

        synthesis_file = job_dir / "synthesis.jsonl"
        with open(synthesis_file, "a") as f:
            f.write(json.dumps(synthesis_result) + "\n")

        logger.info(f"Frame {frame_result['frame_number']} synthesis completed")
        return synthesis_result

    except Exception as e:
        logger.error(f"Frame {frame_result.get('frame_number', 'unknown')} synthesis failed: {e}")
        return None


def _safe_get_transcript_text(transcript):
    if transcript is None:
        return None
    if hasattr(transcript, 'get'):
        try:
            return transcript.get('text')
        except (AttributeError, KeyError):
            pass
    if hasattr(transcript, 'text'):
        try:
            return transcript.text
        except AttributeError:
            pass
    try:
        return transcript['text']
    except (KeyError, TypeError):
        pass
    return None


def _safe_get_transcript_segments(transcript):
    if transcript is None:
        return None
    if hasattr(transcript, 'get'):
        try:
            return transcript.get('segments')
        except (AttributeError, KeyError):
            pass
    if hasattr(transcript, 'segments'):
        try:
            return transcript.segments
        except AttributeError:
            pass
    try:
        return transcript['segments']
    except (KeyError, TypeError):
        pass
    return None


class StandardTwoStepPipeline(AnalysisPipeline):
    """Standard two-step analysis pipeline."""

    def run(self) -> Dict[str, Any]:
        logger.info("=== STANDARD TWO-STEP PIPELINE START ===")

        # Use typed config when available (factory builds it automatically)
        cfg = self.typed_config
        if cfg is None:
            raise RuntimeError("StandardTwoStepPipeline requires typed JobConfig")

        video_path = cfg.video_path_obj
        provider_type = cfg.provider_type
        provider_config = cfg.provider_config.model_dump()
        model = cfg.model
        params = cfg.params
        job_id = cfg.job_id
        video_frames_dir = cfg.video_frames_dir

        two_step_enabled = params.phase2.enabled
        phase2_provider_type = params.phase2.provider_type
        phase2_model = params.phase2.model
        phase2_temperature = params.phase2.temperature
        phase2_provider_config = params.phase2.provider_config.model_dump()

        if phase2_provider_type == "litellm" and not phase2_provider_config.get("url"):
            phase2_provider_config["url"] = "http://172.16.17.3:4000/v1"

        logger.info(f"video_path={video_path}")
        logger.info(f"provider_type={provider_type}")
        logger.info(f"model={model}")
        logger.info(f"video_frames_dir={video_frames_dir}")

        self.update_status({
            "status": "running",
            "stage": "initializing",
            "progress": 0,
            "current_frame": 0,
            "total_frames": 0,
            "pipeline": "standard_two_step",
        })

        try:
            logger.info("=== STAGE 0: Importing video_analyzer modules ===")
            from video_analyzer.config import Config
            from video_analyzer.frame import VideoProcessor
            from video_analyzer.analyzer import VideoAnalyzer
            from video_analyzer.prompt import PromptLoader
            logger.info("All imports successful")

            output_dir = self.output_dir
            frames_dir = output_dir / "frames"
            frames_dir.mkdir(exist_ok=True)

            config_data = self._build_config(
                provider_type, provider_config, model, params,
                phase2_provider_type, phase2_provider_config
            )

            config_file = self.job_dir / "config.json"
            config_file.write_text(json.dumps(config_data))
            logger.info(f"Wrote config to {config_file}")

            logger.info("=== STAGE 1: Audio extraction + transcription ===")
            self.update_status({"stage": "extracting_audio", "progress": 5})

            transcript = self._extract_audio_and_transcribe(video_path, config_data)

            logger.info("=== STAGE 2: Frame preparation ===")
            self.update_status({"stage": "extracting_frames", "progress": 15})

            frames, total_frames = self._prepare_frames(
                video_path, video_frames_dir, params, config_data, frames_dir, total_frames_placeholder=0
            )

            self.update_status({
                "stage": "analyzing_frames",
                "progress": 20,
                "total_frames": total_frames,
            })

            logger.info("=== STAGE 3: Frame analysis ===")
            frame_analyses = self._analyze_frames(
                frames, total_frames, provider_type, provider_config, model,
                config_data, transcript, video_frames_dir, two_step_enabled,
                phase2_provider_type, phase2_model, phase2_temperature, phase2_provider_config,
            )

            logger.info("=== STAGE 4: Video reconstruction ===")
            self.update_status({"stage": "reconstructing", "progress": 85})

            video_description = self._reconstruct_video(
                frame_analyses, frames, transcript, provider_type, provider_config, model, config_data, video_path
            )

            results = self._save_results(
                job_id, provider_type, model, total_frames, transcript,
                frame_analyses, video_description, params, output_dir
            )

            self.update_status({
                "status": "completed",
                "stage": "complete",
                "progress": 100,
                "results_file": str(output_dir / "results.json"),
            })

            logger.info(f"Job {job_id} completed successfully")
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

    def _build_config(
        self,
        provider_type: str,
        provider_config: Dict[str, Any],
        model: str,
        params: "AnalysisParams",
        phase2_provider_type: str,
        phase2_provider_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build video_analyzer library config dict from typed params."""
        config_data = {
            "clients": {
                "default": "openai_api",
                "temperature": params.temperature,
            },
            "analysis_pipeline": {
                "two_step_enabled": params.phase2.enabled,
                "phase2_provider_type": params.phase2.provider_type,
                "phase2_model": params.phase2.model,
                "phase2_temperature": params.phase2.temperature,
                "max_concurrent_synthesis": params.phase2.max_concurrent_synthesis,
            },
            "prompt_dir": "prompts",
            "prompts": [
                {"name": "Frame Analysis", "path": "frame_analysis/frame_analysis.txt"},
                {"name": "Video Reconstruction", "path": "frame_analysis/describe.txt"},
                {"name": "Frame Synthesis", "path": "frame_analysis/synthesis.txt"},
            ],
            "output_dir": str(self.output_dir),
            "frames": {
                "per_minute": params.frames.frames_per_minute,
                "max_count": params.frames.max_frames,
            },
            "audio": {
                "whisper_model": params.audio.whisper_model,
                "language": params.audio.language,
                "device": params.audio.device,
            },
            "prompt": params.user_prompt,
        }

        if provider_type == "litellm":
            config_data["clients"]["default"] = "openai_api"
            config_data["clients"]["openai_api"] = {
                "api_key": "",
                "api_url": provider_config.get("url", "http://172.16.17.3:4000/v1"),
                "model": model,
            }
        else:
            config_data["clients"]["default"] = "openai_api"
            config_data["clients"]["openai_api"] = {
                "api_key": provider_config["api_key"],
                "api_url": "https://openrouter.ai/api/v1",
                "model": model,
            }

        if phase2_provider_type == "litellm":
            config_data["clients"]["default"] = "openai_api"
            config_data["clients"]["phase2_openai_api"] = {
                "api_key": "",
                "api_url": phase2_provider_config.get("url", "http://172.16.17.3:4000/v1"),
                "model": params.phase2.model,
            }
        else:
            config_data["clients"]["default"] = "openai_api"
            config_data["clients"]["phase2_openai_api"] = {
                "api_key": phase2_provider_config.get("api_key", ""),
                "api_url": "https://openrouter.ai/api/v1",
                "model": params.phase2.model,
            }

        return config_data

    def _extract_audio_and_transcribe(self, video_path: Path, config_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        output_dir = self.output_dir
        audio_path = output_dir / "audio.wav"
        transcript = None

        try:
            extract_cmd = [
                "ffmpeg", "-y", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(audio_path),
            ]
            logger.info(f"Running: {' '.join(extract_cmd)}")
            proc = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=120)
            logger.info(f"ffmpeg returncode={proc.returncode}")

            if proc.returncode != 0:
                stderr = proc.stderr or ""
                logger.warning(f"ffmpeg stderr (last 300 chars): {stderr[-300:]}")
                if "does not contain any stream" in stderr or "no audio" in stderr.lower():
                    logger.info("No audio stream, skipping transcription")
                else:
                    logger.warning(f"Audio extraction failed: {stderr[-300:]}")
            elif not audio_path.exists() or audio_path.stat().st_size == 0:
                logger.info("No audio extracted, skipping transcription")
            else:
                audio_size = audio_path.stat().st_size
                logger.info(f"Audio extracted: {audio_path} ({audio_size} bytes)")

                self.update_status({"stage": "transcribing", "progress": 10})

                device = config_data["audio"]["device"]
                if device == "gpu":
                    device = "cuda"
                compute_type = "float16"
                if device == "cpu":
                    compute_type = "int8"

                logger.info(f"Loading Whisper model '{config_data['audio']['whisper_model']}' on {device} (compute_type={compute_type})")
                from faster_whisper import WhisperModel
                whisper = WhisperModel(
                    config_data["audio"]["whisper_model"],
                    device=device,
                    compute_type=compute_type,
                )
                logger.info("Whisper model loaded successfully")

                accepted_languages = {
                    "af","am","ar","as","az","ba","be","bg","bn","bo","br","bs","ca","cs",
                    "cy","da","de","el","en","es","et","eu","fa","fi","fo","fr","gl","gu",
                    "ha","haw","he","hi","hr","ht","hu","hy","id","is","it","ja","jw","ka",
                    "kk","km","kn","ko","la","lb","ln","lo","lt","lv","mg","mi","mk","ml",
                    "mn","mr","ms","mt","my","ne","nl","nn","no","oc","pa","pl","ps","pt",
                    "ro","ru","sa","sd","si","sk","sl","sn","so","sq","sr","su","sv","sw",
                    "ta","te","tg","th","tk","tl","tr","tt","uk","ur","uz","vi","yi","yo",
                    "zh","yue",
                }
                lang = config_data["audio"]["language"]
                lang_param = lang if lang in accepted_languages else None
                logger.info(f"Transcribing with language={lang_param}")

                segments_iter, info = whisper.transcribe(
                    str(audio_path), beam_size=5, word_timestamps=False,
                    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
                    language=lang_param,
                )
                segments = []
                full_text = []
                for seg in segments_iter:
                    segments.append({"text": seg.text, "start": seg.start, "end": seg.end})
                    full_text.append(seg.text)

                transcript = {
                    "text": " ".join(full_text),
                    "segments": segments,
                    "language": info.language if hasattr(info, "language") else lang,
                    "whisper_model": config_data["audio"]["whisper_model"],
                }
                logger.info(f"Transcription complete: {len(segments)} segments, text length={len(transcript['text'])}")

        except Exception as e:
            logger.warning(f"Audio processing failed: {e}")
        finally:
            try:
                if audio_path.exists():
                    audio_path.unlink()
            except Exception:
                pass

        if transcript is None:
            transcript = self.load_transcript()
            if transcript:
                segs = _safe_get_transcript_segments(transcript) or []
                logger.info(f"Loaded pre-existing transcript with {len(segs)} segments")
            else:
                logger.info("No pre-existing transcript found, proceeding without audio context")

        return transcript

    def _prepare_frames(
        self,
        video_path: Path,
        video_frames_dir: str,
        params: "AnalysisParams",
        config_data: Dict[str, Any],
        frames_dir: Path,
        total_frames_placeholder: int = 0,
    ) -> tuple[List[Any], int]:
        pre_extracted_dir = Path(video_frames_dir) if video_frames_dir else None
        if pre_extracted_dir and pre_extracted_dir.exists():
            frame_count = len(list(pre_extracted_dir.glob("frame_*.jpg")))
            logger.info(f"Found {frame_count} frame_*.jpg files in pre_extracted_dir")

        use_pre_extracted = (
            pre_extracted_dir
            and pre_extracted_dir.exists()
            and any(pre_extracted_dir.glob("frame_*.jpg"))
        )
        logger.info(f"use_pre_extracted={use_pre_extracted}")

        frames = []
        total_frames = 0

        if use_pre_extracted:
            meta_path = pre_extracted_dir.parent / "frames_meta.json"
            meta = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    logger.info(f"Loaded frames_meta: {meta}")
                except Exception as e:
                    logger.warning(f"Failed to parse frames_meta.json: {e}")

            frames_index = {}
            frames_index_path = pre_extracted_dir.parent / "frames_index.json"
            if frames_index_path.exists():
                try:
                    frames_index = json.loads(frames_index_path.read_text())
                    logger.info(f"Loaded frames_index with {len(frames_index)} entries")
                except Exception as e:
                    logger.warning(f"Failed to parse frames_index.json: {e}")

            all_frame_files = sorted(pre_extracted_dir.glob("frame_*.jpg"))
            total_available = len(all_frame_files)
            video_fps = meta.get("fps", 1)
            logger.info(f"total_available={total_available}, video_fps={video_fps}")

            start_frame = params.frames.start_frame or 0
            end_frame = params.frames.end_frame or total_available
            start_frame = max(0, min(start_frame, total_available - 1))
            end_frame = max(start_frame + 1, min(end_frame, total_available))

            selected_files = all_frame_files[start_frame:end_frame]

            fpm = params.frames.frames_per_minute
            step = 1
            if video_fps > 0 and fpm < (video_fps * 60):
                step = max(1, int(video_fps * 60 / fpm))
                selected_files = selected_files[::step]

            logger.info(f"After step={step}: {len(selected_files)} frames")

            for i, fp in enumerate(selected_files):
                original_index = start_frame + i * step
                frame_num = original_index + 1
                if frames_index and str(frame_num) in frames_index:
                    timestamp = frames_index[str(frame_num)]
                else:
                    timestamp = original_index / video_fps if video_fps > 0 else float(i)
                frames.append(
                    type(
                        "Frame",
                        (),
                        {
                            "number": i,
                            "path": fp,
                            "timestamp": timestamp,
                            "score": 0,
                        },
                    )()
                )

            total_frames = len(frames)
            logger.info(f"Using {total_frames} pre-extracted frames (range {start_frame}-{end_frame} of {total_available}, step={step})")
        else:
            logger.info("No pre-extracted frames, using VideoProcessor to extract")
            from video_analyzer.frame import VideoProcessor
            processor = VideoProcessor(video_path, frames_dir, self.config.get("model", ""))
            frames = processor.extract_keyframes(
                frames_per_minute=config_data["frames"]["per_minute"],
                duration=params.duration,
                max_frames=config_data["frames"]["max_count"],
                similarity_threshold=int(params.frames.similarity_threshold),
            )
            total_frames = len(frames)
            logger.info(f"VideoProcessor extracted {total_frames} frames")

        if video_frames_dir:
            meta_path = Path(video_frames_dir).parent / "frames_meta.json"
            try:
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text())
                    original_frame_count = meta.get("frame_count", total_frames)
                else:
                    meta = {}
                    original_frame_count = total_frames
                meta["analysis_frame_count"] = total_frames
                meta["frame_count"] = original_frame_count
                meta_path.write_text(json.dumps(meta))
            except Exception as e:
                logger.warning(f"Failed to update frames_meta.json: {e}")

        return frames, total_frames

    def _analyze_frames(
        self,
        frames: List[Any],
        total_frames: int,
        provider_type: str,
        provider_config: Dict[str, Any],
        model: str,
        config_data: Dict[str, Any],
        transcript: Optional[Dict[str, Any]],
        video_frames_dir: str,
        two_step_enabled: bool,
        phase2_provider_type: str,
        phase2_model: str,
        phase2_temperature: float,
        phase2_provider_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        logger.info("=== STAGE 3: Frame analysis ===")
        from video_analyzer.clients.generic_openai_api import GenericOpenAIAPIClient

        config_temperature = config_data["clients"].get("temperature", 0.2)
        logger.info(f"Using temperature={config_temperature} for LLM calls")

        if provider_type == "litellm":
            litellm_url = provider_config.get("url", "http://172.16.17.3:4000/v1")
            if "host.docker.internal" in litellm_url:
                if not Path("/.dockerenv").exists():
                    litellm_url = litellm_url.replace("host.docker.internal", "localhost")
            logger.info(f"Creating GenericOpenAIAPIClient with url={litellm_url}")
            client = GenericOpenAIAPIClient(
                "", litellm_url
            )

        else:
            logger.info("Using OpenRouter client")
            client = GenericOpenAIAPIClient(
                provider_config["api_key"], "https://openrouter.ai/api/v1"
            )

        logger.info("Creating PromptLoader and VideoAnalyzer")
        from video_analyzer.prompt import PromptLoader
        from video_analyzer.analyzer import VideoAnalyzer

        prompt_loader = PromptLoader("prompts", config_data["prompts"])
        analyzer = VideoAnalyzer(
            client,
            model,
            prompt_loader,
            config_data["clients"]["temperature"],
            config_data["prompt"],
        )

        logger.info(f"Analyzer frame_prompt type: {type(analyzer.frame_prompt)}")
        if analyzer.frame_prompt:
            has_context = "{TRANSCRIPT_CONTEXT}" in analyzer.frame_prompt
            has_recent = "{TRANSCRIPT_RECENT}" in analyzer.frame_prompt
            has_prior = "{TRANSCRIPT_PRIOR}" in analyzer.frame_prompt
            logger.info(f"Frame prompt transcript tokens: TRANSCRIPT_CONTEXT={has_context}, TRANSCRIPT_RECENT={has_recent}, TRANSCRIPT_PRIOR={has_prior}")
            if not (has_context or has_recent or has_prior):
                logger.warning("Transcript tokens NOT found in frame prompt template")
                transcript_prompt_paths = [
                    Path("/home/anthony/venvs/video-analyzer/lib/python3.13/site-packages/video_analyzer/prompts/frame_analysis/frame_with_transcript.txt"),
                    Path("/usr/local/lib/python3.10/dist-packages/video_analyzer/prompts/frame_analysis/frame_with_transcript.txt"),
                    Path("/app/venvs/video-analyzer/lib/python3.13/site-packages/video_analyzer/prompts/frame_analysis/frame_with_transcript.txt"),
                ]
                for prompt_path in transcript_prompt_paths:
                    if prompt_path.exists():
                        analyzer.frame_prompt = prompt_path.read_text()
                        logger.info(f"Loaded transcript-aware prompt from {prompt_path}")
                        break

        frame_analyses = []
        analyzer._total_frames = total_frames

        dedup_map = {}
        dedup_path = Path(video_frames_dir).parent / "dedup_results.json" if video_frames_dir else None
        if dedup_path and dedup_path.exists():
            try:
                dedup_map = json.loads(dedup_path.read_text())
                logger.info(f"Loaded dedup mapping with {len(dedup_map.get('dedup_to_original_mapping', {}))} entries")
            except Exception as e:
                logger.warning(f"Failed to load dedup mapping: {e}")

        transcript_segments = []
        if transcript:
            try:
                from src.utils import get_transcript_segments_with_end_times
                transcript_segments = get_transcript_segments_with_end_times(transcript)
                logger.info(f"Loaded {len(transcript_segments)} transcript segments with validated timestamps")
            except ImportError as e:
                logger.warning(f"Failed to import transcript utilities: {e}")
                transcript_segments = _safe_get_transcript_segments(transcript)
                if transcript_segments:
                    logger.info(f"Loaded {len(transcript_segments)} transcript segments (no timestamp validation)")

        _prev_frame_ts = None
        _total_frames = len(frames)

        MAX_PREVIOUS_FRAMES = 3
        _original_analyze_frame = analyzer.analyze_frame

        def _patched_analyze_frame(self_inner, frame):
            if len(self_inner.previous_analyses) > MAX_PREVIOUS_FRAMES:
                self_inner.previous_analyses = self_inner.previous_analyses[-MAX_PREVIOUS_FRAMES:]
            return _original_analyze_frame(frame)

        analyzer.analyze_frame = types.MethodType(_patched_analyze_frame, analyzer)

        total_prompt_tokens = 0
        total_completion_tokens = 0

        for i, frame in enumerate(frames):
            try:
                stem_parts = Path(frame.path).stem.split("_")
                disk_frame_num = int(stem_parts[-1]) if len(stem_parts) >= 2 else (i + 1)
            except (ValueError, IndexError):
                disk_frame_num = i + 1

            orig_ts = dedup_map.get("original_timestamps", {}).get(str(disk_frame_num), frame.timestamp)

            recent_transcript = ""
            prior_transcript = ""
            transcript_note = ""
            current_ts = orig_ts

            if len(transcript_segments) > 0:
                first_seg_start = transcript_segments[0]["start"]
                last_seg = transcript_segments[-1]
                last_seg_end = last_seg.get("end", last_seg["start"] + 5)
                time_buffer = 15.0
                is_near_transcript = (
                    (first_seg_start - time_buffer) <= current_ts <= (last_seg_end + time_buffer)
                )

                if is_near_transcript:
                    current_seg_idx = -1
                    for idx, seg in enumerate(transcript_segments):
                        seg_end = seg.get("end", seg["start"] + 5)
                        if seg["start"] <= current_ts <= seg_end:
                            current_seg_idx = idx
                            break
                        elif seg["start"] < current_ts:
                            current_seg_idx = idx

                    if current_seg_idx >= 0:
                        seg_start = transcript_segments[current_seg_idx]["start"]
                        seg_end = transcript_segments[current_seg_idx].get("end", seg_start + 5)

                        if seg_start <= current_ts <= seg_end:
                            recent_transcript = transcript_segments[current_seg_idx]["text"]
                            prior_start = max(0, current_seg_idx - 2)
                            if current_seg_idx > prior_start:
                                prior_segs = transcript_segments[prior_start:current_seg_idx]
                                prior_transcript = " ".join(s["text"] for s in prior_segs)
                        elif current_ts < first_seg_start:
                            transcript_note = "[Transcript begins later in video]"
                        elif current_ts > last_seg_end:
                            if current_ts - last_seg_end < 30:
                                recent_transcript = last_seg["text"]
                                transcript_note = f"[Transcript ended {current_ts - last_seg_end:.0f}s ago]"
                            else:
                                transcript_note = f"[Transcript ended {current_ts - last_seg_end:.0f}s ago, may not be relevant]"
                else:
                    if current_ts < first_seg_start:
                        transcript_note = f"[Transcript begins {abs(current_ts - first_seg_start):.0f}s later in video]"
                    else:
                        transcript_note = f"[Transcript ended {current_ts - last_seg_end:.0f}s ago, may not be relevant]"

            has_context_token = "{TRANSCRIPT_CONTEXT}" in analyzer.frame_prompt
            has_recent_token = "{TRANSCRIPT_RECENT}" in analyzer.frame_prompt
            has_prior_token = "{TRANSCRIPT_PRIOR}" in analyzer.frame_prompt

            context_section = ""

            if has_context_token:
                if recent_transcript or prior_transcript or transcript_note:
                    prior_text = prior_transcript if prior_transcript else "(none)"
                    tc = f"\nRECENT TRANSCRIPT: {recent_transcript}\n\nPRIOR TRANSCRIPT: {prior_text}\n"
                    if transcript_note:
                        tc += f"\nNOTE: {transcript_note}\n"
                    analyzer.frame_prompt = analyzer.frame_prompt.replace("{TRANSCRIPT_CONTEXT}", tc)
                    context_section = tc.strip()
                else:
                    analyzer.frame_prompt = analyzer.frame_prompt.replace(
                        "{TRANSCRIPT_CONTEXT}", "\nRECENT TRANSCRIPT: \n\nPRIOR TRANSCRIPT: none\n"
                    )
                    context_section = "No transcript available"

            elif has_recent_token or has_prior_token:
                if has_recent_token:
                    analyzer.frame_prompt = analyzer.frame_prompt.replace("{TRANSCRIPT_RECENT}", recent_transcript)
                if has_prior_token:
                    analyzer.frame_prompt = analyzer.frame_prompt.replace("{TRANSCRIPT_PRIOR}", prior_transcript)

                if recent_transcript or transcript_note:
                    if recent_transcript:
                        context_section = f"RECENT: {recent_transcript}"
                        if prior_transcript:
                            context_section += f"\nPRIOR: {prior_transcript}"
                    if transcript_note:
                        context_section = context_section + f"\nNOTE: {transcript_note}" if context_section else f"NOTE: {transcript_note}"
                else:
                    context_section = "No transcript context available"
            else:
                tc = ""
                if recent_transcript:
                    tc = f"\n\nTranscript context for this timeframe: {recent_transcript}"
                    context_section = f"RECENT: {recent_transcript}"
                    if prior_transcript:
                        tc += f"\nPrevious context: {prior_transcript}"
                        context_section += f"\nPRIOR: {prior_transcript}"
                    if transcript_note:
                        tc += f"\n{transcript_note}"
                        context_section += f"\nNOTE: {transcript_note}"
                    analyzer.frame_prompt += tc
                elif transcript_note:
                    tc = f"\n\n{transcript_note}"
                    context_section = f"NOTE: {transcript_note}"
                    analyzer.frame_prompt += tc
                else:
                    context_section = "No transcript available"

            _prev_frame_ts = current_ts

            logger.info(f"Analyzing frame {i+1}/{_total_frames}: {frame.path}")
            analysis = analyzer.analyze_frame(frame)
            frame_analyses.append(analysis)

            if "usage" in analysis:
                usage = analysis["usage"]
                total_prompt_tokens += usage.get("prompt_tokens", 0)
                total_completion_tokens += usage.get("completion_tokens", 0)

            progress = 20 + int((i + 1) / _total_frames * 60)
            orig_frame = dedup_map.get("dedup_to_original_mapping", {}).get(str(disk_frame_num), disk_frame_num)

            frame_result = {
                "frame_number": disk_frame_num,
                "total_frames": _total_frames,
                "original_frame": orig_frame,
                "timestamp": frame.timestamp,
                "original_ts": orig_ts,
                "corrected_ts": current_ts,
                "analysis": analysis.get("response", ""),
                "transcript_context": context_section,
                "tokens": analysis.get("usage", {}),
            }

            frames_file = self.job_dir / "frames.jsonl"
            with open(frames_file, "a") as f:
                f.write(json.dumps(frame_result) + "\n")

            self.update_status({
                "progress": progress,
                "current_frame": i + 1,
                "total_frames": _total_frames,
                "last_frame_analysis": analysis.get("response", ""),
            })

            if two_step_enabled and frame_result.get("analysis"):
                try:
                    synthesis_result = _synthesize_frame(
                        frame_result=frame_result,
                        phase2_provider_type=phase2_provider_type,
                        phase2_model=phase2_model,
                        phase2_temperature=phase2_temperature,
                        phase2_provider_config=phase2_provider_config,
                        job_dir=self.job_dir,
                    )
                    if synthesis_result:
                        synthesis_progress = (i + 1) / _total_frames * 100
                        self.update_status({
                            "synthesis_progress": synthesis_progress,
                            "last_synthesis_frame": frame_result['frame_number'],
                        })
                except Exception as e:
                    logger.error(f"Error during frame {frame_result['frame_number']} synthesis: {e}")

        logger.info(f"Frame analysis complete: {len(frame_analyses)} frames")
        return frame_analyses

    def _reconstruct_video(
        self,
        frame_analyses: List[Dict[str, Any]],
        frames: List[Any],
        transcript: Optional[Dict[str, Any]],
        provider_type: str,
        provider_config: Dict[str, Any],
        model: str,
        config_data: Dict[str, Any],
        video_path: Path,
    ) -> Any:
        logger.info("=== STAGE 4: Video reconstruction ===")

        transcript_for_reconstruct = transcript
        if isinstance(transcript, dict):
            try:
                from video_analyzer.audio_processor import AudioTranscript
                segments = _safe_get_transcript_segments(transcript) or []
                text = _safe_get_transcript_text(transcript) or ""
                if not text and segments:
                    text_parts = []
                    for seg in segments:
                        if hasattr(seg, 'get'):
                            text_parts.append(seg.get("text", ""))
                        elif hasattr(seg, 'text'):
                            text_parts.append(seg.text)
                        elif isinstance(seg, dict):
                            text_parts.append(seg.get("text", ""))
                        else:
                            text_parts.append(str(seg))
                    text = " ".join(text_parts).strip()

                language = "en"
                if hasattr(transcript, 'get'):
                    language = transcript.get("language", "en")
                elif hasattr(transcript, 'language'):
                    language = transcript.language
                elif isinstance(transcript, dict):
                    language = transcript.get("language", "en")

                transcript_for_reconstruct = AudioTranscript(
                    text=text, segments=segments, language=language
                )
                logger.info(f"Converted transcript dict to AudioTranscript object with {len(segments)} segments")
            except Exception as e:
                logger.warning(f"Failed to convert transcript to AudioTranscript: {e}")
                transcript_for_reconstruct = None

        from video_analyzer.analyzer import VideoAnalyzer
        from video_analyzer.prompt import PromptLoader
        from video_analyzer.clients.generic_openai_api import GenericOpenAIAPIClient

        if provider_type == "litellm":
            client = GenericOpenAIAPIClient(
                "", provider_config.get("url", "http://172.16.17.3:4000/v1")
            )
        else:
            client = GenericOpenAIAPIClient(
                provider_config["api_key"], "https://openrouter.ai/api/v1"
            )

        prompt_loader = PromptLoader("prompts", config_data["prompts"])
        analyzer = VideoAnalyzer(
            client, model, prompt_loader,
            config_data["clients"]["temperature"],
            config_data["prompt"],
        )

        video_description = analyzer.reconstruct_video(
            frame_analyses, frames, transcript_for_reconstruct
        )
        logger.info(f"Video description generated: type={type(video_description)}")
        return video_description

    def _save_results(
        self,
        job_id: str,
        provider_type: str,
        model: str,
        total_frames: int,
        transcript: Optional[Dict[str, Any]],
        frame_analyses: List[Dict[str, Any]],
        video_description: Any,
        params: "AnalysisParams",
        output_dir: Path,
    ) -> Dict[str, Any]:
        user_prompt = params.user_prompt

        total_prompt_tokens = sum(
            f.get("tokens", {}).get("prompt_tokens", 0) for f in frame_analyses
        )
        total_completion_tokens = sum(
            f.get("tokens", {}).get("completion_tokens", 0) for f in frame_analyses
        )

        results = {
            "metadata": {
                "job_id": job_id,
                "provider": provider_type,
                "model": model,
                "frames_processed": total_frames,
                "transcription_successful": transcript is not None,
                "user_prompt": user_prompt,
            },
            "transcript": {
                "text": _safe_get_transcript_text(transcript),
                "segments": _safe_get_transcript_segments(transcript),
            } if transcript else None,
            "frame_analyses": frame_analyses,
            "video_description": video_description,
            "token_usage": {
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
            } if provider_type == "openrouter" else None,
        }

        results_file = output_dir / "results.json"
        results_file.write_text(json.dumps(results, indent=2))
        logger.info(f"Results saved to {results_file}")

        desc_text = (
            video_description.get("response", "")
            if isinstance(video_description, dict)
            else str(video_description)
        )
        self.update_status({
            "status": "completed",
            "stage": "complete",
            "progress": 100,
            "results_file": str(results_file),
            "transcript": _safe_get_transcript_text(transcript),
            "video_description": desc_text,
        })

        if user_prompt:
            try:
                import requests
                content_parts = []
                if transcript:
                    tt = _safe_get_transcript_text(transcript)
                    if tt:
                        content_parts.append(f"TRANSCRIPT:\n{tt}")
                if video_description:
                    content_parts.append(f"VIDEO DESCRIPTION:\n{desc_text}")
                if frame_analyses:
                    frames_text = "\n".join(
                        f"Frame {i + 1}: {f.get('response', f.get('analysis', ''))}"
                        for i, f in enumerate(frame_analyses[:20])
                    )
                    content_parts.append(f"FRAME ANALYSES:\n{frames_text}")

                content = "\n\n".join(content_parts)

                app_url = self.config.get("app_url", os.environ.get("APP_URL", "http://localhost:10000"))
                llm_request = {
                    "provider_type": provider_type,
                    "model": model,
                    "prompt": user_prompt,
                    "content": content,
                    "api_key": provider_config.get("api_key", ""),
                    "litellm_url": provider_config.get("url", ""),
                }
                response = requests.post(f"{app_url}/api/llm/chat", json=llm_request, timeout=10)
                if response.status_code == 200:
                    llm_result = response.json()
                    logger.info(f"Auto-queued LLM analysis for job {job_id}, chat job: {llm_result.get('job_id')}")
                else:
                    logger.warning(f"Failed to auto-queue LLM analysis: {response.status_code}")
            except Exception as e:
                logger.error(f"Error auto-queuing LLM analysis: {e}")

        return results
