#!/usr/bin/env python3
path = "/home/anthony/video-analyzer-web/src/api/videos.py"
content = open(path).read()

# We know the delete_video block starts at line 128 and ends at line 163.
# Let's find the exact start and replace the whole block.
import re

# Add _delete_one_video helper before list_videos
old_list = '''@videos_bp.route("/api/videos")
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
    return jsonify(videos)'''

assert old_list in content

new_list = '''def _delete_one_video(filepath: Path, base: Path):
    """Helper: delete a single video file, its thumbnails, its data directory, and job dir."""
    import shutil
    from app import _fix_permissions
    _fix_permissions(base / "uploads")
    stem = filepath.stem
    is_processed = stem.endswith("_dedup")

    # Delete the video file
    if filepath.exists():
        filepath.unlink()

    # Thumbnails
    thumbs_dir = base / "uploads" / "thumbs"
    new_stem = stem.rsplit('_720p', 1)[0] if '_720p' in stem else stem
    for thumb in [thumbs_dir / f"{new_stem}.jpg", thumbs_dir / f"{stem}.jpg"]:
        if thumb.exists():
            try:
                thumb.unlink()
            except PermissionError:
                pass

    # Data directory (same logic as get_video_directory, but skip _720p for source)
    dir_stem = new_stem if not is_processed else stem
    video_dir = base / "uploads" / dir_stem
    if video_dir.exists():
        shutil.rmtree(video_dir, ignore_errors=True)

    # Also try the exact stem directory (for processed videos and edge cases)
    exact_dir = base / "uploads" / stem
    if exact_dir.exists() and exact_dir != video_dir:
        shutil.rmtree(exact_dir, ignore_errors=True)

    # Job directory
    job_dir = base / "jobs" / stem
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    return {"success": True}


@videos_bp.route("/api/videos")
def list_videos():
    """List uploaded videos with metadata, categorized into processed and source."""
    from app import api_error
    upload_dir = Path(__file__).parent.parent.parent / "uploads"
    video_files = [
        f for f in upload_dir.glob("*")
        if f.is_file() and f.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    ]

    processed_files = [f for f in video_files if f.stem.endswith("_dedup")]
    source_files = [f for f in video_files if not f.stem.endswith("_dedup")]

    def _build_video_list(files):
        if not files:
            return []
        video_paths = [str(f) for f in files]
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
        return videos

    return jsonify({
        "processed_videos": _build_video_list(processed_files),
        "source_videos": _build_video_list(source_files),
    })'''

content = content.replace(old_list, new_list)

# Add bulk delete endpoints before upload_video
old_upload = '''@videos_bp.route("/api/videos/upload", methods=["POST"])
def upload_video():'''
assert old_upload in content
new_upload = '''@videos_bp.route("/api/videos/source/all", methods=["DELETE"])
def delete_all_source_videos():
    """Delete all source videos (original uploads) and their extracted data."""
    import logging
    base = Path(__file__).parent.parent.parent
    upload_dir = base / "uploads"
    logger = logging.getLogger(__name__)

    deleted_count = 0
    failed = []

    for filepath in upload_dir.glob("*"):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
            continue
        if filepath.stem.endswith("_dedup"):
            continue
        try:
            _delete_one_video(filepath, base)
            deleted_count += 1
        except Exception as e:
            logger.warning(f"Failed to delete {filepath.name}: {e}")
            failed.append(f"{filepath.name}: {str(e)}")

    logger.info(f"Bulk deleted {deleted_count} source videos")
    return jsonify({"success": True, "deleted": deleted_count, "failed": failed})


@videos_bp.route("/api/videos/processed/all", methods=["DELETE"])
def delete_all_processed_videos():
    """Delete all processed (_dedup) videos and their associated data."""
    import logging
    base = Path(__file__).parent.parent.parent
    upload_dir = base / "uploads"
    logger = logging.getLogger(__name__)

    deleted_count = 0
    failed = []

    for filepath in upload_dir.glob("*"):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
            continue
        if not filepath.stem.endswith("_dedup"):
            continue
        try:
            _delete_one_video(filepath, base)
            deleted_count += 1
        except Exception as e:
            logger.warning(f"Failed to delete {filepath.name}: {e}")
            failed.append(f"{filepath.name}: {str(e)}")

    logger.info(f"Bulk deleted {deleted_count} processed videos")
    return jsonify({"success": True, "deleted": deleted_count, "failed": failed})


@videos_bp.route("/api/videos/upload", methods=["POST"])
def upload_video():'''

content = content.replace(old_upload, new_upload)

# Replace single delete_video
old_del = """@videos_bp.route("/api/videos", methods=["DELETE"])
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
    return jsonify({"success": True})"""

if old_del not in content:
    # actual file uses /api/videos as route path
    old_del = """@videos_bp.route("/api/videos", methods=["DELETE"])
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
    return jsonify({"success": True})"""
assert old_del in content
new_del = '''@videos_bp.route("/api/videos", methods=["DELETE"])
def delete_video(filename):
    """Delete a single video and all its associated data."""
    from app import api_error
    base = Path(__file__).parent.parent.parent
    filepath = base / "uploads" / secure_filename_util(filename)
    if not filepath.exists():
        return api_error("Video not found", 404)
    _delete_one_video(filepath, base)
    return jsonify({"success": True})'''

content = content.replace(old_del, new_del)

open(path, "w").write(content)
print("done")
