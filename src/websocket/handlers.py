"""
SocketIO event handlers for Video Analyzer Web
"""
import json
import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def register_socket_handlers(socketio):
    """Register all SocketIO event handlers"""

    @socketio.on("connect")
    def handle_connect(auth=None):
        from flask_socketio import emit
        from flask import request
        from monitor import monitor
        logger.info(f"Client connected: {request.sid}")
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

    @socketio.on("subscribe_job")
    def handle_subscribe_job(data):
        from flask_socketio import emit, join_room
        from flask import request
        job_id = data.get("job_id")
        if not job_id:
            return
        join_room(f"job_{job_id}")
        logger.info(f"Client {request.sid} subscribed to job {job_id}")
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
        if status.get("stage") == "complete" and results_file.exists():
            try:
                results = json.loads(results_file.read_text())
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
                "keep_frames": data.get("keep_frames", False),
                "user_prompt": data.get("user_prompt", ""),
            },
        }
        (job_dir / "input.json").write_text(json.dumps(config))

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
        emit("job_update", job.to_dict(), room=f"job_{job_id}")
