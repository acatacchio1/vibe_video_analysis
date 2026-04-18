"""
Stored Results API routes
"""
import json
from pathlib import Path
from flask import Blueprint, jsonify

results_bp = Blueprint("results", __name__)


@results_bp.route("/api/results")
def list_all_results():
    """List all completed jobs with their stored results"""
    results_list = []
    jobs_dir = Path("jobs")
    if not jobs_dir.exists():
        return jsonify([])

    for job_dir in sorted(jobs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
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
            desc_obj = res.get("video_description", {})
            desc_preview = ""
            if isinstance(desc_obj, str):
                desc_preview = desc_obj[:200]
            elif isinstance(desc_obj, dict):
                desc_preview = (desc_obj.get("response") or desc_obj.get("text") or "")[:200]

            results_list.append({
                "job_id": job_dir.name,
                "video_path": inp.get("video_path", ""),
                "model": inp.get("model", ""),
                "provider": inp.get("provider_type", ""),
                "created_at": inp.get("created_at", job_dir.stat().st_mtime),
                "mtime": job_dir.stat().st_mtime,
                "has_transcript": bool(res.get("transcript") and res["transcript"].get("text")),
                "frame_count": len(res.get("frame_analyses", [])),
                "desc_preview": desc_preview,
            })
        except Exception:
            continue

    return jsonify(results_list)
