"""
Knowledge Base API blueprint
Endpoints for syncing video analysis results to OpenWebUI Knowledge Base.
"""
import json
import os
import logging
import threading
from pathlib import Path
from flask import Blueprint, request, jsonify

from src.services.openwebui_kb import OpenWebUIClient

logger = logging.getLogger(__name__)

knowledge_bp = Blueprint("knowledge", __name__)


def _get_owui_config() -> dict:
    """Load OpenWebUI config from default_config.json, overlaying env vars."""
    config_path = Path(__file__).parent.parent.parent / "config" / "default_config.json"
    if not config_path.exists():
        return {}
    try:
        config = json.loads(config_path.read_text())
        cfg = config.get("openwebui", {})
    except Exception as e:
        logger.error(f"Failed to load OpenWebUI config: {e}")
        return {}

    # Env var takes precedence for API key (same pattern as OPENROUTER_API_KEY)
    env_key = os.environ.get("OPENWEBUI_API_KEY", "").strip()
    if env_key:
        cfg["api_key"] = env_key

    return cfg


def _get_client() -> OpenWebUIClient:
    """Create an OpenWebUI client from saved config"""
    cfg = _get_owui_config()
    url = cfg.get("url", "")
    api_key = cfg.get("api_key", "")
    if not url or not api_key:
        raise ValueError("OpenWebUI URL or API key not configured")
    return OpenWebUIClient(url, api_key)


def _get_video_name_for_job(job_id: str) -> str:
    """Try to find the video name associated with a job"""
    job_dir = Path("jobs") / job_id
    input_file = job_dir / "input.json"
    if input_file.exists():
        try:
            inp = json.loads(input_file.read_text())
            video_path = inp.get("video_path", "")
            if video_path:
                return Path(video_path).name
        except Exception:
            pass
    results_file = job_dir / "output" / "results.json"
    if results_file.exists():
        try:
            results = json.loads(results_file.read_text())
            meta = results.get("metadata", {})
            if meta.get("video_path"):
                return Path(meta["video_path"]).name
        except Exception:
            pass
    return f"job_{job_id}"


def sync_job_to_kb(job_id: str) -> dict:
    """Sync a single job's results to OpenWebUI KB. Thread-safe."""
    cfg = _get_owui_config()
    if not cfg.get("enabled"):
        return {"success": False, "error": "OpenWebUI integration is disabled"}

    results_file = Path("jobs") / job_id / "output" / "results.json"
    if not results_file.exists():
        return {"success": False, "error": "Results file not found"}

    try:
        results = json.loads(results_file.read_text())
    except Exception as e:
        return {"success": False, "error": f"Failed to read results: {e}"}

    video_name = _get_video_name_for_job(job_id)
    kb_name = cfg.get("knowledge_base_name", "Video Analyzer")

    try:
        client = _get_client()
    except ValueError as e:
        return {"success": False, "error": str(e)}

    try:
        result = client.upload_result_to_kb(
            results=results,
            video_name=video_name,
            kb_name=kb_name,
            job_id=job_id,
        )
        return result
    except Exception as e:
        logger.error(f"Error syncing job {job_id} to KB: {e}")
        return {"success": False, "error": str(e)}


@knowledge_bp.route("/api/knowledge/sync/<job_id>", methods=["POST"])
def sync_single_job(job_id):
    """Manually push a specific job's results to the KB"""
    result = sync_job_to_kb(job_id)
    if result.get("success"):
        return jsonify(result), 200
    return jsonify(result), 400


