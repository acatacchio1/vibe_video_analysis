#!/usr/bin/env python3
"""
Worker process for video analysis.
Runs as subprocess, communicates via job directory files.
"""

import json
import os
import sys
import time
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any

# Constants
LLM_TIMEOUT = 300  # seconds (5 minutes)
MIN_NUM_PREDICT = 2048
DEFAULT_TEMPERATURE = 0.2

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
    """Run video analysis job"""
    import traceback

    # Load job config
    input_file = job_dir / "input.json"
    if not input_file.exists():
        logger.error(f"No input.json found at {input_file}")
        raise ValueError("No input.json found")

    logger.info(f"=== JOB START === dir={job_dir}")
    logger.info(f"Loading config from {input_file}")
    config = json.loads(input_file.read_text())
    logger.info(f"Config keys: {list(config.keys())}")

    video_path = config["video_path"]
    provider_type = config["provider_type"]
    provider_config = config["provider_config"]
    model = config["model"]
    params = config.get("params", {})
    job_id = config["job_id"]
    video_frames_dir = config.get("video_frames_dir", "")

    logger.info(f"video_path={video_path}")
    logger.info(f"provider_type={provider_type}")
    logger.info(f"model={model}")
    logger.info(f"params keys: {list(params.keys())}")
    logger.info(f"video_frames_dir={video_frames_dir}")

    # Update status
    update_status(
        job_dir,
        {
            "status": "running",
            "stage": "initializing",
            "progress": 0,
            "current_frame": 0,
            "total_frames": 0,
        },
    )

    try:
        # Import here to avoid loading heavy deps until needed
        logger.info("=== STAGE 0: Importing video_analyzer modules ===")
        from video_analyzer.config import Config
        from video_analyzer.frame import VideoProcessor
        from video_analyzer.analyzer import VideoAnalyzer
        from video_analyzer.audio_processor import AudioProcessor
        from video_analyzer.prompt import PromptLoader
        logger.info("All imports successful")

        # Setup paths
        output_dir = job_dir / "output"
        output_dir.mkdir(exist_ok=True)
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        # Create custom config
        config_data = {
            "clients": {
                "default": provider_type if provider_type == "ollama" else "openai_api",
                "temperature": params.get("temperature", 0.0),
            },
            "prompt_dir": "prompts",
            "prompts": [
                {"name": "Frame Analysis", "path": "frame_analysis/frame_analysis.txt"},
                {"name": "Video Reconstruction", "path": "frame_analysis/describe.txt"},
            ],
            "output_dir": str(output_dir),
            "frames": {
                "per_minute": params.get("frames_per_minute", 60 / max(params.get("fps", 1), 0.0167)),
                "max_count": params.get("max_frames", 2147483647),
            },
            "audio": {
                "whisper_model": params.get("whisper_model", "large"),
                "language": params.get("language", "en"),
                "device": params.get("device", "gpu"),
            },
            "keep_frames": params.get("keep_frames", False),
            "prompt": params.get("user_prompt", ""),
        }

        # Add provider-specific config
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

        # Write temp config
        config_file = job_dir / "config.json"
        config_file.write_text(json.dumps(config_data))
        logger.info(f"Wrote config to {config_file}")

        # Initialize config
        logger.info("=== STAGE 1: Audio extraction + transcription ===")
        va_config = Config(str(job_dir))

        update_status(job_dir, {"stage": "extracting_audio", "progress": 5})

        # Extract audio with ffmpeg
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
                    logger.info(f"No audio stream, skipping transcription")
                else:
                    logger.warning(f"Audio extraction failed: {stderr[-300:]}")
            elif not audio_path.exists() or audio_path.stat().st_size == 0:
                logger.info("No audio extracted, skipping transcription")
            else:
                audio_size = audio_path.stat().st_size
                logger.info(f"Audio extracted: {audio_path} ({audio_size} bytes)")

                # Transcribe with faster-whisper directly (bypassing external AudioProcessor)
                update_status(job_dir, {"stage": "transcribing", "progress": 10})

                device = config_data["audio"]["device"]
                if device == "gpu":
                    device = "cuda"
                compute_type = "float16"
                if device == "cpu":
                    compute_type = "int8"

                logger.info(f"Loading Whisper model '{config_data['audio']['whisper_model']}' on {device} (compute_type={compute_type})")
                from faster_whisper import WhisperModel
                model_whisper = WhisperModel(
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

                segments_iter, info = model_whisper.transcribe(
                    str(audio_path), beam_size=5, word_timestamps=False,
                    vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
                    language=lang_param,
                )
                segments = []
                full_text = []
                for seg in segments_iter:
                    segments.append({"text": seg.text, "start": seg.start})
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
            logger.warning(traceback.format_exc())
            transcript = None
        finally:
            try:
                if audio_path.exists():
                    audio_path.unlink()
                    logger.info(f"Cleaned up {audio_path}")
            except Exception:
                pass

        # Stage 2: Frame extraction
        logger.info("=== STAGE 2: Frame preparation ===")
        update_status(job_dir, {"stage": "extracting_frames", "progress": 15})

        pre_extracted_dir = Path(video_frames_dir) if video_frames_dir else None
        logger.info(f"pre_extracted_dir={pre_extracted_dir}")
        logger.info(f"pre_extracted_dir exists={pre_extracted_dir.exists() if pre_extracted_dir else 'N/A'}")
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

            all_frame_files = sorted(pre_extracted_dir.glob("frame_*.jpg"))
            total_available = len(all_frame_files)
            video_fps = meta.get("fps", 1)
            logger.info(f"total_available={total_available}, video_fps={video_fps}")

            start_frame = params.get("start_frame", 0) or 0
            end_frame = params.get("end_frame") or total_available
            logger.info(f"start_frame={start_frame}, end_frame={end_frame}")

            start_frame = max(0, min(start_frame, total_available - 1))
            end_frame = max(start_frame + 1, min(end_frame, total_available))

            selected_files = all_frame_files[start_frame:end_frame]
            logger.info(f"selected_files count={len(selected_files)}")

            fpm = params.get("frames_per_minute", 60)
            step = 1
            if video_fps > 0 and fpm < (video_fps * 60):
                step = max(1, int(video_fps * 60 / fpm))
                selected_files = selected_files[::step]

            logger.info(f"After step={step}: {len(selected_files)} frames")

            for i, fp in enumerate(selected_files):
                original_index = start_frame + i * step
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
            logger.info(
                f"Using {total_frames} pre-extracted frames "
                f"(range {start_frame}-{end_frame} of {total_available}, "
                f"step={step if fpm < (video_fps * 60) else 1})"
            )
        else:
            logger.info("No pre-extracted frames, using VideoProcessor to extract")
            processor = VideoProcessor(Path(video_path), frames_dir, model)
            frames = processor.extract_keyframes(
                frames_per_minute=config_data["frames"]["per_minute"],
                duration=params.get("duration"),
                max_frames=config_data["frames"]["max_count"],
                similarity_threshold=params.get("similarity_threshold", 10),
            )
            total_frames = len(frames)
            logger.info(f"VideoProcessor extracted {total_frames} frames")

        update_status(
            job_dir,
            {"stage": "analyzing_frames", "progress": 20, "total_frames": total_frames},
        )

        # Stage 3: Frame analysis
        logger.info("=== STAGE 3: Frame analysis ===")
        from video_analyzer.clients.ollama import OllamaClient
        from video_analyzer.clients.generic_openai_api import GenericOpenAIAPIClient

        if provider_type == "ollama":
            ollama_url = provider_config.get("url", "http://localhost:11434")
            # If host.docker.internal, fall back to localhost (running outside Docker)
            if "host.docker.internal" in ollama_url:
                ollama_url = ollama_url.replace("host.docker.internal", "localhost")
            logger.info(f"Creating OllamaClient with url={ollama_url}")
            client = OllamaClient(ollama_url)

            # Patch generate() to use /api/chat with think:false at the top level.
            import functools, types as _types

            _chat_url = f"{ollama_url.rstrip('/')}/api/chat"
            logger.info(f"Patched OllamaClient chat_url={_chat_url}")

            @functools.wraps(client.generate)
            def _patched_generate(
                self_inner,
                prompt,
                image_path=None,
                stream=False,
                model=model,
                temperature=0.2,
                num_predict=256,
            ):
                import requests as _req

                # Ollama /api/chat: images go in the message as base64 strings
                msg = {"role": "user", "content": prompt}
                if image_path:
                    msg["images"] = [self_inner.encode_image(image_path)]

                data = {
                    "model": model,
                    "messages": [msg],
                    "stream": False,
                    "think": False,  # top-level: disables reasoning mode
                    "options": {
                        "temperature": temperature or DEFAULT_TEMPERATURE,
                        "num_predict": max(num_predict, MIN_NUM_PREDICT),
                    },
                }
                logger.debug(f"Ollama request: model={model}, image={image_path}, url={_chat_url}")
                resp = _req.post(_chat_url, json=data, timeout=LLM_TIMEOUT)
                resp.raise_for_status()
                d = resp.json()
                # Normalise to the same shape the rest of the code expects
                return {
                    "response": d.get("message", {}).get("content", ""),
                    "done": d.get("done", True),
                    "eval_count": d.get("eval_count", 0),
                    "prompt_eval_count": d.get("prompt_eval_count", 0),
                }

            client.generate = _types.MethodType(_patched_generate, client)

        else:
            logger.info("Using OpenRouter client")
            client = GenericOpenAIAPIClient(
                provider_config["api_key"], "https://openrouter.ai/api/v1"
            )

        logger.info("Creating PromptLoader and VideoAnalyzer")
        prompt_loader = PromptLoader("prompts", config_data["prompts"])
        analyzer = VideoAnalyzer(
            client,
            model,
            prompt_loader,
            config_data["clients"]["temperature"],
            config_data["prompt"],
        )

        frame_analyses = []
        analyzer._total_frames = total_frames

        # Track costs for OpenRouter
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for i, frame in enumerate(frames):
            logger.info(f"Analyzing frame {i+1}/{total_frames}: {frame.path}")
            analysis = analyzer.analyze_frame(frame)
            frame_analyses.append(analysis)

            # Track tokens if available (OpenRouter)
            if "usage" in analysis:
                usage = analysis["usage"]
                total_prompt_tokens += usage.get("prompt_tokens", 0)
                total_completion_tokens += usage.get("completion_tokens", 0)

            # Progress: 20% to 80% for frame analysis
            progress = 20 + int((i + 1) / total_frames * 60)

            # Write frame analysis for real-time display
            frame_result = {
                "frame_number": i + 1,
                "total_frames": total_frames,
                "timestamp": frame.timestamp,
                "analysis": analysis.get("response", ""),
                "tokens": analysis.get("usage", {}),
            }

            # Append to frames log
            frames_file = job_dir / "frames.jsonl"
            with open(frames_file, "a") as f:
                f.write(json.dumps(frame_result) + "\n")

            update_status(
                job_dir,
                {
                    "progress": progress,
                    "current_frame": i + 1,
                    "last_frame_analysis": analysis.get("response", ""),
                },
            )

        # Stage 4: Video reconstruction
        logger.info("=== STAGE 4: Video reconstruction ===")
        update_status(job_dir, {"stage": "reconstructing", "progress": 85})

        video_description = analyzer.reconstruct_video(
            frame_analyses, frames, transcript
        )
        logger.info(f"Video description generated: type={type(video_description)}")

        # Save results
        user_prompt = params.get("user_prompt", "")
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
                "text": transcript.text if transcript else None,
                "segments": transcript.segments if transcript else None,
            }
            if transcript
            else None,
            "frame_analyses": frame_analyses,
            "video_description": video_description,
            "token_usage": {
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
            }
            if provider_type == "openrouter"
            else None,
        }

        results_file = output_dir / "results.json"
        results_file.write_text(json.dumps(results, indent=2))
        logger.info(f"Results saved to {results_file}")

        update_status(
            job_dir,
            {
                "status": "completed",
                "stage": "complete",
                "progress": 100,
                "results_file": str(results_file),
                "transcript": transcript.text if transcript else None,
                "video_description": video_description.get("response", "")
                if isinstance(video_description, dict)
                else str(video_description),
            },
        )

        logger.info(f"Job {job_id} completed successfully")
        logger.info("=== JOB END ===")

        # Queue automatic LLM analysis if user_prompt was provided
        if user_prompt:
            try:
                import requests

                # Format content for LLM
                content_parts = []
                if transcript and transcript.text:
                    content_parts.append(f"TRANSCRIPT:\n{transcript.text}")
                if video_description:
                    desc_text = (
                        video_description.get("response", "")
                        if isinstance(video_description, dict)
                        else str(video_description)
                    )
                    content_parts.append(f"VIDEO DESCRIPTION:\n{desc_text}")
                if frame_analyses:
                    frames_text = "\n".join(
                        [
                            f"Frame {i + 1}: {f.get('response', f.get('analysis', ''))}"
                            for i, f in enumerate(
                                frame_analyses[:20]
                            )  # Limit to first 20 frames
                        ]
                    )
                    content_parts.append(f"FRAME ANALYSES:\n{frames_text}")

                content = "\n\n".join(content_parts)

                # Determine provider info
                llm_provider_type = provider_type
                llm_model = model
                llm_api_key = ""
                llm_ollama_url = ""

                if provider_type == "ollama":
                    llm_ollama_url = provider_config.get("url", "")
                else:
                    llm_api_key = provider_config.get("api_key", "")

                # Submit to LLM chat queue
                llm_request = {
                    "provider_type": llm_provider_type,
                    "model": llm_model,
                    "prompt": user_prompt,
                    "content": content,
                    "api_key": llm_api_key,
                    "ollama_url": llm_ollama_url,
                }

                app_url = os.environ.get("APP_URL", "http://localhost:10000")
                response = requests.post(
                    f"{app_url}/api/llm/chat", json=llm_request, timeout=10
                )
                if response.status_code == 200:
                    llm_result = response.json()
                    logger.info(
                        f"Auto-queued LLM analysis for job {job_id}, chat job: {llm_result.get('job_id')}"
                    )
                else:
                    logger.warning(
                        f"Failed to auto-queue LLM analysis: {response.status_code}"
                    )
            except Exception as e:
                logger.error(f"Error auto-queuing LLM analysis: {e}")

    except ValueError as e:
        logger.error(f"Job {job_id} failed - validation error: {e}")
        logger.error(traceback.format_exc())
        update_status(job_dir, {"status": "failed", "error": str(e), "stage": "error"})
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Job {job_id} failed - runtime error: {e}")
        logger.error(traceback.format_exc())
        update_status(job_dir, {"status": "failed", "error": str(e), "stage": "error"})
        sys.exit(1)
    except IOError as e:
        logger.error(f"Job {job_id} failed - I/O error: {e}")
        logger.error(traceback.format_exc())
        update_status(job_dir, {"status": "failed", "error": str(e), "stage": "error"})
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info(f"Job {job_id} interrupted by user")
        update_status(
            job_dir,
            {"status": "cancelled", "error": "User cancelled", "stage": "error"},
        )
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Job {job_id} failed - unexpected error: {e}")
        logger.error(traceback.format_exc())
        update_status(job_dir, {"status": "failed", "error": str(e), "stage": "error"})
        sys.exit(1)
    except RuntimeError as e:
        logger.error(f"Job {job_id} failed - runtime error: {e}")
        logger.error(traceback.format_exc())
        update_status(job_dir, {"status": "failed", "error": str(e), "stage": "error"})
        sys.exit(1)
    except IOError as e:
        logger.error(f"Job {job_id} failed - I/O error: {e}")
        logger.error(traceback.format_exc())
        update_status(job_dir, {"status": "failed", "error": str(e), "stage": "error"})
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info(f"Job {job_id} interrupted by user")
        update_status(
            job_dir,
            {"status": "cancelled", "error": "User cancelled", "stage": "error"},
        )
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Job {job_id} failed - unexpected error: {e}")
        logger.error(traceback.format_exc())
        update_status(job_dir, {"status": "failed", "error": str(e), "stage": "error"})
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: worker.py <job_directory>")
        sys.exit(1)

    job_dir = Path(sys.argv[1])
    run_analysis(job_dir)
