"""
Job API routes
"""
import json
import os
import signal
from pathlib import Path
from flask import Blueprint, request, jsonify
from vram_manager import vram_manager, JobStatus

jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("/api/jobs")
def list_jobs():
    jobs = vram_manager.get_all_jobs()
    return jsonify([job.to_dict() for job in jobs])


@jobs_bp.route("/api/jobs/running")
def running_jobs():
    jobs = vram_manager.get_running_jobs()
    return jsonify([job.to_dict() for job in jobs])


@jobs_bp.route("/api/jobs/queued")
def queued_jobs():
    jobs = vram_manager.get_queued_jobs()
    return jsonify([job.to_dict() for job in jobs])


@jobs_bp.route("/api/jobs/<job_id>")
def get_job(job_id):
    job = vram_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job_dir = Path("jobs") / job_id
    status_file = job_dir / "status.json"
    status_data = {}
    if status_file.exists():
        status_data = json.loads(status_file.read_text())
    result = job.to_dict()
    result.update(status_data)
    return jsonify(result)


@jobs_bp.route("/api/jobs/<job_id>/frames")
def get_job_frames(job_id):
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    job_dir = Path(__file__).parent.parent.parent / "jobs" / job_id
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
            except Exception:
                pass
    return jsonify(frames)


@jobs_bp.route("/api/jobs/<job_id>/results")
def get_job_results(job_id):
    results_file = Path("jobs") / job_id / "output" / "results.json"
    if not results_file.exists():
        return jsonify({"error": "Results not found"}), 404
    return jsonify(json.loads(results_file.read_text()))


@jobs_bp.route("/api/jobs/<job_id>", methods=["DELETE"])
def cancel_job(job_id):
    success = vram_manager.cancel_job(job_id)
    job_dir = Path(__file__).parent.parent.parent / "jobs" / job_id
    pgid_file = job_dir / "pgid"
    pid_file = job_dir / "pid"
    killed = False
    if pgid_file.exists():
        try:
            pgid = int(pgid_file.read_text().strip())
            os.killpg(pgid, signal.SIGTERM)
            killed = True
        except (ProcessLookupError, PermissionError):
            pass
        except Exception:
            pass
    if not killed and pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    if success:
        return jsonify({"success": True, "message": "Job cancellation initiated"})
    else:
        return jsonify({"error": "Cannot cancel job"}), 400


@jobs_bp.route("/api/jobs/<job_id>/priority", methods=["POST"])
def update_priority(job_id):
    data = request.json
    new_priority = data.get("priority", 0)
    success = vram_manager.update_priority(job_id, new_priority)
    return jsonify({"success": success})
