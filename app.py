#!/usr/bin/env python3
"""
Main Flask application for Video Analyzer Web GUI
"""

import os
import re
import json
import uuid
import shutil
import signal
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

import requests
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging

from src.utils.file import (
    allowed_file,
    secure_filename as secure_filename_util,
    validate_upload_size,
)
from src.utils.transcode import probe_video, get_video_duration, probe_all_videos
from vram_manager import VRAMManager, vram_manager, JobStatus
from discovery import discovery
from monitor import monitor
from providers.ollama import OllamaProvider
from providers.openrouter import OpenRouterProvider
from thumbnail import get_thumbnail_path, ensure_thumbnail
from gpu_transcode import build_transcode_command, get_transcode_progress_parser
from chat_queue import chat_queue_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1024 * 1024 * 100,  # 100MB for large video uploads
)

# Provider registry
providers: Dict[str, Any] = {}


# ==================== Routes ====================


@app.route("/")
def index():
    """Main page"""
    return render_template("index.html")


@app.route("/api/videos")
def list_videos():
    """List uploaded videos with metadata"""
    videos = []
    upload_dir = Path(__file__).parent / "uploads"

    # Collect all valid video files
    video_files = [
        f
        for f in upload_dir.glob("*")
        if f.is_file() and f.suffix.lower() in [".mp4", ".avi", ".mov", ".mkv", ".webm"]
    ]

    # Batch probe all videos for efficiency
    video_paths = [str(f) for f in video_files]
    if video_paths:
        probed_videos = probe_all_videos(video_paths)
        for probed in probed_videos:
            video_file = Path(probed["path"])
            thumb_path = get_thumbnail_path(str(video_file))
            has_analysis = (Path(__file__).parent / "jobs" / video_file.stem).exists()

            videos.append(
                {
                    "name": probed["name"],
                    "path": str(video_file),
                    "size": video_file.stat().st_size if video_file.exists() else 0,
                    "size_human": probed.get(
                        "size_human",
                        format_bytes(
                            video_file.stat().st_size if video_file.exists() else 0
                        ),
                    ),
                    "created": datetime.fromtimestamp(
                        video_file.stat().st_mtime if video_file.exists() else 0
                    ).isoformat(),
                    "duration": probed.get("duration", 0),
                    "duration_formatted": probed.get("duration_formatted", "0s"),
                    "thumbnail": thumb_path if Path(thumb_path).exists() else None,
                    "has_analysis": has_analysis,
                }
            )

    # Sort by upload date
    videos.sort(key=lambda x: x["created"], reverse=True)
    return jsonify(videos)


@app.route("/api/videos/upload", methods=["POST"])
def upload_video():
    """Upload a video file"""
    if "video" not in request.files:
        return api_error("No video file", 400)

    file = request.files["video"]
    if file.filename == "":
        return api_error("No file selected", 400)

    # Validate file extension
    if not allowed_file(file.filename):
        return api_error("File type not allowed", 400)

    # Sanitize filename
    safe_filename = secure_filename_util(file.filename)

    # Check file size before saving
    file.stream.seek(0, 2)  # Seek to end
    file_size = file.stream.tell()
    file.stream.seek(0)  # Rewind

    is_valid, msg = validate_upload_size(file_size)
    if not is_valid:
        return api_error(msg, 413)

    # Save file
    filepath = Path(__file__).parent / "uploads" / safe_filename

    # Handle duplicate names
    counter = 1
    original_stem = filepath.stem
    while filepath.exists():
        filepath = (
            Path(__file__).parent
            / "uploads"
            / f"{original_stem}_{counter}{filepath.suffix}"
        )
        counter += 1

    file.save(filepath)

    logger.info(f"Video uploaded: {filepath}")

    # Auto-transcode to 720p@1fps then delete source
    socketio.start_background_task(_transcode_and_delete_with_cleanup, str(filepath))

    return jsonify({"success": True, "filename": filepath.name, "path": str(filepath)})