@knowledge_bp.route("/api/knowledge/sync-all", methods=["POST"])
def sync_all_jobs():
    """Push all existing completed job results to the KB"""
    cfg = _get_owui_config()
    if not cfg.get("enabled"):
        return jsonify({"success": False, "error": "OpenWebUI integration is disabled"}), 400

    jobs_dir = Path("jobs")
    if not jobs_dir.exists():
        return jsonify({"success": True, "total": 0, "synced": 0, "failed": 0, "skipped": 0})

    results = {"total": 0, "synced": 0, "failed": 0, "skipped": 0, "errors": []}

    for job_dir in jobs_dir.iterdir():
        if not job_dir.is_dir():
            continue
        results_file = job_dir / "output" / "results.json"
        if not results_file.exists():
            results["skipped"] += 1
            continue

        job_id = job_dir.name
        results["total"] += 1

        try:
            sync_result = sync_job_to_kb(job_id)
            if sync_result.get("success"):
                results["synced"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({"job_id": job_id, "error": sync_result.get("error")})
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({"job_id": job_id, "error": str(e)})

    return jsonify({"success": True, **results})


@knowledge_bp.route("/api/knowledge/status")
def get_kb_status():
    """Get current OpenWebUI KB configuration and connection status"""
    cfg = _get_owui_config()
    status = {
        "enabled": cfg.get("enabled", False),
        "url": cfg.get("url", ""),
        "has_api_key": bool(cfg.get("api_key")),
        "knowledge_base_name": cfg.get("knowledge_base_name", "Video Analyzer"),
        "auto_sync": cfg.get("auto_sync", True),
    }

    if status["enabled"] and status["has_api_key"]:
        try:
            client = _get_client()
            test = client.test_connection()
            status["connection"] = test
        except Exception as e:
            status["connection"] = {"ok": False, "error": str(e)}

    return jsonify(status)


@knowledge_bp.route("/api/knowledge/test", methods=["POST"])
def test_connection():
    """Test the OpenWebUI connection with provided settings"""
    data = request.json or {}
    url = data.get("url", _get_owui_config().get("url", ""))
    api_key = data.get("api_key", _get_owui_config().get("api_key", ""))

    if not url or not api_key:
        return jsonify({"ok": False, "error": "URL and API key are required"}), 400

    try:
        client = OpenWebUIClient(url, api_key)
        result = client.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@knowledge_bp.route("/api/knowledge/config", methods=["POST"])
def save_config():
    """Save OpenWebUI configuration"""
    data = request.json or {}
    config_path = Path(__file__).parent.parent.parent / "config" / "default_config.json"

    try:
        config = json.loads(config_path.read_text())
    except Exception as e:
        return jsonify({"error": f"Failed to read config: {e}"}), 500

    if "enabled" in data:
        config.setdefault("openwebui", {})["enabled"] = data["enabled"]
    if "url" in data:
        config.setdefault("openwebui", {})["url"] = data["url"]
    if "api_key" in data and data["api_key"]:
        config.setdefault("openwebui", {})["api_key"] = data["api_key"]
    if "knowledge_base_name" in data:
        config.setdefault("openwebui", {})["knowledge_base_name"] = data["knowledge_base_name"]
    if "auto_sync" in data:
        config.setdefault("openwebui", {})["auto_sync"] = data["auto_sync"]

    try:
        config_path.write_text(json.dumps(config, indent=2))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to save config: {e}"}), 500


@knowledge_bp.route("/api/knowledge/bases")
def list_knowledge_bases():
    """List existing knowledge bases from OpenWebUI"""
    try:
        client = _get_client()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        bases = client.list_knowledge_bases()
        return jsonify({"bases": bases})
    except Exception as e:
        logger.error(f"Failed to list KBs: {e}")
        return jsonify({"error": str(e)}), 500


@knowledge_bp.route("/api/knowledge/send/<job_id>", methods=["POST"])
def send_to_kb(job_id):
    """Send a specific job's results to a chosen KB (by ID or name)."""
    data = request.json or {}
    kb_id = data.get("kb_id")
    kb_name = data.get("kb_name")

    if not kb_id and not kb_name:
        return jsonify({"error": "kb_id or kb_name is required"}), 400

    results_file = Path("jobs") / job_id / "output" / "results.json"
    if not results_file.exists():
        return jsonify({"error": "Results file not found"}), 404

    try:
        results = json.loads(results_file.read_text())
    except Exception as e:
        return jsonify({"error": f"Failed to read results: {e}"}), 500

    video_name = _get_video_name_for_job(job_id)

    try:
        client = _get_client()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        if kb_id:
            target_kb_id = kb_id
            existing = client.find_knowledge_base(kb_name or "")
            actual_kb_name = existing["name"] if existing else kb_id
        else:
            target_kb_id = client.ensure_knowledge_base(kb_name)
            if not target_kb_id:
                return jsonify({"error": f"Could not find or create KB '{kb_name}'"}), 400
            actual_kb_name = kb_name

        content = client.__class__.__module__.split('.')[0]
        from src.services.openwebui_kb import format_results_as_markdown
        content = format_results_as_markdown(results, video_name, job_id)
        safe_filename = Path(video_name).stem.replace(" ", "_")[:80]
        file_id = client.upload_text_file(content, f"{safe_filename}_{job_id[:8]}")
        if not file_id:
            return jsonify({"error": "Failed to upload file to OpenWebUI"}), 500

        added = client.add_file_to_knowledge(target_kb_id, file_id)
        if added:
            logger.info(f"Job {job_id} sent to KB '{actual_kb_name}'")
            return jsonify({"success": True, "kb_id": target_kb_id, "kb_name": actual_kb_name, "file_id": file_id})
        return jsonify({"error": "Failed to add file to knowledge base"}), 500
    except Exception as e:
        logger.error(f"Error sending job {job_id} to KB: {e}")
        return jsonify({"error": str(e)}), 500
