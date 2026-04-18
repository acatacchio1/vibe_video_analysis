"""
Video API routes
"""
import json
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file

from src.utils.file import allowed_file, secure_filename as secure_filename_util, validate_upload_size
from src.utils.transcode import probe_all_videos
from thumbnail import get_thumbnail_path, ensure_thumbnail

videos_bp = Blueprint("videos", __name__)


@videos_bp.route("/")
def index():
    """Main page"""
    from flask import render_template
    version = "0.0.0"
    try:
        version = (Path(__file__).parent.parent.parent / "VERSION").read_text().strip()
    except Exception:
        pass
    return render_template("index.html", version=version)


@videos_bp.route("/api/videos")
def list_videos():
    """List uploaded videos with metadata"""
    from app import api_error
    upload_dir = Path(__file__).parent.parent.parent / "uploads"
    video_files = [
        f for f in upload_dir.glob("*")
        if f.is_file() and f.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    ]
    if not video_files:
        return jsonify([])

    video_paths = [str(f) for f in video_files]
    probed_videos = probe_all_videos(video_paths)
    videos = []
    for probed in probed_videos:
        video_file = Path(probed["path"])
        thumb_path = get_thumbnail_path(str(video_file))
        has_analysis = (upload_dir.parent / "jobs" / video_file.stem).exists()
        videos.append({
            "name": probed["name"],
            "path": str(video_file),
            "size": video_file.stat().st_size if video_file.exists() else 0,
            "size_human": probed.get("size_human", _format_bytes(video_file.stat().st_size if video_file.exists() else 0)),
            "created": datetime.fromtimestamp(video_file.stat().st_mtime if video_file.exists() else 0).isoformat(),
            "duration": probed.get("duration", 0),
            "duration_formatted": probed.get("duration_formatted", "0s"),
            "thumbnail": thumb_path if Path(thumb_path).exists() else None,
            "has_analysis": has_analysis,
            "frame_count": _get_frame_count(video_file),
        })
    videos.sort(key=lambda x: x["created"], reverse=True)
    return jsonify(videos)


@videos_bp.route("/api/videos/upload", methods=["POST"])
def upload_video():
    """Upload a video file"""
    from app import socketio, _transcode_and_delete_with_cleanup, api_error
    if "video" not in request.files:
        return api_error("No video file", 400)
    file = request.files["video"]
    if file.filename == "":
        return api_error("No file selected", 400)
    if not allowed_file(file.filename):
        return api_error("File type not allowed", 400)
    safe_filename = secure_filename_util(file.filename)
    file.stream.seek(0, 2)
    file_size = file.stream.tell()
    file.stream.seek(0)
    is_valid, msg = validate_upload_size(file_size)
    if not is_valid:
        return api_error(msg, 413)
    filepath = Path(__file__).parent.parent.parent / "uploads" / safe_filename
    counter = 1
    original_stem = filepath.stem
    while filepath.exists():
        filepath = Path(__file__).parent.parent.parent / "uploads" / f"{original_stem}_{counter}{filepath.suffix}"
        counter += 1
    file.save(filepath)
    fps = float(request.form.get("fps", 1))
    fps = max(0.0167, min(fps, 30))
    whisper_model = request.form.get("whisper_model", "base")
    language = request.form.get("language", "en")
    dedup_threshold = int(request.form.get("dedup_threshold", 10))
    socketio.start_background_task(
        _transcode_and_delete_with_cleanup, str(filepath), fps, whisper_model, language, dedup_threshold
    )
    return jsonify({"success": True, "filename": filepath.name, "path": str(filepath)})


@videos_bp.route("/api/videos/<filename>", methods=["DELETE"])
def delete_video(filename):
    """Delete a video and its thumbnail"""
    import shutil
    from app import api_error
    safe_name = secure_filename_util(filename)
    base = Path(__file__).parent.parent.parent
    filepath = base / "uploads" / safe_name
    if not filepath.exists():
        return api_error("Video not found", 404)
    filepath.unlink()
    thumb = base / "uploads" / "thumbs" / f"{Path(safe_name).stem}.jpg"
    if thumb.exists():
        thumb.unlink()
    job_dir = base / "jobs" / Path(safe_name).stem
    if job_dir.exists():
        shutil.rmtree(job_dir)
    return jsonify({"success": True})


@videos_bp.route("/api/thumbnail/<filename>")
def get_thumbnail(filename):
    """Get video thumbnail"""
    from app import api_error
    safe_name = secure_filename_util(filename)
    thumb_path = Path(__file__).parent.parent.parent / "uploads" / "thumbs" / f"{Path(safe_name).stem}.jpg"
    if thumb_path.exists():
        return send_file(thumb_path, mimetype="image/jpeg")
    return api_error("Thumbnail not found", 404)


@videos_bp.route("/api/videos/<filename>/frames")
def get_video_frames_meta(filename):
    safe_name = secure_filename_util(filename)
    stem = Path(safe_name).stem
    meta_path = Path(__file__).parent.parent.parent / "uploads" / stem / "frames_meta.json"
    if not meta_path.exists():
        return jsonify({"frame_count": 0, "fps": 0, "duration": 0})
    try:
        return jsonify(json.loads(meta_path.read_text()))
    except Exception:
        return jsonify({"frame_count": 0, "fps": 0, "duration": 0})


@videos_bp.route("/api/videos/<filename>/frames/<int:frame_num>")
def get_video_frame(filename, frame_num):
    from app import api_error
    safe_name = secure_filename_util(filename)
    stem = Path(safe_name).stem
    frame_path = Path(__file__).parent.parent.parent / "uploads" / stem / "frames" / f"frame_{frame_num:06d}.jpg"
    if not frame_path.exists():
        return api_error("Frame not found", 404)
    return send_file(frame_path, mimetype="image/jpeg")


@videos_bp.route("/api/videos/<filename>/frames/<int:frame_num>/thumb")
def get_video_frame_thumb(filename, frame_num):
    from app import api_error
    safe_name = secure_filename_util(filename)
    stem = Path(safe_name).stem
    thumb_path = Path(__file__).parent.parent.parent / "uploads" / stem / "frames" / "thumbs" / f"thumb_{frame_num:06d}.jpg"
    if not thumb_path.exists():
        frame_path = Path(__file__).parent.parent.parent / "uploads" / stem / "frames" / f"frame_{frame_num:06d}.jpg"
        if frame_path.exists():
            return send_file(frame_path, mimetype="image/jpeg")
        return api_error("Frame not found", 404)
    return send_file(thumb_path, mimetype="image/jpeg")


@videos_bp.route("/api/videos/<filename>/transcript")
def get_video_transcript(filename):
    safe_name = secure_filename_util(filename)
    stem = Path(safe_name).stem
    transcript_path = Path(__file__).parent.parent.parent / "uploads" / stem / "transcript.json"
    if not transcript_path.exists():
        return jsonify({"segments": [], "text": "", "language": None, "whisper_model": None})
    try:
        return jsonify(json.loads(transcript_path.read_text()))
    except Exception:
        return jsonify({"segments": [], "text": "", "language": None, "whisper_model": None})


def _get_frame_count(video_path: Path) -> int:
    meta_path = video_path.parent / video_path.stem / "frames_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            return meta.get("frame_count", 0)
        except Exception:
            pass
    return 0


def _format_bytes(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