@app.route("/api/videos/<filename>", methods=["DELETE"])
def delete_video(filename):
    """Delete a video and its thumbnail"""
    safe_name = secure_filename_util(filename)
    filepath = Path(__file__).parent / "uploads" / safe_name

    if not filepath.exists():
        return api_error("Video not found", 404)

    # Delete video
    filepath.unlink()

    # Delete thumbnail
    thumb = Path(__file__).parent / "uploads" / "thumbs" / f"{Path(safe_name).stem}.jpg"
    if thumb.exists():
        thumb.unlink()

    # Delete associated jobs
    job_dir = Path(__file__).parent / "jobs" / Path(safe_name).stem
    if job_dir.exists():
        shutil.rmtree(job_dir)

    return jsonify({"success": True})


@app.route("/api/thumbnail/<filename>")
def get_thumbnail(filename):
    """Get video thumbnail"""
    safe_name = secure_filename_util(filename)
    thumb_path = (
        Path(__file__).parent / "uploads" / "thumbs" / f"{Path(safe_name).stem}.jpg"
    )

    if thumb_path.exists():
        return send_file(thumb_path, mimetype="image/jpeg")
    return api_error("Thumbnail not found", 404)


# ==================== Provider APIs ====================


@app.route("/api/providers")
def list_providers():
    """List configured providers"""
    result = []
    for name, provider in providers.items():
        result.append(provider.to_dict())
    return jsonify(result)


@app.route("/api/providers/discover")
def discover_ollama():
    """Trigger Ollama discovery scan"""
    found = discovery.scan()

    # Create/update provider instances
    for url in found:
        name = f"Ollama-{url.split('//')[1].replace(':', '-')}"
        if name not in providers:
            providers[name] = OllamaProvider(name, url)

    return jsonify({"discovered": len(found), "urls": found})


@app.route("/api/providers/ollama/models")
def get_ollama_models():
    """Get models from Ollama server"""
    url = request.args.get("server")
    if not url:
        return jsonify({"error": "No server URL"}), 400

    provider = OllamaProvider("temp", url)
    models = provider.get_models()
    return jsonify({"server": url, "models": models, "status": provider.status})


@app.route("/api/providers/openrouter/models")
def get_openrouter_models():
    """Get models from OpenRouter"""
    api_key = request.args.get("api_key")
    if not api_key:
        return jsonify({"error": "No API key"}), 400

    provider = OpenRouterProvider("OpenRouter", api_key)
    providers["OpenRouter"] = provider  # Save for later
    models = provider.get_models()
    return jsonify({"models": models, "status": provider.status})


@app.route("/api/providers/openrouter/cost")
def estimate_openrouter_cost():
    """Estimate cost for analysis"""
    api_key = request.args.get("api_key")
    model_id = request.args.get("model")
    frame_count = int(request.args.get("frames", 50))

    if not api_key or not model_id:
        return jsonify({"error": "Missing parameters"}), 400

    provider = providers.get("OpenRouter") or OpenRouterProvider("OpenRouter", api_key)
    cost = provider.estimate_cost(model_id, frame_count)
    return jsonify(cost)


# ==================== Job APIs ====================


@app.route("/api/jobs")
def list_jobs():
    """List all jobs"""
    jobs = vram_manager.get_all_jobs()
    return jsonify([job.to_dict() for job in jobs])


@app.route("/api/jobs/running")
def running_jobs():
    """List running jobs"""
    jobs = vram_manager.get_running_jobs()
    return jsonify([job.to_dict() for job in jobs])


@app.route("/api/jobs/queued")
def queued_jobs():
    """List queued jobs"""
    jobs = vram_manager.get_queued_jobs()
    return jsonify([job.to_dict() for job in jobs])


@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    """Get job details"""
    job = vram_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    # Load additional status
    job_dir = Path("jobs") / job_id
    status_file = job_dir / "status.json"
    status_data = {}
    if status_file.exists():
        status_data = json.loads(status_file.read_text())

    result = job.to_dict()
    result.update(status_data)
    return jsonify(result)


