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

from vram_manager import vram_manager, JobStatus
from discovery import discovery
from monitor import monitor
from providers.ollama import OllamaProvider
from thumbnail import ensure_thumbnail
from gpu_transcode import build_transcode_command, get_transcode_progress_parser

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
    max_http_buffer_size=1024 * 1024 * 100,
)

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

app.register_blueprint(videos_bp)
app.register_blueprint(providers_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(llm_bp)
app.register_blueprint(results_bp)
app.register_blueprint(system_bp)
app.register_blueprint(transcode_bp)

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
    if job_id in _spawned_jobs:
        logger.warning(
            f"spawn_worker called twice for job {job_id} — ignoring duplicate"
        )
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
    (job_dir / "pid").write_text(str(proc.pid))
    (job_dir / "pgid").write_text(str(pgid))

    logger.info(f"Spawned worker for job {job_id} (PID: {proc.pid}, PGID: {pgid})")
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

                if status != last_status:
                    last_status = status.copy()
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


# ==================== Callbacks ====================


def on_vram_event(event: str, job):
    """Handle VRAM manager events"""
    if event == "started":
        job_dir = Path("jobs") / job.job_id
        spawn_worker(job.job_id, job_dir, job.gpu_assigned)
    socketio.emit("vram_event", {"event": event, "job": job.to_dict()})


vram_manager.register_callback(on_vram_event)


def on_monitor_update(data: dict):
    """Handle system monitor updates"""
    socketio.emit("system_status", data)


monitor.register_callback(on_monitor_update)


# ==================== Transcode Helpers ====================


def _transcode_and_delete_with_cleanup(src_path: str, fps: float = 1, whisper_model: str = "base", language: str = "en", dedup_threshold: int = 10):
    """
    Background task: transcode src_path to 720p@<fps>fps, extract frames + thumbnails,
    transcribe audio, emit progress via socket, then refresh the video list.
    Source file is preserved (no longer deleted after transcode).
    """
    input_path = Path(src_path)
    output_name = f"{input_path.stem}_720p{fps}fps.mp4"
    output_path = input_path.parent / output_name
    src_name = input_path.name

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

        duration_s = 0.0
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

        _emit("starting", 0)
        logger.info(
            f"Transcoding {src_name} -> {output_name}  (duration {duration_s:.1f}s)"
        )

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
                _extract_frames(str(output_path), dedup_threshold)
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


def _extract_frames(video_path: str, dedup_threshold: int = 10):
    """Extract all frames and thumbnails from a transcoded video."""
    video = Path(video_path)
    stem = video.stem
    frames_dir = video.parent / stem / "frames"
    thumbs_dir = frames_dir / "thumbs"
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
            if streams:
                nb = streams[0].get("nb_frames")
                if nb:
                    total_video_frames = int(nb)
                r_fr = streams[0].get("r_frame_rate", "1/1")
                if "/" in r_fr:
                    num, den = r_fr.split("/")
                    fps = float(num) / float(den) if float(den) else 1.0
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

    if dedup_threshold > 0 and actual_count > 1:
        _emit("deduplicating", 35)
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
            removed = actual_count - len(keep)
            if removed > 0:
                for fp in extracted_frames:
                    if fp not in keep:
                        fp.unlink()
                        thumb = thumbs_dir / fp.name.replace("frame_", "thumb_")
                        if thumb.exists():
                            thumb.unlink()
                actual_count = len(keep)
                logger.info(f"Dedup removed {removed} similar frames (threshold={dedup_threshold}), {actual_count} remaining")
        except Exception as e:
            logger.warning(f"Frame dedup failed (non-fatal): {e}")

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

    meta = {"frame_count": actual_count, "fps": fps, "duration": duration_s}
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
            import torch
            if not torch.cuda.is_available():
                device = "cpu"
                compute_type = "int8"
        except Exception:
            device = "cpu"
            compute_type = "int8"

        logger.info(f"Loading Whisper model '{whisper_model}' on {device}")
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
    ollama_local = OllamaProvider("Ollama-Local", "http://host.docker.internal:11434")
    providers["Ollama-Local"] = ollama_local

    discovered = discovery.scan()
    for url in discovered:
        if "localhost" not in url and "127.0.0.1" not in url:
            name = f"Ollama-{url.split('//')[1].split(':')[0]}"
            providers[name] = OllamaProvider(name, url)

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


monitor.set_ollama_url_provider(
    lambda: next(
        (p.base_url for p in providers.values() if hasattr(p, "base_url")), None
    )
)

monitor.start()
init_providers()


if __name__ == "__main__":
    socketio.run(
        app, host="0.0.0.0", port=10000, debug=False, allow_unsafe_werkzeug=True
    )
