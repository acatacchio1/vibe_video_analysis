"""
System API routes
"""
from flask import Blueprint, jsonify
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