@app.route("/api/jobs/<job_id>/frames")
def get_job_frames(job_id):
    """Get frame analyses for a job with pagination"""
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    job_dir = Path(__file__).parent / "jobs" / job_id
    frames_file = job_dir / "frames.jsonl"

    if not frames_file.exists():
        return jsonify([])

    frames = []
    with open(frames_file) as f:
        for i, line in enumerate(f):
            if i < offset:
                continue
            if len(frames) >= limit:
                break
            try:
                frames.append(json.loads(line.strip()))
            except:
                pass

    return jsonify(frames)


@app.route("/api/jobs/<job_id>/results")
def get_job_results(job_id):
    """Get final results for a job"""
    results_file = Path("jobs") / job_id / "output" / "results.json"
    if not results_file.exists():
        return jsonify({"error": "Results not found"}), 404

    return jsonify(json.loads(results_file.read_text()))


@app.route("/api/jobs/<job_id>", methods=["DELETE"])
def cancel_job(job_id):
    """Cancel a job"""
    success = vram_manager.cancel_job(job_id)

    # Kill entire process group to catch all children (ffmpeg, whisper, etc.)
    job_dir = Path(__file__).parent / "jobs" / job_id
    pgid_file = job_dir / "pgid"
    pid_file = job_dir / "pid"
    killed = False

    if pgid_file.exists():
        try:
            pgid = int(pgid_file.read_text().strip())
            os.killpg(pgid, signal.SIGTERM)
            killed = True
        except (ProcessLookupError, PermissionError) as e:
            logger.debug(f"Could not kill PGID {pgid}: {e}")
        except Exception as e:
            logger.warning(f"Failed to kill PGID for job {job_id}: {e}")

    if not killed and pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    if success:
        return jsonify({"success": True, "message": "Job cancellation initiated"})
    else:
        return api_error("Cannot cancel job", 400)


@app.route("/api/jobs/<job_id>/priority", methods=["POST"])
def update_priority(job_id):
    """Update job priority"""
    data = request.json
    new_priority = data.get("priority", 0)
    success = vram_manager.update_priority(job_id, new_priority)
    return jsonify({"success": success})


@app.route("/api/vram")
def get_vram_status():
    """Get current VRAM status for all GPUs"""
    return jsonify(vram_manager.get_status())


@app.route("/api/gpus")
def get_gpu_list():
    """Get list of all GPUs with details"""
    gpus = vram_manager._get_gpu_status()
    return jsonify(
        [
            {
                "index": gpu.index,
                "name": gpu.name,
                "total_gb": round(gpu.total_vram / (1024**3), 2),
                "used_gb": round(gpu.used_vram / (1024**3), 2),
                "free_gb": round(gpu.free_vram / (1024**3), 2),
            }
            for gpu in gpus
        ]
    )


@app.route("/api/videos/transcode", methods=["POST"])
def transcode_video():
    """Manually trigger transcode for an already-uploaded video"""
    data = request.json
    video_path = data.get("video_path")

    if not video_path or not Path(video_path).exists():
        return jsonify({"error": "Video not found"}), 404

    socketio.start_background_task(_transcode_and_delete_with_cleanup, video_path)
    return jsonify({"success": True, "message": "Transcoding started"})


# ==================== LLM Chat API ====================


@app.route("/api/llm/chat", methods=["POST"])
def llm_chat():
    """Submit a chat request to the queue and return job_id"""
    data = request.json
    provider_type = data.get("provider_type")  # "ollama" or "openrouter"
    model_id = data.get("model")
    prompt = data.get("prompt", "")
    content = data.get("content", "")  # the document text being analyzed
    api_key = data.get("api_key", "")
    ollama_url = data.get("ollama_url", "http://host.docker.internal:11434")

    if not model_id:
        return api_error("Model is required", 400)
    if not prompt and not content:
        return api_error("Prompt or content is required", 400)

    try:
        # Submit to chat queue
        job_id = chat_queue_manager.submit_job(
            provider_type=provider_type or "ollama",
            model_id=model_id,
            prompt=prompt,
            content=content,
            api_key=api_key,
            ollama_url=ollama_url,
        )

        return jsonify({"job_id": job_id, "message": "Chat job submitted to queue"})

    except ValueError as e:
        logger.error(f"Invalid chat request: {e}")
        return api_error(str(e), 400)
    except Exception as e:
        logger.error(f"Error submitting chat job: {e}")
        return api_error(f"Internal error: {str(e)}", 500)


