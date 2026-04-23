"""
Video Reprocessing API routes (parallel extraction + transcription)
"""
from pathlib import Path
from flask import Blueprint, request, jsonify

transcode_bp = Blueprint("transcode", __name__)


@transcode_bp.route("/api/videos/transcode", methods=["POST"])
def transcode_video():
    """Direct processing for an already-uploaded video (extract frames + transcribe)"""
    from app import socketio, _process_video_direct
    data = request.json
    video_path = data.get("video_path")
    if not video_path or not Path(video_path).exists():
        return jsonify({"error": "Video not found"}), 404
    # Use default whisper settings
    whisper_model = data.get("whisper_model", "base")
    language = data.get("language", "en")
    socketio.start_background_task(_process_video_direct, video_path, whisper_model, language)
    return jsonify({"success": True, "message": "Video processing started"})


@transcode_bp.route("/api/videos/reprocess", methods=["POST"])
def reprocess_video():
    """Reprocess an already-uploaded video with new settings (whisper model, language)"""
    from app import socketio, _process_video_direct
    data = request.json
    video_path = data.get("video_path")
    if not video_path or not Path(video_path).exists():
        return jsonify({"error": "Video not found"}), 404
    
    # Delete existing extracted frames and transcription if they exist
    video_file = Path(video_path)
    stem = video_file.stem.rsplit('_720p', 1)[0] if '_720p' in video_file.stem else video_file.stem
    video_dir = video_file.parent / stem
    
    import shutil
    if video_dir.exists():
        try:
            shutil.rmtree(video_dir)
        except Exception as e:
            print(f"Warning: Could not remove existing video directory {video_dir}: {e}")
    
    # Process with new settings
    whisper_model = data.get("whisper_model", "base")
    language = data.get("language", "en")
    socketio.start_background_task(
        _process_video_direct, video_path, whisper_model, language
    )
    return jsonify({"success": True, "message": "Reprocessing started"})
