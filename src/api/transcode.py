"""
Transcode API routes
"""
from pathlib import Path
from flask import Blueprint, request, jsonify

transcode_bp = Blueprint("transcode", __name__)


@transcode_bp.route("/api/videos/transcode", methods=["POST"])
def transcode_video():
    """Manually trigger transcode for an already-uploaded video"""
    from app import socketio, _transcode_and_delete_with_cleanup
    data = request.json
    video_path = data.get("video_path")
    if not video_path or not Path(video_path).exists():
        return jsonify({"error": "Video not found"}), 404
    socketio.start_background_task(_transcode_and_delete_with_cleanup, video_path)
    return jsonify({"success": True, "message": "Transcoding started"})


@transcode_bp.route("/api/videos/reprocess", methods=["POST"])
def reprocess_video():
    """Reprocess an already-uploaded video with new settings (fps, dedup, whisper)"""
    from app import socketio, _transcode_and_delete_with_cleanup
    data = request.json
    video_path = data.get("video_path")
    if not video_path or not Path(video_path).exists():
        return jsonify({"error": "Video not found"}), 404
    fps = float(data.get("fps", 1))
    fps = max(0.0167, min(fps, 30))
    whisper_model = data.get("whisper_model", "base")
    language = data.get("language", "en")
    dedup_threshold = int(data.get("dedup_threshold", 10))
    socketio.start_background_task(
        _transcode_and_delete_with_cleanup, video_path, fps, whisper_model, language, dedup_threshold
    )
    return jsonify({"success": True, "message": "Reprocessing started"})
