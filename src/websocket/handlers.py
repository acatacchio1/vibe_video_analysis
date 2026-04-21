"""
SocketIO event handlers for Video Analyzer Web
"""
import json
import uuid
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def get_openrouter_api_key():
    """Get OpenRouter API key from environment"""
    return os.environ.get("OPENROUTER_API_KEY", "")


def register_socket_handlers(socketio):
    """Register all SocketIO event handlers"""
    from config.constants import DEBUG

    @socketio.on("connect")
    def handle_connect(auth=None):
        from flask_socketio import emit
        from flask import request
        from monitor import monitor
        logger.info(f"Client connected: {request.sid}")
        if DEBUG:
            logger.debug(f"[SOCKET RECV] connect auth={auth}")
        emit("connected", {"message": "Connected to Video Analyzer Web"})
        latest = monitor.get_latest()
        if latest["nvidia_smi"]:
            emit("system_status", {
                "type": "nvidia_smi",
                "data": {"text": latest["nvidia_smi"], "gpus": latest.get("nvidia_gpus", [])},
                "timestamp": latest["timestamp"],
            })
        if latest["ollama_ps"]:
            emit("system_status", {
                "type": "ollama_ps",
                "data": {"text": latest["ollama_ps"]},
                "timestamp": latest["timestamp"],
            })

    @socketio.on("disconnect")
    def handle_disconnect(auth=None):
        from flask import request
        logger.info(f"Client disconnected: {request.sid}")
        if DEBUG:
            logger.debug(f"[SOCKET RECV] disconnect sid={request.sid}")

    @socketio.on("subscribe_job")
    def handle_subscribe_job(data):
        from flask_socketio import emit, join_room
        from flask import request
        job_id = data.get("job_id")
        if not job_id:
            return
        join_room(f"job_{job_id}")
        logger.info(f"Client {request.sid} subscribed to job {job_id}")
        if DEBUG:
            logger.debug(f"[SOCKET RECV] subscribe_job data={data}")
        job_dir = Path("jobs") / job_id
        status_file = job_dir / "status.json"
        frames_file = job_dir / "frames.jsonl"
        results_file = job_dir / "output" / "results.json"
        status = {}
        if status_file.exists():
            try:
                status = json.loads(status_file.read_text())
                emit("job_status", {"job_id": job_id, **status})
            except Exception as e:
                logger.warning(f"Failed to send status for job {job_id}: {e}")
        if frames_file.exists():
            try:
                lines = [l for l in frames_file.read_text().strip().split("\n") if l]
                for line in lines:
                    try:
                        frame_data = json.loads(line)
                        emit("frame_analysis", {"job_id": job_id, **frame_data})
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Failed to send frame history for job {job_id}: {e}")
        # Always try to replay transcript from disk — it exists as soon as the video
        # was uploaded, long before the worker reaches the reconstructing stage.
        transcript_replayed = False
        input_file = job_dir / "input.json"
        if input_file.exists():
            try:
                job_config = json.loads(input_file.read_text())
                video_path = job_config.get("video_path", "")
                if video_path:
                    transcript_path = Path(video_path).parent / Path(video_path).stem / "transcript.json"
                    if transcript_path.exists():
                        transcript_data = json.loads(transcript_path.read_text())
                        transcript_text = transcript_data.get("text") or ""
                        if transcript_text:
                            emit("job_transcript", {"job_id": job_id, "transcript": transcript_text})
                            transcript_replayed = True
            except Exception as e:
                logger.warning(f"Failed to replay transcript from disk for job {job_id}: {e}")

        if status.get("stage") == "complete" and results_file.exists():
            try:
                results = json.loads(results_file.read_text())
                if not transcript_replayed:
                    transcript_text = results.get("transcript", {})
                    if isinstance(transcript_text, dict):
                        transcript_text = transcript_text.get("text")
                    if transcript_text:
                        emit("job_transcript", {"job_id": job_id, "transcript": transcript_text})
                vd = results.get("video_description")
                if vd:
                    description = vd.get("response") or vd if isinstance(vd, str) else str(vd)
                    emit("job_description", {"job_id": job_id, "description": description})
                emit("job_complete", {"job_id": job_id, "success": True, **status})
            except Exception as e:
                logger.warning(f"Failed to replay final results for job {job_id}: {e}")

    @socketio.on("unsubscribe_job")
    def handle_unsubscribe_job(data):
        from flask_socketio import leave_room
        job_id = data.get("job_id")
        if job_id:
            leave_room(f"job_{job_id}")
            if DEBUG:
                logger.debug(f"[SOCKET RECV] unsubscribe_job job_id={job_id}")

    @socketio.on("start_analysis")
    def handle_start_analysis(data):
        from flask_socketio import emit
        from flask import request
        from vram_manager import vram_manager

        job_id = str(uuid.uuid4())[:8]
        video_path = data.get("video_path")
        provider_type = data.get("provider_type")
        provider_name = data.get("provider_name")
        model_id = data.get("model")
        priority = data.get("priority", 0)
        provider_config = data.get("provider_config", {})

        # For OpenRouter, inject API key from environment if not provided
        if provider_type == "openrouter":
            if not provider_config or not provider_config.get("api_key"):
                env_key = get_openrouter_api_key()
                if env_key:
                    provider_config = provider_config or {}
                    provider_config["api_key"] = env_key
                    logger.info(f"Using OpenRouter API key from environment for job {job_id}")
                else:
                    emit("error", {"message": "OpenRouter API key not configured"})
                    return

        if DEBUG:
            logger.debug(f"[SOCKET RECV] start_analysis video={video_path} provider={provider_name}/{provider_type} model={model_id} params_keys={list(data.keys())}")

        vram_required = 0
        if provider_type == "ollama":
            from app import providers
            provider = providers.get(provider_name)
            if provider:
                vram_required = provider.estimate_vram(model_id) or 0

        job_dir = Path("jobs") / job_id
        job_dir.mkdir(parents=True)

        video_stem = Path(video_path).stem if video_path else ""
        base_dir = Path(__file__).parent.parent.parent
        video_frames_dir = str(base_dir / "uploads" / video_stem / "frames") if video_stem else ""

        config = {
            "job_id": job_id,
            "video_path": video_path,
            "provider_type": provider_type,
            "provider_name": provider_name,
            "provider_config": provider_config,
            "model": model_id,
            "video_frames_dir": video_frames_dir,
            "params": {
                "temperature": data.get("temperature", 0.0),
                "start_frame": data.get("start_frame", 0),
                "end_frame": data.get("end_frame"),
                "fps": data.get("fps", 1),
                "frames_per_minute": data.get("frames_per_minute", 60),
                "similarity_threshold": data.get("similarity_threshold", 10),
                "whisper_model": data.get("whisper_model", "large"),
                "language": data.get("language", "en"),
                "device": data.get("device", "gpu"),
                "user_prompt": data.get("user_prompt", ""),
            },
        }
        (job_dir / "input.json").write_text(json.dumps(config))

        if DEBUG:
            logger.debug(f"[JOB CREATED] job_id={job_id} video_frames_dir={video_frames_dir} start_frame={config['params']['start_frame']} end_frame={config['params']['end_frame']}")

        # Emit transcript immediately if it already exists on disk — no need to wait
        # for the worker to reach the reconstructing stage.
        if video_path:
            transcript_path = Path(video_path).parent / Path(video_path).stem / "transcript.json"
            try:
                if transcript_path.exists():
                    transcript_data = json.loads(transcript_path.read_text())
                    transcript_text = transcript_data.get("text") or ""
                    if transcript_text:
                        emit("job_transcript", {"job_id": job_id, "transcript": transcript_text})
                        logger.debug(f"[JOB CREATED] emitted pre-existing transcript for job {job_id}")
            except Exception as e:
                logger.warning(f"Could not pre-load transcript for job {job_id}: {e}")

        job = vram_manager.submit_job(
            job_id=job_id,
            provider_type=provider_type,
            provider_name=provider_name,
            model_id=model_id,
            vram_required=vram_required,
            video_path=video_path,
            params=config["params"],
            priority=priority,
        )
        emit("job_created", {"job_id": job_id, "status": job.status.value})