@app.route("/api/llm/chat/<job_id>", methods=["GET"])
def llm_chat_status(job_id: str):
    """Get status of a chat job"""
    status = chat_queue_manager.get_job_status(job_id)
    if not status:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(status)


@app.route("/api/llm/chat/<job_id>", methods=["DELETE"])
def cancel_llm_chat(job_id: str):
    """Cancel a chat job"""
    success = chat_queue_manager.cancel_job(job_id)
    if not success:
        return jsonify({"error": "Cannot cancel job"}), 400

    return jsonify({"success": True, "message": "Job cancelled"})


@app.route("/api/llm/queue/stats", methods=["GET"])
def llm_queue_stats():
    """Get chat queue statistics"""
    stats = chat_queue_manager.get_queue_stats()
    return jsonify(stats)


# ==================== Stored Results API ====================


@app.route("/api/results")
def list_all_results():
    """List all completed jobs with their stored results"""
    results_list = []
    jobs_dir = Path("jobs")
    if not jobs_dir.exists():
        return jsonify([])

    for job_dir in sorted(
        jobs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        if not job_dir.is_dir():
            continue
        results_file = job_dir / "output" / "results.json"
        input_file = job_dir / "input.json"
        status_file = job_dir / "status.json"
        if not results_file.exists():
            continue
        try:
            inp = json.loads(input_file.read_text()) if input_file.exists() else {}
            status = json.loads(status_file.read_text()) if status_file.exists() else {}
            res = json.loads(results_file.read_text())
            descObj = res.get("video_description", {})
            desc_preview = ""
            if isinstance(descObj, str):
                desc_preview = descObj[:200]
            elif isinstance(descObj, dict):
                desc_preview = (descObj.get("response") or descObj.get("text") or "")[
                    :200
                ]

            results_list.append(
                {
                    "job_id": job_dir.name,
                    "video_path": inp.get("video_path", ""),
                    "model": inp.get("model", ""),
                    "provider": inp.get("provider_type", ""),
                    "created_at": inp.get("created_at", job_dir.stat().st_mtime),
                    "mtime": job_dir.stat().st_mtime,
                    "has_transcript": bool(
                        res.get("transcript") and res["transcript"].get("text")
                    ),
                    "frame_count": len(res.get("frame_analyses", [])),
                    "desc_preview": desc_preview,
                }
            )
        except Exception:
            continue

    return jsonify(results_list)


@app.route("/api/providers/openrouter/balance")
def get_openrouter_balance():
    """Get OpenRouter API key balance"""
    api_key = request.args.get("api_key")
    if not api_key:
        return api_error("No API key", 400)

    try:
        response = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            return jsonify(
                {
                    "balance": data.get("data", {}).get("balance", 0),
                    "usage": data.get("data", {}).get("usage", 0),
                    "limit": data.get("data", {}).get("limit", None),
                }
            )
        elif response.status_code == 401:
            return api_error("Invalid API key", 401)
        else:
            return api_error(
                f"Failed to fetch balance: {response.status_code}", response.status_code
            )

    except requests.RequestException as e:
        return api_error(f"Network error: {str(e)}", 503)
    except Exception as e:
        logger.error(f"Unexpected error getting balance: {e}")
        return api_error("Internal server error", 500)


# ==================== SocketIO Events ====================


@socketio.on("connect")
def handle_connect():
    """Client connected"""
    logger.info(f"Client connected: {request.sid}")
    emit("connected", {"message": "Connected to Video Analyzer Web"})

    # Replay last monitor data to new client immediately
    latest = monitor.get_latest()
    if latest["nvidia_smi"]:
        emit(
            "system_status",
            {
                "type": "nvidia_smi",
                "data": {
                    "text": latest["nvidia_smi"],
                    "gpus": latest.get("nvidia_gpus", []),
                },
                "timestamp": latest["timestamp"],
            },
        )
    if latest["ollama_ps"]:
        emit(
            "system_status",
            {
                "type": "ollama_ps",
                "data": {"text": latest["ollama_ps"]},
                "timestamp": latest["timestamp"],
            },
        )


@socketio.on("disconnect")
def handle_disconnect():
    """Client disconnected"""
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on("subscribe_job")
def handle_subscribe_job(data):
    """Subscribe to job updates and send current state"""
    job_id = data.get("job_id")
    if not job_id:
        return

    join_room(f"job_{job_id}")
    logger.info(f"Client {request.sid} subscribed to job {job_id}")

    job_dir = Path("jobs") / job_id
    status_file = job_dir / "status.json"
    frames_file = job_dir / "frames.jsonl"
    results_file = job_dir / "output" / "results.json"

    # Send current status
    status = {}
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text())
            emit("job_status", {"job_id": job_id, **status})
        except Exception as e:
            logger.warning(f"Failed to send status for job {job_id}: {e}")

    # Send all frame history
    if frames_file.exists():
        try:
            lines = [l for l in frames_file.read_text().strip().split("\n") if l]
            for line in lines:
                try:
                    frame_data = json.loads(line)
                    emit("frame_analysis", {"job_id": job_id, **frame_data})
                except:
                    pass
        except Exception as e:
            logger.warning(f"Failed to send frame history for job {job_id}: {e}")

    # If job is already complete, replay final results immediately
    if status.get("stage") == "complete" and results_file.exists():
        try:
            results = json.loads(results_file.read_text())

            transcript_text = results.get("transcript", {})
            if isinstance(transcript_text, dict):
                transcript_text = transcript_text.get("text")
            if transcript_text:
                emit(
                    "job_transcript", {"job_id": job_id, "transcript": transcript_text}
                )

            vd = results.get("video_description")
            if vd:
                description = (
                    vd.get("response") or vd if isinstance(vd, str) else str(vd)
                )
                emit("job_description", {"job_id": job_id, "description": description})

            emit("job_complete", {"job_id": job_id, "success": True, **status})
        except Exception as e:
            logger.warning(f"Failed to replay final results for job {job_id}: {e}")


