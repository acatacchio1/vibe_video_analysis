#!/usr/bin/env python3
"""
Main Flask application for Video Analyzer Web GUI
"""

import os
import json
import uuid
import signal
import threading
import subprocess
from pathlib import Path
from typing import Dict, Optional, Any

from flask import Flask
from flask_socketio import SocketIO
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from vram_manager import vram_manager, JobStatus
from discovery import discovery
from monitor import monitor
from providers.ollama import OllamaProvider
from providers.openrouter import OpenRouterProvider
from thumbnail import ensure_thumbnail
from gpu_transcode import build_transcode_command, get_transcode_progress_parser
from config.constants import DEBUG, LOG_LEVEL, LOG_FORMAT

# Setup logging
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# Optional parallel deduplication utilities
try:
    from src.utils.parallel_file_ops import delete_frames_parallel
    from src.utils.dedup_scheduler import get_dedup_strategy, log_dedup_start, log_dedup_completion
    PARALLEL_DEDUP_AVAILABLE = True
    logger.info("Parallel deduplication utilities loaded successfully")
except ImportError as e:
    PARALLEL_DEDUP_AVAILABLE = False
    logger.warning(f"Parallel deduplication utilities not available: {e}")
    logger.warning("Falling back to sequential deduplication only")
if DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)
    for name in ("src.websocket.handlers", "src.api.videos", "src.api.providers",
                  "src.api.jobs", "src.api.transcode", "worker"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    logger.info("DEBUG mode enabled - all loggers set to DEBUG")

# Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1024 * 1024 * 100,
)

# Debug: wrap socketio.emit to log every emission
_original_emit = socketio.emit
def _debug_emit(event, *args, **kwargs):
    if DEBUG and event != 'log_message':
        room = kwargs.get("room", "broadcast")
        logger.debug(f"[SOCKET EMIT] event={event} room={room} args_preview={str(args)[:200]}")
    return _original_emit(event, *args, **kwargs)
socketio.emit = _debug_emit

# Socket log handler - emits log records to connected clients
# Uses a thread-safe queue + background emitter to work with eventlet
import queue as _queue
import time as _time
_log_queue = _queue.Queue(maxsize=500)

class SocketLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            _log_queue.put_nowait({
                'level': record.levelname,
                'message': msg,
                'timestamp': _time.strftime('%Y-%m-%d %H:%M:%S', _time.localtime(record.created)),
            })
        except _queue.Full:
            pass  # Drop oldest if queue full

def _log_emitter():
    """Background thread that drains the log queue and emits via SocketIO"""
    while True:
        try:
            data = _log_queue.get(timeout=1)
            socketio.emit('log_message', data)
        except _queue.Empty:
            continue
        except Exception:
            pass

socket_log_handler = SocketLogHandler()
socket_log_handler.setLevel(logging.INFO)  # Only send INFO+ to browser, DEBUG stays in terminal
socket_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(socket_log_handler)

# Start the log emitter background thread
_log_thread = threading.Thread(target=_log_emitter, daemon=True, name='log-emitter')
_log_thread.start()

# Provider registry
providers: Dict[str, Any] = {}

# Register API blueprints
from src.api.videos import videos_bp
from src.api.providers import providers_bp
from src.api.jobs import jobs_bp
from src.api.llm import llm_bp
from src.api.results import results_bp
from src.api.system import system_bp
from src.api.transcode import transcode_bp
from src.api.knowledge import knowledge_bp

