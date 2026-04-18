"""
System API routes
"""
import logging
from flask import Blueprint, jsonify, request
from vram_manager import vram_manager

system_bp = Blueprint("system", __name__)


@system_bp.route("/api/vram")
def get_vram_status():
    """Get current VRAM status for all GPUs"""
    return jsonify(vram_manager.get_status())


@system_bp.route("/api/gpus")
def get_gpu_list():
    """Get list of all GPUs with details"""
    gpus = vram_manager._get_gpu_status()
    return jsonify([
        {
            "index": gpu.index,
            "name": gpu.name,
            "total_gb": round(gpu.total_vram / (1024**3), 2),
            "used_gb": round(gpu.used_vram / (1024**3), 2),
            "free_gb": round(gpu.free_vram / (1024**3), 2),
        }
        for gpu in gpus
    ])


@system_bp.route("/api/debug", methods=["GET"])
def get_debug_status():
    """Get current debug mode status"""
    from config.constants import DEBUG
    return jsonify({"debug": DEBUG})


@system_bp.route("/api/debug", methods=["POST"])
def toggle_debug():
    """Toggle debug logging at runtime"""
    from config.constants import DEBUG
    data = request.json or {}
    enable = data.get("enable", not DEBUG)
    level = logging.DEBUG if enable else logging.INFO
    logging.getLogger().setLevel(level)
    for name in ("src.websocket.handlers", "src.api.videos", "src.api.providers",
                  "src.api.jobs", "src.api.transcode", "worker", __name__):
        logging.getLogger(name).setLevel(level)
    import config.constants as _c
    _c.DEBUG = enable
    msg = f"Debug mode {'enabled' if enable else 'disabled'}"
    logging.getLogger(__name__).info(msg)
    return jsonify({"debug": enable, "message": msg})