@socketio.on("unsubscribe_job")
def handle_unsubscribe_job(data):
    """Unsubscribe from job updates"""
    job_id = data.get("job_id")
    if job_id:
        leave_room(f"job_{job_id}")


@socketio.on("start_analysis")
def handle_start_analysis(data):
    """Start a new analysis job"""
    job_id = str(uuid.uuid4())[:8]

    video_path = data.get("video_path")
    provider_type = data.get("provider_type")
    provider_name = data.get("provider_name")
    model_id = data.get("model")
    priority = data.get("priority", 0)

    # Get provider config
    provider_config = data.get("provider_config", {})

    # Estimate VRAM
    vram_required = 0
    if provider_type == "ollama":
        # Get VRAM from provider model info
        provider = providers.get(provider_name)
        if provider:
            vram_required = provider.estimate_vram(model_id) or 0

    # Create job directory
    job_dir = Path("jobs") / job_id
    job_dir.mkdir(parents=True)

    # Write input config
    config = {
        "job_id": job_id,
        "video_path": video_path,
        "provider_type": provider_type,
        "provider_name": provider_name,
        "provider_config": provider_config,
        "model": model_id,
        "params": {
            "temperature": data.get("temperature", 0.0),
            "duration": data.get("duration"),
            "max_frames": data.get("max_frames", 2147483647),
            "frames_per_minute": data.get("frames_per_minute", 60),
            "whisper_model": data.get("whisper_model", "large"),
            "language": data.get("language", "en"),
            "device": data.get("device", "gpu"),
            "keep_frames": data.get("keep_frames", False),
            "user_prompt": data.get("user_prompt", ""),
        },
    }

    (job_dir / "input.json").write_text(json.dumps(config))

    # Submit to VRAM manager.
    # on_vram_event("started", ...) will spawn the worker — do NOT also spawn here.
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


