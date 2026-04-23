"""
Worker entry point
"""
import sys
from pathlib import Path


def run_analysis(job_dir: Path):
    """Run analysis for a job"""
    import json
    import subprocess
    import os
    import signal
    import time
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(job_dir / "worker.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger(__name__)

    input_file = job_dir / "input.json"
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        sys.exit(1)

    config = json.loads(input_file.read_text())
    params = config.get("params", {})

    video_path = config.get("video_path")
    model = config.get("model")
    provider_type = config.get("provider_type")
    provider_name = config.get("provider_name")
    provider_config = config.get("provider_config", {})
    video_frames_dir = config.get("video_frames_dir", "")

    status_file = job_dir / "status.json"
    frames_file = job_dir / "frames.jsonl"
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    def update_status(**kwargs):
        status = {}
        if status_file.exists():
            try:
                status = json.loads(status_file.read_text())
            except Exception:
                pass
        status.update(kwargs)
        status_file.write_text(json.dumps(status, indent=2))

    def append_frame(frame_data):
        with open(frames_file, "a") as f:
            f.write(json.dumps(frame_data) + "\n")

    # Patch Ollama client to add think:false
    if provider_type == "ollama":
        try:
            import ollama
            original_chat = ollama.chat

            def patched_chat(model_name, messages=None, stream=False, **kwargs):
                if messages:
                    for msg in messages:
                        if "options" not in msg:
                            msg["options"] = {}
                        msg["options"]["think"] = False
                return original_chat(model=model_name, messages=messages, stream=stream, **kwargs)

            ollama.chat = patched_chat
        except Exception:
            pass

    # Stage 1: Get frame list
    update_status(stage="preparing", progress=0)
    logger.info(f"Starting analysis for {video_path}")

    frame_files = sorted(Path(video_frames_dir).glob("*.jpg")) if video_frames_dir else []
    start_frame = params.get("start_frame", 0)
    end_frame = params.get("end_frame")

    if start_frame > 0:
        frame_files = frame_files[start_frame - 1:]
    if end_frame:
        frame_files = frame_files[:end_frame - start_frame]

    total_frames = len(frame_files)
    if total_frames == 0:
        logger.error("No frames found to analyze")
        update_status(stage="failed", progress=0, error="No frames found")
        sys.exit(1)

    # Load frames_index.json for accurate video timestamps (maps frame_num -> seconds)
    frames_index = {}
    if video_frames_dir:
        frames_index_path = Path(video_frames_dir).parent / "frames_index.json"
        if frames_index_path.exists():
            try:
                frames_index = json.loads(frames_index_path.read_text())
                # Keys are strings in JSON; convert to int for lookup
                frames_index = {int(k): v for k, v in frames_index.items()}
                logger.info(f"Loaded frames_index with {len(frames_index)} entries")
            except Exception as e:
                logger.warning(f"Failed to load frames_index: {e}")

    def get_video_timestamp(frame_num):
        """Return video timestamp in seconds for the given (1-based) frame number."""
        return frames_index.get(frame_num)

    logger.info(f"Found {total_frames} frames to analyze")

    # Update frames_meta.json with the post-dedup frame count so the UI
    # shows the correct number everywhere (job cards, video list, etc.)
    if video_frames_dir:
        meta_path = Path(video_frames_dir).parent / "frames_meta.json"
        try:
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
            else:
                meta = {}
            meta["frame_count"] = total_frames
            meta_path.write_text(json.dumps(meta))
        except Exception as e:
            logger.warning(f"Failed to update frames_meta.json: {e}")

    update_status(stage="analyzing_frames", progress=5, total_frames=total_frames)

    # Stage 2: Analyze frames
    frame_analyses = []
    temperature = params.get("temperature", 0.0)
    user_prompt = params.get("user_prompt", "")

    system_prompt = (
        "You are a video analysis AI. Analyze each frame in detail. "
        "Describe what you see, including objects, people, text, actions, and context. "
        "Be thorough but concise."
    )

    if provider_type == "ollama":
        from providers.ollama import OllamaProvider

        provider = OllamaProvider(provider_name, provider_config.get("url", "http://host.docker.internal:11434"))
        provider.check_health()

        if provider.status != "online":
            logger.error(f"Ollama provider {provider_name} is not online")
            update_status(stage="failed", progress=0, error=f"Provider {provider_name} not available")
            sys.exit(1)

        for i, frame_path in enumerate(frame_files):
            frame_num = i + 1
            actual_frame_num = start_frame + frame_num if start_frame > 0 else frame_num
            video_ts = get_video_timestamp(actual_frame_num)
            try:
                response = provider.analyze_frame(str(frame_path), model, system_prompt, user_prompt, temperature)
                frame_data = {
                    "frame": frame_num,
                    "response": response,
                    "timestamp": time.time(),
                    "video_ts": video_ts,
                }
                frame_analyses.append(frame_data)
                append_frame(frame_data)
                update_status(
                    stage="analyzing_frames",
                    progress=int((i + 1) / total_frames * 80) + 5,
                    current_frame=frame_num,
                    total_frames=total_frames,
                )
                logger.info(f"Frame {frame_num}/{total_frames} analyzed")
            except Exception as e:
                logger.error(f"Error analyzing frame {frame_num}: {e}")
                frame_data = {"frame": frame_num, "response": f"Error: {e}", "timestamp": time.time(), "video_ts": video_ts}
                frame_analyses.append(frame_data)
                append_frame(frame_data)

    elif provider_type == "openrouter":
        from providers.openrouter import OpenRouterProvider

        api_key = provider_config.get("api_key", "")
        provider = OpenRouterProvider(provider_name, api_key)

        for i, frame_path in enumerate(frame_files):
            frame_num = i + 1
            actual_frame_num = start_frame + frame_num if start_frame > 0 else frame_num
            video_ts = get_video_timestamp(actual_frame_num)
            try:
                response = provider.analyze_frame(str(frame_path), model, system_prompt, user_prompt, temperature)
                frame_data = {
                    "frame": frame_num,
                    "response": response,
                    "timestamp": time.time(),
                    "video_ts": video_ts,
                }
                frame_analyses.append(frame_data)
                append_frame(frame_data)
                update_status(
                    stage="analyzing_frames",
                    progress=int((i + 1) / total_frames * 80) + 5,
                    current_frame=frame_num,
                    total_frames=total_frames,
                )
                logger.info(f"Frame {frame_num}/{total_frames} analyzed")
            except Exception as e:
                logger.error(f"Error analyzing frame {frame_num}: {e}")
                frame_data = {"frame": frame_num, "response": f"Error: {e}", "timestamp": time.time(), "video_ts": video_ts}
                frame_analyses.append(frame_data)
                append_frame(frame_data)

    # Stage 3: Load transcript
    update_status(stage="loading_transcript", progress=85)
    transcript_data = {}
    
    try:
        # Use shared transcript loading utility for consistent path resolution
        from src.utils import load_transcript
        transcript_data = load_transcript(video_path, video_frames_dir)
        
        if transcript_data:
            logger.info(f"Loaded transcript: {len(transcript_data.get('segments', []))} segments")
        else:
            logger.info("No transcript found")
    except ImportError as e:
        logger.warning(f"Failed to import transcript utilities: {e}")
        # Fallback to original logic for backward compatibility
        transcript_path = Path(video_path).parent / Path(video_path).stem / "transcript.json"
        if transcript_path.exists():
            try:
                transcript_data = json.loads(transcript_path.read_text())
                logger.info(f"Loaded transcript: {len(transcript_data.get('segments', []))} segments")
            except Exception as e2:
                logger.warning(f"Failed to load transcript: {e2}")

    transcript_text = ""
    if isinstance(transcript_data, dict):
        transcript_text = transcript_data.get("text") or ""

    update_status(
        stage="reconstructing",
        progress=90,
        transcript=transcript_text,
    )

    # Stage 4: Generate video description
    video_description = ""
    try:
        frame_texts = [f"Frame {fa['frame']}: {fa['response']}" for fa in frame_analyses if fa.get("response")]
        combined = "\n".join(frame_texts)

        reconstruction_prompt = (
            "Based on the following sequential frame analyses and transcript, "
            "provide a comprehensive description of the video content. "
            "Include key events, narrative flow, important details, and overall summary."
        )
        if transcript_data.get("text"):
            reconstruction_prompt += f"\n\nTranscript:\n{transcript_data['text']}"

        reconstruction_prompt += f"\n\nFrame Analyses:\n{combined}"

        if provider_type == "ollama":
            video_description = provider.analyze_frame("", model, system_prompt, reconstruction_prompt, temperature)
        elif provider_type == "openrouter":
            video_description = provider.analyze_frame("", model, system_prompt, reconstruction_prompt, temperature)

        logger.info("Video description generated")
    except Exception as e:
        logger.error(f"Failed to generate video description: {e}")
        video_description = f"Error generating description: {e}"

    update_status(stage="complete", progress=100, video_description=video_description)

    # Save results
    results = {
        "frame_analyses": frame_analyses,
        "transcript": transcript_data,
        "video_description": video_description,
        "metadata": {
            "model": model,
            "provider": provider_type,
            "total_frames": total_frames,
            "temperature": temperature,
        },
    }

    results_file = output_dir / "results.json"
    results_file.write_text(json.dumps(results, indent=2))
    logger.info(f"Results saved to {results_file}")

    # Auto-LLM analysis
    try:
        auto_llm_model = config.get("auto_llm_model")
        auto_llm_prompt = config.get("auto_llm_prompt")
        if auto_llm_model and auto_llm_prompt:
            logger.info(f"Auto-LLM: submitting to queue with model={auto_llm_model}")
            from chat_queue import chat_queue_manager

            chat_queue_manager.submit_job(
                provider_type=provider_type,
                model_id=auto_llm_model,
                prompt=auto_llm_prompt,
                content=json.dumps(results, indent=2),
                api_key=provider_config.get("api_key", ""),
                ollama_url=provider_config.get("url", "http://host.docker.internal:11434"),
            )
            logger.info("Auto-LLM job submitted")
    except Exception as e:
        logger.warning(f"Auto-LLM submission failed (non-fatal): {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 worker.py <job_dir>")
        sys.exit(1)

    job_dir = Path(sys.argv[1])
    run_analysis(job_dir)