app.register_blueprint(videos_bp)
app.register_blueprint(providers_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(llm_bp)
app.register_blueprint(results_bp)
app.register_blueprint(system_bp)
app.register_blueprint(transcode_bp)
app.register_blueprint(knowledge_bp)

# Register SocketIO handlers
from src.websocket.handlers import register_socket_handlers
register_socket_handlers(socketio)


# ==================== Utilities ====================


def api_error(message: str, code: int = 400):
    """Standardized error response helper"""
    from flask import jsonify
    return jsonify({"error": {"code": code, "message": message}}), code


def format_bytes(size: int) -> str:
    """Format bytes to human readable"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# ==================== Worker Management ====================

_spawned_jobs: set = set()


def spawn_worker(job_id: str, job_dir: Path, gpu_assigned: Optional[int] = None):
    """Spawn worker subprocess for a job"""
    # Guard against double-spawn: check pid file and in-memory set
    pid_file = job_dir / "pid"
    if pid_file.exists():
        logger.warning(f"spawn_worker: pid file already exists for {job_id}, skipping")
        return
    if job_id in _spawned_jobs:
        logger.warning(f"spawn_worker called twice for job {job_id} — ignoring duplicate")
        return
    _spawned_jobs.add(job_id)

    log_file = open(job_dir / "worker.log", "w")

    if gpu_assigned is not None:
        (job_dir / "gpu_assigned.txt").write_text(str(gpu_assigned))

    env = os.environ.copy()
    if gpu_assigned is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(gpu_assigned)
        logger.info(
            f"Job {job_id} assigned to GPU {gpu_assigned}, setting CUDA_VISIBLE_DEVICES={gpu_assigned}"
        )

    proc = subprocess.Popen(
        ["python3", "worker.py", str(job_dir)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
    )

    pgid = os.getpgid(proc.pid)
    pid_file.write_text(str(proc.pid))
    (job_dir / "pgid").write_text(str(pgid))

    logger.info(f"Spawned worker for job {job_id} (PID: {proc.pid}, PGID: {pgid})")
    socketio.start_background_task(monitor_job, job_id, job_dir, proc)


def monitor_job(job_id: str, job_dir: Path, proc: subprocess.Popen):
    """Monitor job status and emit updates"""
    status_file = job_dir / "status.json"
    last_status = {}
    last_frame_count = 0
    last_synthesis_count = 0

    while proc.poll() is None:
        try:
            if status_file.exists():
                try:
                    status = json.loads(status_file.read_text())
                except json.JSONDecodeError:
                    socketio.sleep(1)
                    continue

                if status != last_status:
                    last_status = status.copy()
                    if DEBUG:
                        logger.debug(f"[MONITOR] job={job_id} status changed: stage={status.get('stage')} progress={status.get('progress')} current_frame={status.get('current_frame')}")
                    socketio.emit(
                        "job_status", {"job_id": job_id, **status}, room=f"job_{job_id}"
                    )

                    if status.get("stage") in (
                        "reconstructing",
                        "complete",
                    ) and status.get("transcript"):
                        socketio.emit(
                            "job_transcript",
                            {"job_id": job_id, "transcript": status["transcript"]},
                            room=f"job_{job_id}",
                        )

                    if status.get("video_description"):
                        socketio.emit(
                            "job_description",
                            {"job_id": job_id, "description": status["video_description"]},
                            room=f"job_{job_id}",
                        )

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
                            if DEBUG:
                                for nl in new_frames:
                                    try:
                                        fd = json.loads(nl)
                                        logger.debug(f"[MONITOR] job={job_id} frame={fd.get('frame_number')} analysis_len={len(str(fd.get('analysis','')))}")
                                    except Exception:
                                        pass
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
                
                # Monitor synthesis.jsonl for combined analysis
                synthesis_file = job_dir / "synthesis.jsonl"
                if synthesis_file.exists():
                    try:
                        lines = [
                            l for l in synthesis_file.read_text().strip().split("\n") if l
                        ]
                        new_synthesis = lines[last_synthesis_count:]
                        if new_synthesis:
                            logger.debug(
                                f"Emitting {len(new_synthesis)} new synthesis results for job {job_id}"
                            )
                            for line in new_synthesis:
                                try:
                                    synthesis_data = json.loads(line)
                                    socketio.emit(
                                        "frame_synthesis",
                                        {"job_id": job_id, **synthesis_data},
                                        room=f"job_{job_id}",
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to emit synthesis for job {job_id}: {e}"
                                    )
                        last_synthesis_count = len(lines)
                    except Exception as e:
                        logger.error(f"Error reading synthesis file for job {job_id}: {e}")

        except Exception as e:
            logger.error(f"Error monitoring job {job_id}: {e}")

        socketio.sleep(1)

    pgid_file = job_dir / "pgid"
    if pgid_file.exists():
        try:
            pgid = int(pgid_file.read_text().strip())
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        except Exception as e:
            logger.debug(f"PGID cleanup for job {job_id}: {e}")

    success = proc.returncode == 0
    if DEBUG:
        logger.debug(f"[MONITOR] job={job_id} worker exited returncode={proc.returncode} success={success}")
    job_obj = vram_manager.get_job(job_id)
    if job_obj and job_obj.status in (
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    ):
        # Update status.json to reflect the final state
        if status_file.exists():
            try:
                status = json.loads(status_file.read_text())
                status["status"] = job_obj.status.value
                status["stage"] = "cancelled" if job_obj.status == JobStatus.CANCELLED else status.get("stage", "error")
                if job_obj.status == JobStatus.CANCELLED:
                    status["error"] = "Job cancelled by user"
                status_file.write_text(json.dumps(status))
            except Exception:
                pass
        socketio.emit(
            "job_complete",
            {"job_id": job_id, "success": job_obj.status == JobStatus.COMPLETED, "status": job_obj.status.value},
            room=f"job_{job_id}",
        )
        logger.info(f"Job {job_id} finalized as {job_obj.status.value} (worker exited)")
        _spawned_jobs.discard(job_id)
        return
    vram_manager.complete_job(job_id, success)
    _spawned_jobs.discard(job_id)

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
                    {"job_id": job_id, "transcript": transcript_text},
                    room=f"job_{job_id}",
                )
            if description:
                socketio.emit(
                    "job_description",
                    {"job_id": job_id, "description": description},
                    room=f"job_{job_id}",
                )
        except Exception as e:
            logger.error(f"Failed to emit final results for {job_id}: {e}")

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

    if success:
        socketio.start_background_task(_sync_to_openwebui_kb, job_id)


def _sync_to_openwebui_kb(job_id: str):
    """Background task: sync job results to OpenWebUI KB if enabled"""
    try:
        from src.api.knowledge import _get_owui_config, sync_job_to_kb
        cfg = _get_owui_config()
        if cfg.get("enabled") and cfg.get("auto_sync"):
            logger.info(f"Auto-syncing job {job_id} to OpenWebUI KB...")
            result = sync_job_to_kb(job_id)
            if result.get("success"):
                logger.info(f"Job {job_id} synced to OpenWebUI KB successfully")
                socketio.emit(
                    "kb_sync_complete",
                    {"job_id": job_id, "kb_id": result.get("kb_id")},
                )
            else:
                logger.warning(f"Job {job_id} KB sync failed: {result.get('error')}")
                socketio.emit(
                    "kb_sync_error",
                    {"job_id": job_id, "error": result.get("error")},
                )
    except Exception as e:
        logger.error(f"Error in KB sync for job {job_id}: {e}")

    if success:
        socketio.start_background_task(_sync_to_openwebui_kb, job_id)


def _sync_to_openwebui_kb(job_id: str):
    """Background task: sync job results to OpenWebUI KB if enabled"""
    try:
        from src.api.knowledge import _get_owui_config, sync_job_to_kb
        cfg = _get_owui_config()
        if cfg.get("enabled") and cfg.get("auto_sync"):
            logger.info(f"Auto-syncing job {job_id} to OpenWebUI KB...")
            result = sync_job_to_kb(job_id)
            if result.get("success"):
                logger.info(f"Job {job_id} synced to OpenWebUI KB successfully")
                socketio.emit(
                    "kb_sync_complete",
                    {"job_id": job_id, "kb_id": result.get("kb_id")},
                )
            else:
                logger.warning(f"Job {job_id} KB sync failed: {result.get('error')}")
                socketio.emit(
                    "kb_sync_error",
                    {"job_id": job_id, "error": result.get("error")},
                )
    except Exception as e:
        logger.error(f"Error in KB sync for job {job_id}: {e}")


# ==================== Callbacks ====================


def on_vram_event(event: str, job):
    """Handle VRAM manager events"""
    logger.info(f"VRAM event: {event} job={job.job_id} status={job.status.value} gpu={job.gpu_assigned}")
    if event == "started":
        job_dir = Path("jobs") / job.job_id
        spawn_worker(job.job_id, job_dir, job.gpu_assigned)
    socketio.emit("vram_event", {"event": event, "job": job.to_dict()})


vram_manager.register_callback(on_vram_event)


def on_monitor_update(data: dict):
    """Handle system monitor updates"""
    socketio.emit("system_status", data)


monitor.register_callback(on_monitor_update)


def recover_stale_jobs():
    """On startup, find jobs with status 'running' that have no live worker and mark them failed."""
    jobs_dir = Path("jobs")
    if not jobs_dir.exists():
        return
    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        status_file = job_dir / "status.json"
        if not status_file.exists():
            continue
        try:
            status = json.loads(status_file.read_text())
        except Exception:
            continue
        if status.get("status") not in ("running", "queued"):
            continue
        # Check if worker process is still alive
        pid_file = job_dir / "pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)  # Check if process exists
                logger.info(f"Recovering monitor for running job {job_dir.name} (PID {pid})")
                _spawned_jobs.discard(job_dir.name)  # Allow re-spawn
                # Clean stale pid/pgid so spawn_worker doesn't skip
                pid_file.unlink(missing_ok=True)
                (job_dir / "pgid").unlink(missing_ok=True)
                # Re-queue the job with VRAM manager
                input_file = job_dir / "input.json"
                if input_file.exists():
                    try:
                        config = json.loads(input_file.read_text())
                        vram_manager.submit_job(
                            job_id=job_dir.name,
                            provider_type=config.get("provider_type", "ollama"),
                            provider_name=config.get("provider_name", ""),
                            model_id=config.get("model", ""),
                            vram_required=0,
                            video_path=config.get("video_path", ""),
                            params=config.get("params", {}),
                            priority=0,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to re-queue job {job_dir.name}: {e}")
            except ProcessLookupError:
                logger.info(f"Job {job_dir.name} has stale PID, marking failed")
                status["status"] = "failed"
                status["stage"] = "error"
                status["error"] = "Worker process died (container restart)"
                status_file.write_text(json.dumps(status))
                pid_file.unlink(missing_ok=True)
                (job_dir / "pgid").unlink(missing_ok=True)
            except PermissionError:
                pass
            except Exception as e:
                logger.warning(f"Error checking stale job {job_dir.name}: {e}")


recover_stale_jobs()


# ==================== Transcode Helpers ====================


def _transcode_and_delete_with_cleanup(src_path: str, fps: float = None, whisper_model: str = "base", language: str = "en"):
    """
    Background task: transcode src_path to 720p@<fps>fps, extract frames + thumbnails,
    transcribe audio, emit progress via socket, then refresh the video list.
    Source file is preserved (no longer deleted after transcode).
    If fps is None, detect original framerate from source video.
    """
    input_path = Path(src_path)
    src_name = input_path.name
    
    # output_name and output_path will be defined after fps detection

    log_file = None

    try:
        duration_s = 0.0
        # Detect framerate from source video if not provided
        if fps is None:
            try:
                probe = subprocess.run(
                    [
                        "ffprobe", "-v", "error",
                        "-show_entries", "format=duration",
                        "-show_entries", "stream=r_frame_rate",
                        "-of", "json", str(input_path),
                    ],
                    capture_output=True, text=True, timeout=15,
                )
                if probe.returncode == 0:
                    info = json.loads(probe.stdout)
                    fmt = info.get("format", {})
                    duration_s = float(fmt.get("duration", 0))
                    streams = info.get("streams", [])
                    
                    logger.debug(f"Framerate detection for {src_name}: found {len(streams)} streams")
                    
                    if streams:
                        # Find first video stream
                        video_stream = None
                        for i, stream in enumerate(streams):
                            codec_type = stream.get("codec_type", "unknown")
                            r_fr = stream.get("r_frame_rate", "N/A")
                            logger.debug(f"  Stream {i}: codec_type={codec_type}, r_frame_rate={r_fr}")
                            if codec_type == "video":
                                video_stream = stream
                                logger.debug(f"  Found video stream at index {i}")
                                break
                        
                        # If no video stream found, use first stream
                        if video_stream is None:
                            video_stream = streams[0]
                            logger.debug("No video stream found, using first stream")
                        
                        r_fr = video_stream.get("r_frame_rate", "1/1")
                        logger.debug(f"Selected stream r_frame_rate: {r_fr}")
                        
                        if "/" in r_fr:
                            num, den = r_fr.split("/")
                            fps = float(num) / float(den) if float(den) else 1.0
                            logger.debug(f"Parsed as fraction: {num}/{den} = {fps} fps")
                        else:
                            try:
                                fps = float(r_fr)
                                logger.debug(f"Parsed as float: {fps} fps")
                            except ValueError:
                                fps = 1.0
                                logger.debug(f"Could not parse as float, using default: {fps} fps")
                    else:
                        fps = 1.0
                        logger.debug(f"No streams found, using default: {fps} fps")
                else:
                    fps = 1.0
                    logger.debug(f"FFprobe failed (returncode={probe.returncode}), using default: {fps} fps")
            except Exception as e:
                logger.warning(f"Failed to detect framerate from {src_name}: {e}")
                logger.debug(f"Exception details:", exc_info=True)
                fps = 1.0
        else:
            # If fps was provided, still get duration for progress reporting
            try:
                probe = subprocess.run(
                    [
                        "ffprobe",
                        "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        str(input_path),
                    ],
                    capture_output=True, text=True, timeout=15,
                )
                if probe.returncode == 0:
                    duration_s = float(probe.stdout.strip())
            except Exception:
                pass

        # Update output filename with actual fps (smart rounding)
        # For common video framerates (≈24, ≈25, ≈30, ≈60): round to nearest integer
        # For very low framerates (< 5): keep 1 decimal place
        # For others: round to nearest integer
        if fps < 5:
            # Low framerate, keep 1 decimal place for accuracy
            fps_rounded = round(fps, 1)
        else:
            # Normal framerate, round to nearest integer
            fps_rounded = round(fps)
        
        # Format without trailing .0 if integer
        if fps_rounded == int(fps_rounded):
            fps_formatted = int(fps_rounded)
        else:
            fps_formatted = fps_rounded
            
        output_name = f"{input_path.stem}_720p{fps_formatted}fps.mp4"
        output_path = input_path.parent / output_name

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

        _emit("starting", 0)
        logger.info(
            f"Transcoding {src_name} -> {output_name} at {fps_formatted}fps (duration {duration_s:.1f}s, original framerate)"
        )
        logger.info(f"Detected framerate for {src_name}: {fps} fps (formatted as {fps_formatted} for filename)")

        try:
            cmd = build_transcode_command(
                input_path=str(input_path),
                output_path=str(output_path),
                width=1280, height=720, fps=fps, gpu_index=0,
            )

            logger.info(f"Transcode command: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )

            output_lines = []
            error_lines = []

            def read_output(stream, target_list):
                for line in stream:
                    target_list.append(line)

            stdout_thread = threading.Thread(target=read_output, args=(proc.stdout, output_lines))
            stderr_thread = threading.Thread(target=read_output, args=(proc.stderr, error_lines))
            stdout_thread.start()
            stderr_thread.start()

            current_time_s = 0.0
            parse_progress = get_transcode_progress_parser("standard")
            proc.wait(timeout=3600)
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

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

            err_content = "".join(error_lines)[-400:] if error_lines else "unknown error"

            if proc.returncode == 0:
                _emit("finalizing", 99)
                ensure_thumbnail(str(output_path))
                logger.info(f"Transcode complete: {output_name}")
                _emit("complete", 100)
                # Fix permissions on any root-owned dirs from Docker
                _fix_permissions(input_path.parent)
                _extract_frames(str(output_path))
                _transcribe_video(str(output_path), whisper_model, language)
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
        if log_file:
            log_file.close()

    socketio.emit("videos_updated", {})


def _fix_permissions(base_dir: Path):
    """Fix root-owned files/dirs created by Docker to be user-writable."""
    try:
        import os
        uid = os.getuid()
        for item in base_dir.rglob("*"):
            try:
                stat = item.stat()
                if stat.st_uid == 0:  # owned by root
                    if item.is_dir():
                        os.chmod(item, 0o775)
                    else:
                        os.chmod(item, 0o664)
                    os.chown(item, uid, -1)
            except (OSError, PermissionError):
                pass
    except Exception as e:
        logger.warning(f"Permission fix failed: {e}")


def _run_dedup_sequential(frames_dir: Path, thumbs_dir: Path, dedup_threshold: int, fps: float):
    """Run sequential deduplication on extracted frames. Returns dedup results dict."""
    extracted_frames = sorted(frames_dir.glob("frame_*.jpg"))
    original_count = len(extracted_frames)
    original_frame_numbers = {}
    original_timestamps = {}
    for fp in extracted_frames:
        old_num = int(fp.stem.split("_")[1])
        original_frame_numbers[old_num] = old_num
        original_timestamps[old_num] = round((old_num - 1) / fps, 3)

    if dedup_threshold <= 0 or original_count <= 1:
        return {
            "original_count": original_count,
            "deduped_count": original_count,
            "threshold": dedup_threshold,
            "original_to_dedup_mapping": {str(k): k for k in range(1, original_count + 1)},
            "original_timestamps": {str(k): v for k, v in original_timestamps.items()},
            "dedup_to_original_mapping": {str(k): k for k in range(1, original_count + 1)},
        }

    try:
        from PIL import Image
        import imagehash
        keep = [extracted_frames[0]]
        prev_hash = imagehash.phash(Image.open(extracted_frames[0]))
        for fp in extracted_frames[1:]:
            curr_hash = imagehash.phash(Image.open(fp))
            if (prev_hash - curr_hash) >= dedup_threshold:
                keep.append(fp)
                prev_hash = curr_hash
        removed = original_count - len(keep)
        if removed > 0:
            for fp in extracted_frames:
                if fp not in keep:
                    fp.unlink()
                    thumb = thumbs_dir / fp.name.replace("frame_", "thumb_")
                    if thumb.exists():
                        thumb.unlink()
        actual_count = len(keep)
        logger.info(f"Sequential dedup removed {removed} similar frames (threshold={dedup_threshold}), {actual_count} remaining")
    except Exception as e:
        logger.warning(f"Frame dedup failed (non-fatal): {e}")
        actual_count = original_count
        keep = extracted_frames

    original_to_dedup = {}
    dedup_to_original = {}
    kept_timestamps = {}
    for new_idx, fp in enumerate(sorted(keep), start=1):
        old_num = int(fp.stem.split("_")[1])
        original_to_dedup[str(old_num)] = new_idx
        dedup_to_original[str(new_idx)] = old_num
        kept_timestamps[str(new_idx)] = round((old_num - 1) / fps, 3)

    return {
        "original_count": original_count,
        "deduped_count": actual_count,
        "threshold": dedup_threshold,
        "original_to_dedup_mapping": original_to_dedup,
        "original_timestamps": kept_timestamps,
        "dedup_to_original_mapping": dedup_to_original,
    }


def _run_dedup_parallel(frames_dir: Path, thumbs_dir: Path, dedup_threshold: int, fps: float, max_workers: int = None):
    """Run parallel deduplication on extracted frames. Returns dedup results dict."""
    import time
    from src.utils.parallel_hash import compute_hashes_parallel
    from src.utils.parallel_file_ops import delete_frames_parallel
    
    extracted_frames = sorted(frames_dir.glob("frame_*.jpg"))
    original_count = len(extracted_frames)
    
    logger.info(f"Starting parallel deduplication for {original_count} frames")
    logger.info(f"Threshold: {dedup_threshold}, FPS: {fps}, Max workers: {max_workers}")
    
    # Store original frame metadata
    original_timestamps = {}
    for fp in extracted_frames:
        old_num = int(fp.stem.split("_")[1])
        original_timestamps[old_num] = round((old_num - 1) / fps, 3)
    
    # Early return for trivial cases
    if dedup_threshold <= 0 or original_count <= 1:
        logger.info(f"Trivial case: threshold={dedup_threshold}, frames={original_count}")
        return {
            "original_count": original_count,
            "deduped_count": original_count,
            "threshold": dedup_threshold,
            "original_to_dedup_mapping": {str(k): k for k in range(1, original_count + 1)},
            "original_timestamps": {str(k): v for k, v in original_timestamps.items()},
            "dedup_to_original_mapping": {str(k): k for k in range(1, original_count + 1)},
        }
    
    performance_metrics = {}
    
    try:
        # PHASE 1: Parallel hash computation
        logger.info("PHASE 1: Computing perceptual hashes in parallel...")
        hash_start = time.time()
        
        hash_results = compute_hashes_parallel(
            extracted_frames,
            max_workers=max_workers,
            chunk_size=100
        )
        
        hash_time = time.time() - hash_start
        performance_metrics["hash_computation_time"] = hash_time
        
        if not hash_results:
            logger.error("No hashes computed successfully, falling back to sequential")
            return _run_dedup_sequential(frames_dir, thumbs_dir, dedup_threshold, fps)
        
        # PHASE 2: Sequential dedup logic (fast with pre-computed hashes)
        logger.info("PHASE 2: Running deduplication logic...")
        dedup_start = time.time()
        
        # Extract hashes in frame order
        hashes = []
        frame_order = []
        for fp in extracted_frames:
            if fp in hash_results:
                phash, frame_num = hash_results[fp]
                hashes.append(phash)
                frame_order.append((fp, frame_num))
            else:
                # Use placeholder for failed frames (kept by default)
                hashes.append(None)
                frame_order.append((fp, -1))
        
        # Run dedup algorithm
        keep_indices = [0]  # Always keep first frame
        prev_hash = hashes[0]
        
        for i in range(1, len(hashes)):
            if hashes[i] is None:
                # Keep frames with failed hash computation
                keep_indices.append(i)
                prev_hash = hashes[i-1] if i > 0 and hashes[i-1] is not None else None
            elif prev_hash is not None and (prev_hash - hashes[i]) >= dedup_threshold:
                keep_indices.append(i)
                prev_hash = hashes[i]
        
        # Get frames to keep
        keep_frames = [frame_order[i][0] for i in keep_indices]
        actual_count = len(keep_frames)
        removed = original_count - actual_count
        
        dedup_time = time.time() - dedup_start
        performance_metrics["dedup_logic_time"] = dedup_time
        
        logger.info(f"Dedup logic complete: {removed} frames to remove, {actual_count} to keep")
        
        # PHASE 3: Parallel file deletion
        if removed > 0:
            logger.info(f"PHASE 3: Deleting {removed} frames in parallel...")
            delete_start = time.time()
            
            # Determine frames to delete
            frames_to_delete = []
            for i, (fp, _) in enumerate(frame_order):
                if i not in keep_indices:
                    frames_to_delete.append(fp)
            
            # Delete in parallel
            delete_stats = delete_frames_parallel(
                frames_to_delete,
                thumbs_dir,
                max_workers=min(max_workers or 30, len(frames_to_delete) // 10 + 1)
            )
            
            delete_time = time.time() - delete_start
            performance_metrics["file_deletion_time"] = delete_time
            performance_metrics["deletion_stats"] = delete_stats
            
            logger.info(f"Deleted {delete_stats['successful']}/{delete_stats['total']} frames "
                       f"({delete_stats['success_rate']}% success)")
            
            if delete_stats['failed'] > 0:
                logger.warning(f"Failed to delete {delete_stats['failed']} frames")
        
        else:
            logger.info("PHASE 3: No frames to delete")
            performance_metrics["file_deletion_time"] = 0
        
        # PHASE 4: Build results mapping
        logger.info("PHASE 4: Building results mapping...")
        mapping_start = time.time()
        
        original_to_dedup = {}
        dedup_to_original = {}
        kept_timestamps = {}
        
        for new_idx, (fp, old_num) in enumerate([frame_order[i] for i in keep_indices], start=1):
            if old_num > 0:  # Valid frame number
                original_to_dedup[str(old_num)] = new_idx
                dedup_to_original[str(new_idx)] = old_num
                kept_timestamps[str(new_idx)] = round((old_num - 1) / fps, 3)
            else:
                # Handle frames with unknown original number
                try:
                    actual_num = int(fp.stem.split("_")[1])
                    original_to_dedup[str(actual_num)] = new_idx
                    dedup_to_original[str(new_idx)] = actual_num
                    kept_timestamps[str(new_idx)] = round((actual_num - 1) / fps, 3)
                except:
                    # Fallback: use index
                    original_to_dedup[str(new_idx)] = new_idx
                    dedup_to_original[str(new_idx)] = new_idx
                    kept_timestamps[str(new_idx)] = round((new_idx - 1) / fps, 3)
        
        mapping_time = time.time() - mapping_start
        performance_metrics["mapping_time"] = mapping_time
        
        # Calculate total time
        total_time = hash_time + dedup_time + performance_metrics.get("file_deletion_time", 0) + mapping_time
        performance_metrics["total_time"] = total_time
        
        logger.info(f"Parallel deduplication completed in {total_time:.2f}s:")
        logger.info(f"  Hash computation: {hash_time:.2f}s")
        logger.info(f"  Dedup logic: {dedup_time:.2f}s")
        logger.info(f"  File deletion: {performance_metrics.get('file_deletion_time', 0):.2f}s")
        logger.info(f"  Mapping: {mapping_time:.2f}s")
        logger.info(f"  Removed {removed} similar frames (threshold={dedup_threshold}), {actual_count} remaining")
        
        return {
            "original_count": original_count,
            "deduped_count": actual_count,
            "threshold": dedup_threshold,
            "original_to_dedup_mapping": original_to_dedup,
            "original_timestamps": kept_timestamps,
            "dedup_to_original_mapping": dedup_to_original,
            "performance_metrics": performance_metrics
        }
        
    except Exception as e:
        logger.error(f"Parallel dedup failed: {e}", exc_info=True)
        logger.warning("Falling back to sequential dedup")
        
        # Fall back to sequential
        return _run_dedup_sequential(frames_dir, thumbs_dir, dedup_threshold, fps)


def _run_dedup(frames_dir: Path, thumbs_dir: Path, dedup_threshold: int, fps: float):
    """Smart deduplication dispatcher - chooses parallel or sequential based on workload."""
    extracted_frames = sorted(frames_dir.glob("frame_*.jpg"))
    original_count = len(extracted_frames)
    
    # Check if parallel utilities are available
    if not PARALLEL_DEDUP_AVAILABLE:
        logger.warning("Parallel deduplication utilities not available, using sequential")
        return _run_dedup_sequential(frames_dir, thumbs_dir, dedup_threshold, fps)
    
    try:
        from src.utils.dedup_scheduler import get_dedup_strategy, log_dedup_start, log_dedup_completion
        
        # Get dedup strategy
        strategy = get_dedup_strategy(
            frame_count=original_count,
            dedup_threshold=dedup_threshold,
            video_duration=original_count / fps if fps > 0 else 0,
            available_memory_gb=192  # System has 192GB RAM
        )
        
        # Log start
        log_dedup_start(strategy)
        
        # Execute chosen strategy
        if strategy["use_parallel"]:
            logger.info("Executing PARALLEL deduplication")
            results = _run_dedup_parallel(
                frames_dir, 
                thumbs_dir, 
                dedup_threshold, 
                fps, 
                max_workers=strategy["worker_count"]
            )
        else:
            logger.info("Executing SEQUENTIAL deduplication")
            results = _run_dedup_sequential(frames_dir, thumbs_dir, dedup_threshold, fps)
        
        # Add strategy info to results
        results["dedup_strategy"] = {
            "method": "parallel" if strategy["use_parallel"] else "sequential",
            "worker_count": strategy["worker_count"],
            "reason": strategy["reason"]
        }
        
        # Log completion
        performance = results.get("performance_metrics", {})
        log_dedup_completion(strategy, results, performance)
        
        return results
        
    except Exception as e:
        logger.error(f"Error in smart dedup dispatcher: {e}", exc_info=True)
        logger.warning("Falling back to sequential dedup")
        return _run_dedup_sequential(frames_dir, thumbs_dir, dedup_threshold, fps)


def _renumber_frames(frames_dir: Path, thumbs_dir: Path, fps: float):
    """Renumber frames sequentially and build timestamp index."""
    kept_frames = sorted(frames_dir.glob("frame_*.jpg"))
    actual_count = len(kept_frames)
    frames_index = {}
    
    # Detect if we need to adjust FPS for timestamp calculation
    # If fps is 1.0 (analysis FPS) but frame numbers suggest original video FPS,
    # we need to estimate the correct FPS for timestamp calculation
    adjusted_fps = fps
    if actual_count > 0 and fps == 1.0:
        # Get the largest frame number
        max_frame_num = 0
        for frame in kept_frames:
            try:
                frame_num = int(frame.stem.split("_")[1])
                max_frame_num = max(max_frame_num, frame_num)
            except (ValueError, IndexError):
                pass
        
        # If max frame number is much larger than frame count * expected duration,
        # we're likely dealing with original FPS frames, not 1fps frames
        # A 7-minute (420s) video at 1fps should have ~420 frames
        # If we have frame numbers like 10342, that suggests original FPS ~25-30
        if max_frame_num > actual_count * 10:  # Heuristic: frame numbers are much larger than expected
            # Try to estimate original FPS from frame numbers
            # Common video FPS values
            common_fps = [23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0]
            video_duration_guess = 300  # Guess 5 minutes as typical video duration
            
            for orig_fps in common_fps:
                estimated_max_frame = video_duration_guess * orig_fps
                if abs(max_frame_num - estimated_max_frame) < estimated_max_frame * 0.5:  # Within 50%
                    adjusted_fps = orig_fps
                    logger.info(f"Detected original video FPS ≈ {orig_fps} from frame numbers (max={max_frame_num}, was using fps={fps})")
                    break
    
    for new_idx, old_frame in enumerate(kept_frames, start=1):
        old_num = int(old_frame.stem.split("_")[1])
        timestamp_s = (old_num - 1) / adjusted_fps
        frames_index[new_idx] = round(timestamp_s, 3)
        if new_idx != old_num:
            new_name = f"frame_{new_idx:06d}.jpg"
            new_path = frames_dir / new_name
            old_frame.rename(new_path)
            old_thumb = thumbs_dir / old_frame.name.replace("frame_", "thumb_")
            new_thumb = thumbs_dir / new_name.replace("frame_", "thumb_")
            if old_thumb.exists():
                old_thumb.rename(new_thumb)
    logger.info(f"Renumbered {actual_count} frames sequentially with timestamp index (using fps={adjusted_fps})")
    return frames_index, actual_count, adjusted_fps


def _extract_frames_direct(video_path: str, original_video_path: str = None):
    """
    Direct frame extraction from original video (no transcode step).
    Extracts all frames from video at original resolution/framerate.
    If original_video_path is provided, it will be deleted after successful extraction.
    """
    video = Path(video_path)
    original_video = Path(original_video_path) if original_video_path else None
    
    # Use the video stem for the directory name
    stem = video.stem.rsplit('_720p', 1)[0] if '_720p' in video.stem else video.stem
    if video.parent.name == 'uploads':
        # In uploads directory, create subdirectory for frames
        video_dir = video.parent / stem
    else:
        # In a subdirectory (like after transcode), use existing structure
        video_dir = video.parent / stem
    
    frames_dir = video_dir / "frames"
    thumbs_dir = frames_dir / "thumbs"
    
    # Fix permissions on any root-owned dirs created by Docker
    _fix_permissions(video.parent)
    
    frames_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    
    duration_s = 0.0
    fps = 1.0
    total_video_frames = 0
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-show_entries", "stream=r_frame_rate,nb_frames,width,height",
                "-of", "json", str(video),
            ],
            capture_output=True, text=True, timeout=15,
        )
        if probe.returncode == 0:
            info = json.loads(probe.stdout)
            fmt = info.get("format", {})
            streams = info.get("streams", [])
            duration_s = float(fmt.get("duration", 0))
            
            logger.debug(f"Direct frame extraction probe for {video.name}: found {len(streams)} streams")
            
            if streams:
                # Find first video stream
                video_stream = None
                for i, stream in enumerate(streams):
                    codec_type = stream.get("codec_type", "unknown")
                    r_fr = stream.get("r_frame_rate", "N/A")
                    width = stream.get("width", "N/A")
                    height = stream.get("height", "N/A")
                    logger.debug(f"  Stream {i}: codec_type={codec_type}, r_frame_rate={r_fr}, resolution={width}x{height}")
                    if codec_type == "video":
                        video_stream = stream
                        logger.debug(f"  Found video stream at index {i}")
                        break
                
                # If no video stream found, use first stream
                if video_stream is None:
                    video_stream = streams[0]
                    logger.debug("No video stream found, using first stream")
                
                nb = video_stream.get("nb_frames")
                if nb:
                    total_video_frames = int(nb)
                r_fr = video_stream.get("r_frame_rate", "1/1")
                logger.debug(f"Selected stream r_frame_rate: {r_fr}")
                if "/" in r_fr:
                    num, den = r_fr.split("/")
                    fps = float(num) / float(den) if float(den) else 1.0
                    logger.debug(f"Parsed as fraction: {num}/{den} = {fps} fps")
    except Exception as e:
        logger.warning(f"Failed to probe video for direct frame extraction: {e}")

    if total_video_frames == 0 and duration_s > 0:
        total_video_frames = int(duration_s * fps)

    src_name = video.name

    def _emit(stage, progress, error=None):
        socketio.emit(
            "frame_extraction_progress",
            {
                "source": src_name, "stage": stage, "progress": progress,
                "current_frame": 0, "total_frames": total_video_frames, "error": error,
            },
        )

    _emit("extracting_frames", 0, f"Extracting {total_video_frames} frames from original video")
    logger.info(f"Direct frame extraction from {src_name} ({total_video_frames} frames at {fps}fps)")

    # Extract frames using ffmpeg
    frame_pattern = frames_dir / "frame_%06d.jpg"
    extract_cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-q:v", "2",  # Quality factor (2-31, lower is better)
        "-f", "image2",
        str(frame_pattern),
    ]

    try:
        proc = subprocess.Popen(
            extract_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        def read_output(stream, prefix="", progress_callback=None):
            for line in stream:
                line = line.strip()
                if line:
                    # Parse frame number from ffmpeg output
                    if "frame=" in line:
                        try:
                            parts = line.split()
                            for part in parts:
                                if part.startswith("frame="):
                                    frame_num = int(part.split("=")[1])
                                    if total_video_frames > 0:
                                        progress = min(100, int((frame_num / total_video_frames) * 100))
                                        _emit("extracting_frames", progress, f"Extracted {frame_num}/{total_video_frames} frames")
                                    break
                        except (ValueError, IndexError):
                            pass

        stdout_thread = threading.Thread(target=read_output, args=(proc.stdout, "stdout"))
        stderr_thread = threading.Thread(target=read_output, args=(proc.stderr, "stderr"))
        
        stdout_thread.start()
        stderr_thread.start()
        
        proc.wait(timeout=3600)  # 1 hour timeout
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        if proc.returncode == 0:
            # Count actually extracted frames
            extracted_frames = sorted(frames_dir.glob("frame_*.jpg"))
            actual_count = len(extracted_frames)
            
            # Save frame index with original timestamps
            frames_index = {}
            for i, frame_file in enumerate(extracted_frames, start=1):
                frame_num = i
                timestamp_seconds = round((frame_num - 1) / fps, 3)
                frames_index[frame_num] = timestamp_seconds
            
            index_file = video_dir / "frames_index.json"
            with open(index_file, "w") as f:
                json.dump(frames_index, f, indent=2)
            
            # Create thumbnail from first frame
            if extracted_frames:
                try:
                    from PIL import Image
                    first_frame = extracted_frames[0]
                    thumb_path = video.parent / "thumbs" / f"{stem}.jpg"
                    thumb_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    img = Image.open(first_frame)
                    img.thumbnail((320, 240))
                    img.save(thumb_path, "JPEG", quality=85)
                except Exception as e:
                    logger.warning(f"Failed to create thumbnail: {e}")
                    # Copy first frame as thumbnail
                    import shutil
                    thumb_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(first_frame, thumb_path)
            
            _emit("complete", 100, f"Extracted {actual_count} frames")
            logger.info(f"Direct frame extraction complete: {actual_count} frames from {src_name}")
            
            # Delete original video if specified
            if original_video and original_video.exists():
                try:
                    original_video.unlink()
                    logger.info(f"Deleted original video: {original_video.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete original video {original_video.name}: {e}")
            
            return {
                "frames_dir": str(frames_dir),
                "frame_count": actual_count,
                "fps": fps,
                "duration": duration_s,
                "video_dir": str(video_dir),
            }
        else:
            stderr_content = proc.stderr.read() if proc.stderr else "unknown error"
            error_msg = f"Frame extraction failed: {stderr_content[-300:]}"
            _emit("failed", 0, error=error_msg)
            logger.error(f"Direct frame extraction failed for {src_name}: {stderr_content}")
            return None

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        _emit("failed", 0, error="Frame extraction timed out")
        logger.error(f"Direct frame extraction timed out for {src_name}")
        return None
    except Exception as e:
        _emit("failed", 0, error=str(e))
        logger.error(f"Direct frame extraction error for {src_name}: {e}")
        return None

def _process_video_direct(src_path: str, whisper_model: str = "base", language: str = "en"):
    """
    Process uploaded video directly: extract frames and transcribe audio in parallel.
    Deletes original video after successful extraction.
    """
    input_path = Path(src_path)
    src_name = input_path.name
    
    logger.info(f"Direct video processing started for {src_name}")
    
    def _emit_progress(stage, progress, error=None, source=None):
        socketio.emit(
            "video_processing_progress",
            {
                "source": source or src_name,
                "stage": stage,
                "progress": progress,
                "error": error,
            },
        )
    
    # Start both processes in parallel
    import concurrent.futures
    
    _emit_progress("starting", 0, "Starting parallel processing")
    
    results = {}
    errors = {}
    
    def extract_frames_task():
        try:
            _emit_progress("extracting_frames", 5, "Starting frame extraction", f"{src_name}_frames")
            result = _extract_frames_direct(str(input_path), str(input_path))
            if result:
                results["frames"] = result
                _emit_progress("extracting_frames", 100, "Frame extraction complete", f"{src_name}_frames")
                return True
            else:
                errors["frames"] = "Frame extraction failed"
                _emit_progress("extracting_frames", 0, "Frame extraction failed", f"{src_name}_frames")
                return False
        except Exception as e:
            errors["frames"] = str(e)
            _emit_progress("extracting_frames", 0, f"Frame extraction error: {e}", f"{src_name}_frames")
            return False
    
    def transcribe_audio_task():
        try:
            _emit_progress("transcribing_audio", 5, "Starting audio transcription", f"{src_name}_transcription")
            # Extract audio first
            stem = input_path.stem.rsplit('_720p', 1)[0] if '_720p' in input_path.stem else input_path.stem
            video_dir = input_path.parent / stem
            video_dir.mkdir(parents=True, exist_ok=True)
            
            audio_path = video_dir / "audio.wav"
            
            # Extract audio
            extract_cmd = [
                "ffmpeg", "-y", "-i", str(input_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                str(audio_path),
            ]
            
            proc = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=300)
            if proc.returncode != 0:
                stderr = proc.stderr or ""
                if "does not contain any stream" in stderr or "no audio" in stderr.lower():
                    _emit_progress("transcribing_audio", 100, "No audio stream found", f"{src_name}_transcription")
                    results["transcription"] = {"source": src_name, "model": whisper_model, "language": language, "text": "", "segments": []}
                    return True
                else:
                    _emit_progress("transcribing_audio", 0, f"Audio extraction failed: {stderr[-200:]}", f"{src_name}_transcription")
                    return False
            
            if not audio_path.exists() or audio_path.stat().st_size == 0:
                _emit_progress("transcribing_audio", 100, "No audio extracted", f"{src_name}_transcription")
                results["transcription"] = {"source": src_name, "model": whisper_model, "language": language, "text": "", "segments": []}
                return True
            
            # Transcribe with GPU
            _emit_progress("transcribing_audio", 30, "Loading Whisper model", f"{src_name}_transcription")
            
            from faster_whisper import WhisperModel
            
            device = "cuda"
            compute_type = "float16"
            
            try:
                model = WhisperModel(whisper_model, device=device, compute_type=compute_type)
            except Exception as cuda_err:
                logger.warning(f"CUDA unavailable for Whisper ({cuda_err}), falling back to CPU")
                device = "cpu"
                compute_type = "int8"
                model = WhisperModel(whisper_model, device=device, compute_type=compute_type)
            
            _emit_progress("transcribing_audio", 50, "Transcribing audio", f"{src_name}_transcription")
            
            # Language detection/validation
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
            lang_param = language if language in accepted_languages else None
            
            segments_generator, info = model.transcribe(
                str(audio_path),
                language=lang_param,
                beam_size=5,
                vad_filter=True,
            )
            
            segments = []
            for segment in segments_generator:
                segments.append({
                    "id": len(segments),
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": segment.text.strip(),
                })
            
            _emit_progress("transcribing_audio", 90, "Saving transcription", f"{src_name}_transcription")
            
            # Save transcription
            transcript_path = video_dir / "transcript.json"
            # Concatenate all segment texts
            full_text = " ".join(seg["text"] for seg in segments).strip()
            transcript_data = {
                "source": src_name,
                "model": whisper_model,
                "language": info.language if hasattr(info, 'language') else language,
                "text": full_text,
                "segments": segments,
            }
            with open(transcript_path, "w") as f:
                json.dump(transcript_data, f, indent=2)
            
            # Clean up audio file
            try:
                audio_path.unlink()
            except Exception:
                pass
            
            results["transcription"] = transcript_data
            _emit_progress("transcribing_audio", 100, "Transcription complete", f"{src_name}_transcription")
            return True
            
        except Exception as e:
            errors["transcription"] = str(e)
            _emit_progress("transcribing_audio", 0, f"Transcription error: {e}", f"{src_name}_transcription")
            return False
    
    # Run both tasks in parallel with timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_frames = executor.submit(extract_frames_task)
        future_transcribe = executor.submit(transcribe_audio_task)
        
        try:
            frames_result = future_frames.result(timeout=7200)  # 2 hours for frame extraction
            transcribe_result = future_transcribe.result(timeout=1800)  # 30 minutes for transcription
            
            if frames_result and transcribe_result:
                _emit_progress("complete", 100, "Processing complete")
                logger.info(f"Direct video processing complete for {src_name}")
                return True
            else:
                error_msg = "Processing failed: "
                if errors:
                    error_msg += "; ".join([f"{k}: {v}" for k, v in errors.items()])
                _emit_progress("failed", 0, error_msg)
                logger.error(f"Direct video processing failed for {src_name}: {errors}")
                return False
                
        except concurrent.futures.TimeoutError:
            _emit_progress("failed", 0, "Processing timed out")
            logger.error(f"Direct video processing timed out for {src_name}")
            return False
        except Exception as e:
            _emit_progress("failed", 0, f"Processing error: {e}")
            logger.error(f"Direct video processing error for {src_name}: {e}")
            return False

def _extract_frames(video_path: str):
    """Extract all frames and thumbnails from a transcoded video."""
    video = Path(video_path)
    stem = video.stem
    frames_dir = video.parent / stem / "frames"
    thumbs_dir = frames_dir / "thumbs"

    # Fix permissions on any root-owned dirs created by Docker
    _fix_permissions(video.parent)

    frames_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    duration_s = 0.0
    fps = 1.0
    total_video_frames = 0
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-show_entries", "stream=r_frame_rate,nb_frames",
                "-of", "json", str(video),
            ],
            capture_output=True, text=True, timeout=15,
        )
        if probe.returncode == 0:
            info = json.loads(probe.stdout)
            fmt = info.get("format", {})
            streams = info.get("streams", [])
            duration_s = float(fmt.get("duration", 0))
            
            logger.debug(f"Frame extraction probe for {video.name}: found {len(streams)} streams")
            
            if streams:
                # Find first video stream
                video_stream = None
                for i, stream in enumerate(streams):
                    codec_type = stream.get("codec_type", "unknown")
                    r_fr = stream.get("r_frame_rate", "N/A")
                    logger.debug(f"  Stream {i}: codec_type={codec_type}, r_frame_rate={r_fr}")
                    if codec_type == "video":
                        video_stream = stream
                        logger.debug(f"  Found video stream at index {i}")
                        break
                
                # If no video stream found, use first stream
                if video_stream is None:
                    video_stream = streams[0]
                    logger.debug("No video stream found, using first stream")
                
                nb = video_stream.get("nb_frames")
                if nb:
                    total_video_frames = int(nb)
                r_fr = video_stream.get("r_frame_rate", "1/1")
                logger.debug(f"Selected stream r_frame_rate: {r_fr}")
                if "/" in r_fr:
                    num, den = r_fr.split("/")
                    fps = float(num) / float(den) if float(den) else 1.0
                    logger.debug(f"Parsed as fraction: {num}/{den} = {fps} fps")
    except Exception as e:
        logger.warning(f"Failed to probe video for frame extraction: {e}")

    if total_video_frames == 0 and duration_s > 0:
        total_video_frames = int(duration_s * fps)

    src_name = video.name

    def _emit(stage, progress, error=None):
        socketio.emit(
            "frame_extraction_progress",
            {
                "source": src_name, "stage": stage, "progress": progress,
                "current_frame": 0, "total_frames": total_video_frames, "error": error,
            },
        )

    _emit("extracting_frames", 0)
    logger.info(f"Extracting frames from {src_name} ({total_video_frames} frames)")

    try:
        extract_cmd = [
            "ffmpeg", "-y", "-i", str(video),
            "-q:v", "5", str(frames_dir / "frame_%06d.jpg"),
        ]
        proc = subprocess.Popen(extract_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        proc.wait(timeout=1800)
        if proc.returncode != 0:
            err = proc.stderr.read()[-400:] if proc.stderr else "unknown"
            logger.error(f"Frame extraction failed: {err}")
            _emit("failed", 0, error=err)
            return
    except subprocess.TimeoutExpired:
        proc.kill()
        _emit("failed", 0, error="Frame extraction timed out")
        return
    except Exception as e:
        logger.error(f"Frame extraction error: {e}")
        _emit("failed", 0, error=str(e))
        return

    extracted_frames = sorted(frames_dir.glob("frame_*.jpg"))
    actual_count = len(extracted_frames)
    logger.info(f"Extracted {actual_count} frames from {src_name}")

    # Renumber frames sequentially and build timestamp index
    _emit("renumbering", 45)
    frames_index, actual_count, actual_fps = _renumber_frames(frames_dir, thumbs_dir, fps)

    # Save frames_index.json: {frame_num: timestamp_seconds}
    index_path = video.parent / stem / "frames_index.json"
    index_path.write_text(json.dumps(frames_index))

    _emit("generating_thumbnails", 50)
    try:
        thumb_cmd = [
            "ffmpeg", "-y", "-i", str(video),
            "-vf", "scale=320:-1", "-q:v", "5",
            str(thumbs_dir / "thumb_%06d.jpg"),
        ]
        proc = subprocess.Popen(thumb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        proc.wait(timeout=1800)
        if proc.returncode != 0:
            err = proc.stderr.read()[-400:] if proc.stderr else "unknown"
            logger.warning(f"Thumbnail extraction failed (non-fatal): {err}")
    except Exception as e:
        logger.warning(f"Thumbnail extraction error (non-fatal): {e}")

    # Use same rounding logic as _transcode_and_delete_with_cleanup
        if fps < 5:
            fps_rounded = round(fps, 1)
        else:
            fps_rounded = round(fps)
        
        meta = {"frame_count": actual_count, "fps": fps_rounded, "duration": duration_s}
    meta_path = video.parent / stem / "frames_meta.json"
    meta_path.write_text(json.dumps(meta))
    logger.info(f"Wrote frame metadata: {meta_path} ({meta})")
    _emit("complete", 100)


def _transcribe_video(video_path: str, whisper_model: str = "base", language: str = "en"):
    """
    Transcribe audio from a transcoded video using faster-whisper.
    Non-fatal: if transcription fails, the upload still succeeds.
    """
    video = Path(video_path)
    stem = video.stem
    video_dir = video.parent / stem
    # Fix permissions before writing (Docker may have created as root)
    _fix_permissions(video.parent)
    video_dir.mkdir(parents=True, exist_ok=True)
    src_name = video.name

    def _emit(stage, progress, error=None):
        socketio.emit(
            "transcription_progress",
            {"source": src_name, "stage": stage, "progress": progress, "error": error},
        )

    _emit("extracting_audio", 0)
    logger.info(f"Starting transcription for {src_name} (model={whisper_model}, lang={language})")

    audio_path = video_dir / "audio.wav"
    try:
        extract_cmd = [
            "ffmpeg", "-y", "-i", str(video),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path),
        ]
        proc = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            stderr = proc.stderr or ""
            if "does not contain any stream" in stderr or "no audio" in stderr.lower():
                logger.info(f"No audio stream in {src_name}, skipping transcription")
                _emit("complete", 100)
                return
            logger.warning(f"Audio extraction failed for {src_name}: {stderr[-300:]}")
            _emit("failed", 0, error="Audio extraction failed")
            return
        if not audio_path.exists() or audio_path.stat().st_size == 0:
            logger.info(f"No audio extracted from {src_name}, skipping transcription")
            _emit("complete", 100)
            return
    except subprocess.TimeoutExpired:
        _emit("failed", 0, error="Audio extraction timed out")
        return
    except Exception as e:
        logger.warning(f"Audio extraction error for {src_name}: {e}")
        _emit("failed", 0, error=str(e))
        return

    _emit("transcribing", 10)

    try:
        from faster_whisper import WhisperModel

        device = "cuda"
        compute_type = "float16"
        try:
            logger.info(f"Loading Whisper model '{whisper_model}' on {device}")
            model = WhisperModel(whisper_model, device=device, compute_type=compute_type)
        except Exception as cuda_err:
            logger.warning(f"CUDA unavailable for Whisper ({cuda_err}), falling back to CPU")
            device = "cpu"
            compute_type = "int8"
            model = WhisperModel(whisper_model, device=device, compute_type=compute_type)
        _emit("transcribing", 30)

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
        lang_param = language if language in accepted_languages else None

        segments_iter, info = model.transcribe(
            str(audio_path), beam_size=5, word_timestamps=False,
            vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
            language=lang_param,
        )
        _emit("transcribing", 50)

        segments = []
        full_text_parts = []
        for seg in segments_iter:
            segments.append({"text": seg.text, "start": seg.start})
            full_text_parts.append(seg.text)

        _emit("transcribing", 90)

        transcript_data = {
            "text": " ".join(full_text_parts),
            "segments": segments,
            "language": info.language if hasattr(info, "language") else language,
            "whisper_model": whisper_model,
        }
        transcript_path = video_dir / "transcript.json"
        transcript_path.write_text(json.dumps(transcript_data))
        logger.info(f"Transcription complete for {src_name}: {len(segments)} segments, model={whisper_model}")
        _emit("complete", 100)

    except Exception as e:
        logger.warning(f"Transcription failed for {src_name}: {e}")
        _emit("failed", 0, error=str(e))
    finally:
        try:
            if audio_path.exists():
                audio_path.unlink()
        except Exception:
            pass


# ==================== Initialization ====================


def init_providers():
    """Initialize default providers"""
    # Use localhost since we're running outside Docker
    ollama_local = OllamaProvider("Ollama-Local", "http://localhost:11434")
    providers["Ollama-Local"] = ollama_local

    # Load existing Ollama instances from config without scanning
    config_path = Path(__file__).parent / "config" / "default_config.json"
    known_instances = []
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            known_instances = config.get("ollama_instances", [])
        except Exception as e:
            logger.warning(f"Could not load config: {e}")

    # Add known instances from config
    for url in known_instances:
        if "localhost" not in url and "127.0.0.1" not in url:
            name = f"Ollama-{url.split('//')[1].split(':')[0]}"
            providers[name] = OllamaProvider(name, url)
            discovery.add_host(url)

    # Add specific Ollama instances on the network (hardcoded fallback)
    additional_ollama_hosts = [
        ("Ollama-192.168.1.237", "http://192.168.1.237:11434"),
        ("Ollama-192.168.1.241", "http://192.168.1.241:11434"),
    ]
    for name, url in additional_ollama_hosts:
        if url not in known_instances:
            providers[name] = OllamaProvider(name, url)
            discovery.add_host(url)

    # Initialize OpenRouter provider with API key from environment
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        providers["OpenRouter"] = OpenRouterProvider("OpenRouter", openrouter_key)
        logger.info("OpenRouter provider initialized with API key from environment")
    else:
        logger.warning("OPENROUTER_API_KEY not set - OpenRouter provider not available")

    def get_loaded_ollama_models() -> set:
        loaded = set()
        for p in providers.values():
            if hasattr(p, "get_running_models"):
                try:
                    for m in p.get_running_models():
                        loaded.add(m.get("name", ""))
                except Exception:
                    pass
        return loaded

    vram_manager.set_ollama_running_models_provider(get_loaded_ollama_models)


def _get_monitor_ollama_url():
    """Return the best available Ollama URL for monitoring.
    Prefers non-localhost providers (which work inside Docker) over localhost."""
    # First try any online non-localhost provider
    for p in providers.values():
        if hasattr(p, "base_url") and p.status == "online":
            url = p.base_url
            if "localhost" not in url and "127.0.0.1" not in url:
                return url
    # Fall back to any online provider
    for p in providers.values():
        if hasattr(p, "base_url") and p.status == "online":
            return p.base_url
    # Last resort: any provider with a base_url
    return next((p.base_url for p in providers.values() if hasattr(p, "base_url")), None)

monitor.set_ollama_url_provider(_get_monitor_ollama_url)

monitor.start()
init_providers()


if __name__ == "__main__":
    socketio.run(
        app, host="0.0.0.0", port=10000, debug=False, allow_unsafe_werkzeug=True
    )