_spawned_jobs: set = set()  # Guard against double-spawn


def spawn_worker(job_id: str, job_dir: Path, gpu_assigned: Optional[int] = None):
    """Spawn worker subprocess for a job"""
    if job_id in _spawned_jobs:
        logger.warning(
            f"spawn_worker called twice for job {job_id} — ignoring duplicate"
        )
        return
    _spawned_jobs.add(job_id)

    log_file = open(job_dir / "worker.log", "w")

    # Save GPU assignment to file for worker reference
    if gpu_assigned is not None:
        (job_dir / "gpu_assigned.txt").write_text(str(gpu_assigned))

    # Set environment variables based on GPU assignment
    env = os.environ.copy()
    if gpu_assigned is not None:
        # Set CUDA_VISIBLE_DEVICES to restrict to assigned GPU
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_assigned)
        logger.info(
            f"Job {job_id} assigned to GPU {gpu_assigned}, setting CUDA_VISIBLE_DEVICES={gpu_assigned}"
        )

    proc = subprocess.Popen(
        ["python3", "worker.py", str(job_dir)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # New process group so we can kill all children
        env=env,
    )

    # Save PID and process group ID
    pgid = os.getpgid(proc.pid)
    (job_dir / "pid").write_text(str(proc.pid))
    (job_dir / "pgid").write_text(str(pgid))

    logger.info(f"Spawned worker for job {job_id} (PID: {proc.pid}, PGID: {pgid})")

    # Start monitoring thread
    socketio.start_background_task(monitor_job, job_id, job_dir, proc)


def monitor_job(job_id: str, job_dir: Path, proc: subprocess.Popen):
    """Monitor job status and emit updates"""
    status_file = job_dir / "status.json"
    last_status = {}
    last_frame_count = 0

    while proc.poll() is None:
        try:
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                except json.JSONDecodeError:
                    socketio.sleep(1)
                    continue

                # Only emit if changed
                if status != last_status:
                    last_status = status.copy()
                    socketio.emit(
                        "job_status", {"job_id": job_id, **status}, room=f"job_{job_id}"
                    )

                    # Emit transcript and description when available
                    if status.get("stage") in (
                        "reconstructing",
                        "complete",
                    ) and status.get("transcript"):
                        socketio.emit(
                            "job_transcript",
                            {
                                "job_id": job_id,
                                "transcript": status["transcript"],
                            },
                            room=f"job_{job_id}",
                        )

                    if status.get("video_description"):
                        socketio.emit(
                            "job_description",
                            {
                                "job_id": job_id,
                                "description": status["video_description"],
                            },
                            room=f"job_{job_id}",
                        )

                # Emit new frames since last check
                frames_file = job_dir / "frames.jsonl"
                if frames_file.exists():
                    try:
                        lines = [
                            l for l in frames_file.read_text().strip().split("\n") if l
                        ]
                        new_frames = lines[last_frame_count:]
                        if new_frames:
                            logger.debug(
                                f"Emitting {len(new_frames)} new frames for job {job_id}"
                            )
                        for line in new_frames:
                            try:
                                frame_data = json.loads(line)
                                socketio.emit(
                                    "frame_analysis",
                                    {"job_id": job_id, **frame_data},
                                    room=f"job_{job_id}",
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to emit frame for job {job_id}: {e}"
                                )
                        last_frame_count = len(lines)
                    except Exception as e:
                        logger.error(f"Error reading frames file for job {job_id}: {e}")

        except Exception as e:
            logger.error(f"Error monitoring job {job_id}: {e}")

        socketio.sleep(1)

    # Reap any zombie children in the process group
    pgid_file = job_dir / "pgid"
    if pgid_file.exists():
        try:
            pgid = int(pgid_file.read_text().strip())
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass  # Already dead, fine
        except Exception as e:
            logger.debug(f"PGID cleanup for job {job_id}: {e}")

    # Job completed — guard against two monitor threads both calling complete_job
    success = proc.returncode == 0
    job_obj = vram_manager.get_job(job_id)
    if job_obj and job_obj.status in (
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    ):
        logger.debug(
            f"monitor_job: job {job_id} already finalized, skipping complete_job"
        )
        return
    vram_manager.complete_job(job_id, success)
    _spawned_jobs.discard(job_id)

    # Emit final results
    results_file = job_dir / "output" / "results.json"
    if results_file.exists():
        try:
            results = json.loads(results_file.read_text())
            transcript_text = None
            if results.get("transcript") and results["transcript"].get("text"):
                transcript_text = results["transcript"]["text"]
            description = None
            if results.get("video_description"):
                vd = results["video_description"]
                description = (
                    vd.get("response") or vd if isinstance(vd, str) else str(vd)
                )

            if transcript_text:
                socketio.emit(
                    "job_transcript",
                    {
                        "job_id": job_id,
                        "transcript": transcript_text,
                    },
                    room=f"job_{job_id}",
                )
            if description:
                socketio.emit(
                    "job_description",
                    {
                        "job_id": job_id,
                        "description": description,
                    },
                    room=f"job_{job_id}",
                )
        except Exception as e:
            logger.error(f"Failed to emit final results for {job_id}: {e}")

    # Final status
    if status_file.exists():
        try:
            final_status = json.loads(status_file.read_text())
        except json.JSONDecodeError:
            final_status = {}
        socketio.emit(
            "job_complete",
            {"job_id": job_id, "success": success, **final_status},
            room=f"job_{job_id}",
        )


# ==================== VRAM Manager Callback ====================


def on_vram_event(event: str, job):
    """Handle VRAM manager events"""
    if event == "started":
        job_dir = Path("jobs") / job.job_id
        spawn_worker(job.job_id, job_dir, job.gpu_assigned)

    # Broadcast to all clients
    socketio.emit("vram_event", {"event": event, "job": job.to_dict()})


vram_manager.register_callback(on_vram_event)


# ==================== System Monitor Callback ====================


def on_monitor_update(data: dict):
    """Handle system monitor updates"""
    socketio.emit("system_status", data)


monitor.register_callback(on_monitor_update)


# ==================== Transcode Helper ====================


def _transcode_and_delete_with_cleanup(src_path: str):
    """
    Background task: transcode src_path to 720p@1fps, emit progress via socket,
    delete the source file on success, then refresh the video list.
    Includes proper cleanup in finally block.
    """
    input_path = Path(src_path)
    output_name = f"{input_path.stem}_720p1fps.mp4"
    output_path = input_path.parent / output_name
    src_name = input_path.name

    # Create log file for cleanup
    log_file = None

    try:

        def _emit(stage, progress, error=None):
            socketio.emit(
                "transcode_progress",
                {
                    "source": src_name,
                    "output": output_name,
                    "stage": stage,
                    "progress": progress,
                    "error": error,
                },
            )

        # Get video duration for progress calculation
        duration_s = 0.0
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(input_path),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if probe.returncode == 0:
                duration_s = float(probe.stdout.strip())
        except Exception:
            pass

        _emit("starting", 0)
        logger.info(
            f"Transcoding {src_name} -> {output_name}  (duration {duration_s:.1f}s)"
        )

        try:
            # Build transcoding command
            cmd = build_transcode_command(
                input_path=str(input_path),
                output_path=str(output_path),
                width=1280,
                height=720,
                fps=1,
                gpu_index=0,  # Use first GPU for transcoding
            )

            logger.info(f"Transcode command: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # Stream reading with timeout
            output_lines = []
            error_lines = []

            def read_output(stream, target_list):
                for line in stream:
                    target_list.append(line)

            stdout_thread = threading.Thread(
                target=read_output, args=(proc.stdout, output_lines)
            )
            stderr_thread = threading.Thread(
                target=read_output, args=(proc.stderr, error_lines)
            )

            stdout_thread.start()
            stderr_thread.start()

            # Parse ffmpeg progress lines
            current_time_s = 0.0
            parse_progress = get_transcode_progress_parser("standard")

            proc.wait(timeout=3600)

            # Wait for threads
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

            # Parse output for progress
            for line in output_lines:
                line = line.strip()
                progress = parse_progress(line, current_time_s, duration_s)
                if progress is not None:
                    _emit("transcoding", int(progress))
                elif line.startswith("out_time_ms="):
                    try:
                        current_time_s = int(line.split("=")[1]) / 1_000_000
                        if duration_s > 0:
                            pct = min(current_time_s / duration_s * 100, 99)
                            _emit("transcoding", int(pct))
                    except ValueError:
                        pass

            err_content = (
                "".join(error_lines)[-400:] if error_lines else "unknown error"
            )

            if proc.returncode == 0:
                _emit("finalizing", 99)
                ensure_thumbnail(str(output_path))
                # Delete source file
                try:
                    input_path.unlink()
                    logger.info(f"Deleted source file: {src_name}")
                except Exception as e:
                    logger.warning(f"Could not delete source {src_name}: {e}")

                logger.info(f"Transcode complete: {output_name}")
                _emit("complete", 100)
            else:
                logger.warning(f"Transcode failed for {src_name}: {err_content}")
                _emit("failed", 0, error=err_content)

        except subprocess.TimeoutExpired:
            proc.kill()
            _, _ = proc.communicate()
            _emit("failed", 0, error="Transcode timed out")

    except Exception as e:
        logger.warning(f"Transcode error for {src_name}: {e}")
        _emit("failed", 0, error=str(e))

    finally:
        # Ensure proper cleanup
        if log_file:
            log_file.close()

    socketio.emit("videos_updated", {})


# ==================== Utilities ====================


def api_error(message: str, code: int = 400):
    """Standardized error response helper"""
    return jsonify({"error": {"code": code, "message": message}}), code


def secure_filename(filename: str) -> str:
    """Secure a filename for storage"""
    filename = re.sub(r"[^\w\s.-]", "", filename).strip()
    return filename


def format_bytes(size: int) -> str:
    """Format bytes to human readable"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration to human readable"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def map_exit_code_to_status(returncode: int) -> tuple[str, str]:
    """Map process exit code to status and message"""
    if returncode == 0:
        return "completed", "Job completed successfully"
    elif returncode == 1:
        return "failed", "Job failed due to error"
    elif returncode == 130:
        return "cancelled", "Job cancelled by user"
    elif returncode == 137:
        return "failed", "Job terminated due to out of memory"
    elif returncode == 139:
        return "failed", "Job crashed (segmentation fault)"
    else:
        return "failed", f"Job failed with exit code {returncode}"


# ==================== Initialization ====================


def init_providers():
    """Initialize default providers"""
    # Use host.docker.internal so the container can reach the host's Ollama
    ollama_local = OllamaProvider("Ollama-Local", "http://host.docker.internal:11434")
    providers["Ollama-Local"] = ollama_local

    # Try to discover others
    discovered = discovery.scan()
    for url in discovered:
        if "localhost" not in url and "127.0.0.1" not in url:
            name = f"Ollama-{url.split('//')[1].split(':')[0]}"
            providers[name] = OllamaProvider(name, url)


# Set up Ollama URL provider for monitor
monitor.set_ollama_url_provider(
    lambda: next(
        (p.base_url for p in providers.values() if hasattr(p, "base_url")), None
    )
)

# Start system monitor
monitor.start()

# Initialize providers
init_providers()


if __name__ == "__main__":
    socketio.run(
        app, host="0.0.0.0", port=11000, debug=False, allow_unsafe_werkzeug=True
    )
