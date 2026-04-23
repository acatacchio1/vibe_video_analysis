"""
Video API routes
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file

from src.utils.security import allowed_file, secure_filename as secure_filename_util, validate_upload_size
from src.utils.video import probe_all_videos
from thumbnail import get_thumbnail_path, ensure_thumbnail

videos_bp = Blueprint("videos", __name__)


def get_video_directory(filename):
    """
    Get the video directory path for a given filename, handling both old and new naming conventions.
    Old: video_name_720p.mp4 -> video_name_720p directory
    New: video_name_720p.mp4 -> video_name directory (removes _720p suffix)
    
    Also handles video files that haven't been processed yet (no directory exists).
    """
    safe_name = secure_filename_util(filename)
    stem = Path(safe_name).stem
    base = Path(__file__).parent.parent.parent / "uploads"
    
    # Try new naming convention first (removes _720p suffix if present)
    new_stem = stem.rsplit('_720p', 1)[0] if '_720p' in stem else stem
    video_dir = base / new_stem
    
    # If directory doesn't exist with new convention, try old convention
    if not video_dir.exists():
        video_dir = base / stem
    
    # If still doesn't exist, the video might not have been processed yet
    # Return the expected directory path based on new convention
    if not video_dir.exists():
        video_dir = base / new_stem
    
    return video_dir


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
    """Upload a video file (parallel frame extraction + transcription, no transcode)"""
    from app import socketio, _process_video_direct, api_error
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
    
    whisper_model = request.form.get("whisper_model", "base")
    language = request.form.get("language", "en")
    
    # Start parallel processing (extract frames + transcribe audio)
    socketio.start_background_task(
        _process_video_direct, str(filepath), whisper_model, language
    )
    return jsonify({"success": True, "filename": filepath.name, "path": str(filepath)})


@videos_bp.route("/api/videos/<filename>", methods=["DELETE"])
def delete_video(filename):
    """Delete a video and its thumbnail"""
    import shutil
    from app import api_error, _fix_permissions
    safe_name = secure_filename_util(filename)
    base = Path(__file__).parent.parent.parent
    filepath = base / "uploads" / safe_name
    if not filepath.exists():
        return api_error("Video not found", 404)
    _fix_permissions(base / "uploads")
    filepath.unlink()
    # Try to delete thumbnail with both naming conventions
    stem = Path(safe_name).stem
    new_stem = stem.rsplit('_720p', 1)[0] if '_720p' in stem else stem
    thumbs_dir = base / "uploads" / "thumbs"
    
    # Try new convention first
    thumb = thumbs_dir / f"{new_stem}.jpg"
    if thumb.exists():
        try:
            thumb.unlink()
        except PermissionError:
            pass
    
    # Try old convention
    thumb = thumbs_dir / f"{stem}.jpg"
    if thumb.exists():
        try:
            thumb.unlink()
        except PermissionError:
            pass
    job_dir = base / "jobs" / Path(safe_name).stem
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    return jsonify({"success": True})


@videos_bp.route("/api/thumbnail/<filename>")
def get_thumbnail(filename):
    """Get video thumbnail"""
    from app import api_error
    safe_name = secure_filename_util(filename)
    stem = Path(safe_name).stem
    base = Path(__file__).parent.parent.parent / "uploads" / "thumbs"
    
    # Try new naming convention first (removes _720p suffix if present)
    new_stem = stem.rsplit('_720p', 1)[0] if '_720p' in stem else stem
    thumb_path = base / f"{new_stem}.jpg"
    
    # If not found with new convention, try old convention
    if not thumb_path.exists():
        thumb_path = base / f"{stem}.jpg"
    
    if thumb_path.exists():
        return send_file(thumb_path, mimetype="image/jpeg")
    return api_error("Thumbnail not found", 404)


@videos_bp.route("/api/videos/<filename>/frames")
def get_video_frames_meta(filename):
    """Get frame metadata for a video"""
    video_dir = get_video_directory(filename)
    meta_path = video_dir / "frames_meta.json"
    
    # Also check for frames_index.json (new system may use this)
    if not meta_path.exists():
        index_path = video_dir / "frames_index.json"
        if index_path.exists():
            try:
                with open(index_path, 'r') as f:
                    frames_index = json.load(f)
                frame_count = len(frames_index)
                # Try to get FPS from frames if available
                fps = 1.0
                if frame_count > 0:
                    # Try to get duration from video file if it still exists
                    video_path = Path(__file__).parent.parent.parent / "uploads" / secure_filename_util(filename)
                    if video_path.exists():
                        try:
                            import subprocess
                            probe = subprocess.run(
                                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                                capture_output=True, text=True, timeout=10
                            )
                            if probe.returncode == 0:
                                duration = float(probe.stdout.strip())
                                fps = frame_count / duration if duration > 0 else 1.0
                        except Exception:
                            pass
                return jsonify({"frame_count": frame_count, "fps": fps, "duration": 0})
            except Exception:
                pass
    
    if not meta_path.exists():
        return jsonify({"frame_count": 0, "fps": 0, "duration": 0})
    try:
        return jsonify(json.loads(meta_path.read_text()))
    except Exception:
        return jsonify({"frame_count": 0, "fps": 0, "duration": 0})


@videos_bp.route("/api/videos/<filename>/frames/<int:frame_num>")
def get_video_frame(filename, frame_num):
    from app import api_error
    video_dir = get_video_directory(filename)
    frame_path = video_dir / "frames" / f"frame_{frame_num:06d}.jpg"
    if not frame_path.exists():
        return api_error("Frame not found", 404)
    return send_file(frame_path, mimetype="image/jpeg")


@videos_bp.route("/api/videos/<filename>/frames/<int:frame_num>/thumb")
def get_video_frame_thumb(filename, frame_num):
    from app import api_error
    video_dir = get_video_directory(filename)
    thumb_path = video_dir / "frames" / "thumbs" / f"thumb_{frame_num:06d}.jpg"
    if not thumb_path.exists():
        frame_path = video_dir / "frames" / f"frame_{frame_num:06d}.jpg"
        if frame_path.exists():
            return send_file(frame_path, mimetype="image/jpeg")
        return api_error("Frame not found", 404)
    return send_file(thumb_path, mimetype="image/jpeg")


@videos_bp.route("/api/videos/<filename>/dedup", methods=["POST"])
def run_video_dedup(filename):
    from app import socketio, api_error, _run_dedup, _renumber_frames, _fix_permissions
    from pathlib import Path
    import subprocess
    import json
    import shutil
    
    logger = logging.getLogger(__name__)
    
    safe_name = secure_filename_util(filename)
    stem = Path(safe_name).stem
    base = Path(__file__).parent.parent.parent
    
    video_dir = get_video_directory(filename)
    frames_dir = video_dir / "frames"
    thumbs_dir = frames_dir / "thumbs"

    if not frames_dir.exists() or not any(frames_dir.glob("frame_*.jpg")):
        return api_error(f"No frames found for {filename}. Upload and transcode first.", 400)

    data = request.get_json(silent=True) or {}
    threshold = int(data.get("threshold", 10))
    threshold = max(0, min(threshold, 64))

    fps = 1.0
    duration = 0.0
    meta_path = video_dir / "frames_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            fps = meta.get("fps", 1.0)
            duration = meta.get("duration", 0)
        except Exception:
            pass

    # Restore all frames from backup if available, otherwise work with what's there
    backup_dir = video_dir / "frames_backup"
    if backup_dir.exists() and any(backup_dir.glob("frame_*.jpg")):
        for fp in backup_dir.glob("frame_*.jpg"):
            dest = frames_dir / fp.name
            if not dest.exists():
                fp.rename(dest)
        backup_thumbs = backup_dir / "thumbs"
        if backup_thumbs.exists():
            for tp in backup_thumbs.glob("thumb_*.jpg"):
                dest = thumbs_dir / tp.name
                if not dest.exists():
                    tp.rename(dest)

    # Save a backup of current frames before dedup
    if not backup_dir.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / "thumbs").mkdir(exist_ok=True)
    for fp in frames_dir.glob("frame_*.jpg"):
        dest = backup_dir / fp.name
        if not dest.exists():
            fp.rename(dest)
    for tp in thumbs_dir.glob("thumb_*.jpg"):
        dest = backup_dir / "thumbs" / tp.name
        if not dest.exists():
            tp.rename(dest)

    # Restore all frames from backup
    for fp in sorted(backup_dir.glob("frame_*.jpg")):
        fp.rename(frames_dir / fp.name)
    backup_thumbs = backup_dir / "thumbs"
    if backup_thumbs.exists():
        for tp in sorted(backup_thumbs.glob("thumb_*.jpg")):
            tp.rename(thumbs_dir / tp.name)

    # Check if we have pre-computed dedup results for this threshold
    detailed_results_file = video_dir / "dedup_detailed_results.json"
    if detailed_results_file.exists():
        try:
            detailed_results = json.loads(detailed_results_file.read_text())
            keep_indices_by_threshold = detailed_results.get("keep_indices_by_threshold", {})
            frame_paths = detailed_results.get("frame_paths", [])
            
            # Try both string and integer keys since JSON keys are strings
            threshold_key_str = str(threshold)
            threshold_key_int = threshold
            
            keep_indices = None
            if threshold_key_str in keep_indices_by_threshold:
                keep_indices = keep_indices_by_threshold[threshold_key_str]
            elif threshold_key_int in keep_indices_by_threshold:
                keep_indices = keep_indices_by_threshold[threshold_key_int]
            
            if keep_indices is not None:
                logger.info(f"Using pre-computed dedup results for threshold {threshold}")
                # We have pre-computed results, apply them directly
                keep_indices = keep_indices_by_threshold[str(threshold)]
                
                # Get list of all frame files
                all_frames = sorted(frames_dir.glob("frame_*.jpg"))
                
                # Delete frames not in keep_indices
                frames_to_keep = [all_frames[i] for i in keep_indices]
                frames_to_delete = [f for i, f in enumerate(all_frames) if i not in keep_indices]
                
                # Delete the frames
                for frame_file in frames_to_delete:
                    frame_file.unlink(missing_ok=True)
                    # Also delete corresponding thumbnail if it exists
                    # Frame is named like "frame_000123.jpg", thumbnail is "thumb_000123.jpg"
                    thumb_name = frame_file.name.replace("frame_", "thumb_")
                    thumb_file = thumbs_dir / thumb_name
                    thumb_file.unlink(missing_ok=True)
                
                # Update dedup_results with information
                original_count = len(all_frames)
                deduped_count = len(frames_to_keep)
                dropped = original_count - deduped_count
                pct = round((dropped / original_count) * 100, 1) if original_count > 0 else 0
                
                dedup_results = {
                    "original_count": original_count,
                    "deduped_count": deduped_count,
                    "dropped": dropped,
                    "dropped_pct": pct,
                    "threshold": threshold,
                    "using_precomputed": True
                }
                
                # Now renumber the remaining frames
                frames_index, frame_count = _renumber_frames(frames_dir, thumbs_dir, fps)
                
            else:
                # No pre-computed results for this threshold, compute normally
                logger.info(f"No pre-computed results for threshold {threshold}, computing normally")
                dedup_results = _run_dedup(frames_dir, thumbs_dir, threshold, fps)
                frames_index, frame_count, actual_fps = _renumber_frames(frames_dir, thumbs_dir, fps)
                
        except Exception as e:
            logger.error(f"Error using pre-computed dedup results: {e}, falling back to normal dedup")
            dedup_results = _run_dedup(frames_dir, thumbs_dir, threshold, fps)
            frames_index, frame_count, actual_fps = _renumber_frames(frames_dir, thumbs_dir, fps)
    else:
        # No pre-computed results at all, compute normally
        dedup_results = _run_dedup(frames_dir, thumbs_dir, threshold, fps)
        frames_index, frame_count, actual_fps = _renumber_frames(frames_dir, thumbs_dir, fps)

    index_path = video_dir / "frames_index.json"
    index_path.write_text(json.dumps(frames_index))

    # Use same rounding logic as _transcode_and_delete_with_cleanup
    # Use actual_fps (detected) instead of original fps (might be wrong)
    if actual_fps < 5:
        fps_rounded = round(actual_fps, 1)
    else:
        fps_rounded = round(actual_fps)
    
    # Calculate actual duration from frames_index (last timestamp)
    actual_duration = 0
    if frames_index:
        actual_duration = max(frames_index.values())
    
    meta = {"frame_count": frame_count, "fps": fps_rounded, "duration": actual_duration}
    meta_path.write_text(json.dumps(meta))

    dedup_path = video_dir / "dedup_results.json"
    dedup_path.write_text(json.dumps(dedup_results))

    # Create a new deduped video from the remaining frames
    dedup_stem = f"{stem}_dedup"
    dedup_video_name = f"{dedup_stem}.mp4"
    dedup_video_path = base / "uploads" / dedup_video_name
    dedup_new_dir = base / "uploads" / dedup_stem
    dedup_frames_dir = dedup_new_dir / "frames"
    dedup_thumbs_dir = dedup_frames_dir / "thumbs"

    # Build deduped video from remaining frames
    sorted_frames = sorted(frames_dir.glob("frame_*.jpg"))
    frame_list_file = frames_dir / "dedup_frame_list.txt"
    try:
        with open(frame_list_file, "w") as f:
            for fp in sorted_frames:
                f.write(f"file '{fp}'\n")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(frame_list_file),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-r", str(fps),
            str(dedup_video_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            logger = __import__("logging").getLogger(__name__)
            logger.warning(f"Dedup video creation failed: {proc.stderr[-400:]}")
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.warning(f"Dedup video creation error: {e}")
    finally:
        if frame_list_file.exists():
            frame_list_file.unlink()

    # Copy frames and thumbnails to new video directory
    dedup_frames_dir.mkdir(parents=True, exist_ok=True)
    dedup_thumbs_dir.mkdir(parents=True, exist_ok=True)
    for fp in sorted_frames:
        dest = dedup_frames_dir / fp.name
        if not dest.exists():
            shutil.copy2(fp, dest)
    for tp in thumbs_dir.glob("thumb_*.jpg"):
        dest = dedup_thumbs_dir / tp.name
        if not dest.exists():
            shutil.copy2(tp, dest)

    # Copy transcript if available
    transcript_path = video_dir / "transcript.json"
    if transcript_path.exists():
        shutil.copy2(transcript_path, dedup_new_dir / "transcript.json")

    # Save frames_index and frames_meta for the new video
    (dedup_new_dir / "frames_index.json").write_text(json.dumps(frames_index))
    (dedup_new_dir / "frames_meta.json").write_text(json.dumps(meta))
    (dedup_new_dir / "dedup_results.json").write_text(json.dumps(dedup_results))

    # Ensure thumbnail for new video
    from thumbnail import ensure_thumbnail
    ensure_thumbnail(str(dedup_video_path))

    socketio.emit("videos_updated")
    return jsonify({**dedup_results, "dedup_video": dedup_video_name})


@videos_bp.route("/api/videos/<filename>/dedup-multi", methods=["POST"])
def run_video_dedup_multi(filename):
    """Run deduplication using standalone dedup_worker.py subprocess."""
    import json
    import subprocess
    import tempfile
    from pathlib import Path
    
    from app import api_error
    from src.utils.security import secure_filename as secure_filename_util
    
    logger = logging.getLogger(__name__)
    
    safe_name = secure_filename_util(filename)
    stem = Path(safe_name).stem
    base = Path(__file__).parent.parent.parent
    
    new_stem = stem.rsplit('_720p', 1)[0] if '_720p' in stem else stem
    video_dir = base / "uploads" / new_stem
    frames_dir = video_dir / "frames"
    
    if not frames_dir.exists():
        video_dir = base / "uploads" / stem
        frames_dir = video_dir / "frames"
    
    data = request.get_json(silent=True) or {}
    thresholds = data.get("thresholds", [5, 10, 15, 20, 30])
    thresholds = sorted(set(max(0, min(t, 64)) for t in thresholds))
    
    # Count frames if directory exists
    original_count = 0
    if frames_dir.exists():
        original_count = len(list(frames_dir.glob("frame_*.jpg")))
    
    if original_count == 0:
        return api_error(f"No frames found for {filename}. Upload and transcode first.", 400)
    
    logger.info(f"Running dedup for {filename} with {original_count} frames, thresholds: {thresholds}")
    
    try:
        # Run dedup_worker.py as a subprocess with the frames directory and thresholds
        cmd = ["python3", "dedup_worker.py", str(frames_dir)] + [str(t) for t in thresholds]
        
        logger.info(f"Running dedup command: {' '.join(cmd)}")
        
        # Run with timeout (60 seconds per 1000 frames)
        timeout = max(60, original_count * 0.06)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(base)  # Run from project root so dedup_worker.py can be found
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Dedup failed with unknown error"
            logger.error(f"Dedup failed: {error_msg}")
            return api_error(f"Dedup failed: {error_msg}", 500)
        
        # Parse JSON output from dedup_worker.py
        dedup_results = json.loads(result.stdout)
        
        # Add FPS and duration estimation if available
        meta_path = video_dir / "frames_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                dedup_results["fps"] = meta.get("fps", 30.0)
                dedup_results["duration"] = meta.get("duration", original_count / 30.0)
            except Exception:
                dedup_results["fps"] = 30.0
                dedup_results["duration"] = original_count / 30.0
        
        # Save detailed results for later use by apply button
        results_file = video_dir / "dedup_detailed_results.json"
        results_file.write_text(json.dumps(dedup_results, indent=2))
        logger.info(f"Saved detailed dedup results to {results_file}")
        
        logger.info(f"Dedup completed successfully for {filename}")
        return jsonify(dedup_results)
        
    except subprocess.TimeoutExpired:
        logger.error(f"Dedup timed out after {timeout} seconds for {filename}")
        return api_error(f"Dedup timed out after {timeout} seconds", 504)
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse dedup results: {e}")
        return api_error("Failed to parse dedup results", 500)
        
    except Exception as e:
        logger.error(f"Dedup failed: {e}", exc_info=True)
        return api_error(f"Dedup failed: {str(e)}", 500)

    


@videos_bp.route("/api/videos/<filename>/frames_index")
def get_video_frames_index(filename):
    """Return frames_index.json mapping sequential frame numbers to video timestamps."""
    video_dir = get_video_directory(filename)
    index_path = video_dir / "frames_index.json"
    if not index_path.exists():
        return jsonify({})
    try:
        return jsonify(json.loads(index_path.read_text()))
    except Exception:
        return jsonify({})


@videos_bp.route("/api/videos/<filename>/transcript")
def get_video_transcript(filename):
    video_dir = get_video_directory(filename)
    transcript_path = video_dir / "transcript.json"
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


@videos_bp.route("/api/videos/<filename>/scenes", methods=["GET", "POST"])
def detect_video_scenes(filename):
    """Detect scenes in a video with extracted frames."""
    import time
    import logging
    
    from app import api_error
    
    logger = logging.getLogger(__name__)
    
    video_dir = get_video_directory(filename)
    frames_dir = video_dir / "frames"
    
    if not frames_dir.exists() or not any(frames_dir.glob("frame_*.jpg")):
        return api_error(f"No frames found for {filename}. Upload and transcode first.", 400)
    
    # Get parameters
    data = request.get_json(silent=True) or {}
    detector_type = data.get("detector_type", "content")
    threshold = float(data.get("threshold", 30.0))
    min_scene_len = int(data.get("min_scene_len", 15))
    
    # Get FPS for time calculations
    fps = 1.0
    meta_path = video_dir / "frames_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            fps = meta.get("fps", 1.0)
        except Exception:
            pass
    
    logger.info(f"Scene detection for {filename}: detector={detector_type}, threshold={threshold}")
    
    start_time = time.time()
    
    try:
        # Check if scene detection is available
        try:
            from src.utils.scene_detection import detect_scenes_from_frames, save_scene_info, get_scene_statistics
            from src.utils.scene_detection import integrate_scenes_with_dedup
        except ImportError as e:
            logger.error(f"Scene detection utilities not available: {e}")
            return api_error("Scene detection not available. Please install PySceneDetect.", 501)
        
        # Detect scenes
        scenes = detect_scenes_from_frames(
            frames_dir,
            fps=fps,
            detector_type=detector_type,
            threshold=threshold,
            min_scene_len=min_scene_len
        )
        
        detection_time = time.time() - start_time
        
        # Save scene info
        scene_info_path = video_dir / "scene_info.json"
        save_scene_info(scenes, scene_info_path)
        
        # Get scene statistics
        scene_stats = get_scene_statistics(scenes)
        
        # If requested, also integrate with dedup
        dedup_threshold = data.get("dedup_threshold")
        dedup_results = {}
        if dedup_threshold is not None:
            dedup_start = time.time()
            dedup_results = integrate_scenes_with_dedup(
                frames_dir,
                scenes,
                fps=fps,
                dedup_threshold=int(dedup_threshold),
                use_parallel=data.get("use_parallel", True)
            )
            dedup_time = time.time() - dedup_start
            dedup_results["processing_time"] = dedup_time
        
        response = {
            "video": filename,
            "scenes": [scene.to_dict() for scene in scenes] if hasattr(scenes[0], 'to_dict') else scenes,
            "statistics": scene_stats,
            "detection_time": detection_time,
            "fps": fps,
            "detector_config": {
                "detector_type": detector_type,
                "threshold": threshold,
                "min_scene_len": min_scene_len
            },
            "dedup_integration": dedup_results if dedup_results else None
        }
        
        logger.info(f"Scene detection completed: {len(scenes)} scenes in {detection_time:.2f}s")
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Scene detection failed: {e}", exc_info=True)
        return api_error(f"Scene detection failed: {str(e)}", 500)


@videos_bp.route("/api/videos/<filename>/scene-aware-dedup", methods=["POST"])
def scene_aware_dedup(filename):
    """Perform scene-aware deduplication."""
    import time
    import logging
    
    from app import api_error
    
    logger = logging.getLogger(__name__)
    
    video_dir = get_video_directory(filename)
    frames_dir = video_dir / "frames"
    
    if not frames_dir.exists() or not any(frames_dir.glob("frame_*.jpg")):
        return api_error(f"No frames found for {filename}. Upload and transcode first.", 400)
    
    # Get parameters
    data = request.get_json(silent=True) or {}
    dedup_threshold = int(data.get("threshold", 10))
    scene_detection_threshold = float(data.get("scene_threshold", 30.0))
    min_scene_len = int(data.get("min_scene_len", 15))
    use_parallel = data.get("use_parallel", True)
    
    # Get FPS
    fps = 1.0
    meta_path = video_dir / "frames_meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            fps = meta.get("fps", 1.0)
        except Exception:
            pass
    
    logger.info(f"Scene-aware dedup for {filename}: dedup_threshold={dedup_threshold}, scene_threshold={scene_detection_threshold}")
    
    start_time = time.time()
    
    try:
        # Check if scene detection is available
        try:
            from src.utils.scene_detection import integrate_scenes_with_dedup, detect_scenes_from_frames, save_scene_info
            from src.utils.dedup_scheduler import get_scene_aware_dedup_plan
        except ImportError as e:
            logger.error(f"Scene detection utilities not available: {e}")
            return api_error("Scene detection not available. Please install PySceneDetect.", 501)
        
        # Get scene-aware dedup plan
        plan = get_scene_aware_dedup_plan(
            frames_dir,
            dedup_threshold=dedup_threshold,
            fps=fps,
            available_memory_gb=192,  # System has 192GB RAM
            scene_detection_threshold=scene_detection_threshold
        )
        
        # Perform deduplication
        dedup_start = time.time()
        
        # Detect scenes
        scenes = detect_scenes_from_frames(
            frames_dir,
            fps=fps,
            detector_type="content",
            threshold=scene_detection_threshold,
            min_scene_len=min_scene_len
        )
        
        # Integrate with dedup
        dedup_results = integrate_scenes_with_dedup(
            frames_dir,
            scenes,
            fps=fps,
            dedup_threshold=dedup_threshold,
            use_parallel=use_parallel
        )
        
        dedup_time = time.time() - dedup_start
        total_time = time.time() - start_time
        
        # Save scene info
        scene_info_path = video_dir / "scene_info.json"
        save_scene_info(scenes, scene_info_path)
        
        response = {
            "video": filename,
            "plan": plan,
            "results": dedup_results,
            "performance": {
                "total_time": total_time,
                "dedup_time": dedup_time,
                "scene_detection_time": dedup_start - start_time
            },
            "config": {
                "dedup_threshold": dedup_threshold,
                "scene_threshold": scene_detection_threshold,
                "min_scene_len": min_scene_len,
                "use_parallel": use_parallel,
                "fps": fps
            }
        }
        
        logger.info(f"Scene-aware dedup completed in {total_time:.2f}s")
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Scene-aware dedup failed: {e}", exc_info=True)
        return api_error(f"Scene-aware dedup failed: {str(e)}", 500)
