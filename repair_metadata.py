#!/usr/bin/env python3
"""
Repair video metadata (frames_meta.json) by detecting correct FPS from frame files.
"""
import json
import logging
from pathlib import Path
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def detect_video_fps_from_frames(frames_dir: Path) -> float:
    """
    Detect original video FPS from frame file numbers.
    Returns estimated FPS or 1.0 if undetectable.
    """
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if not frames:
        return 1.0
    
    # Get frame numbers
    frame_nums = []
    for frame in frames:
        try:
            frame_num = int(frame.stem.split("_")[1])
            frame_nums.append(frame_num)
        except (ValueError, IndexError):
            continue
    
    if not frame_nums:
        return 1.0
    
    max_frame = max(frame_nums)
    frame_count = len(frame_nums)
    
    # If frames are sequential (1, 2, 3...), they're likely 1fps extraction
    # If frame numbers are large and non-sequential, they're likely original FPS
    if max_frame <= frame_count * 2:
        return 1.0  # Likely 1fps extraction
    
    # Try to estimate FPS based on typical video durations
    # Common durations in seconds: 30, 60, 120, 300, 600, 1800, 3600
    common_durations = [30, 60, 120, 300, 420, 600, 900, 1800, 3600, 7200]
    common_fps = [23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0]
    
    best_fps = 1.0
    best_error = float('inf')
    
    for duration in common_durations:
        for fps in common_fps:
            expected_frames = duration * fps
            error = abs(max_frame - expected_frames) / expected_frames
            
            if error < best_error and error < 0.5:  # Within 50%
                best_error = error
                best_fps = fps
    
    if best_fps == 1.0:
        logger.warning(f"Could not detect FPS for {frames_dir.parent.name}, max frame={max_frame}, frame count={frame_count}")
    
    return best_fps

def repair_video_metadata(video_dir: Path):
    """Repair frames_meta.json for a video directory."""
    meta_path = video_dir / "frames_meta.json"
    frames_dir = video_dir / "frames"
    
    if not meta_path.exists():
        logger.error(f"No metadata file: {meta_path}")
        return False
    
    if not frames_dir.exists():
        logger.error(f"No frames directory: {frames_dir}")
        return False
    
    try:
        # Load current metadata
        with open(meta_path) as f:
            meta = json.load(f)
        
        current_fps = meta.get("fps", 1.0)
        detected_fps = detect_video_fps_from_frames(frames_dir)
        
        if abs(current_fps - detected_fps) > 0.1:  # Significant difference
            logger.info(f"Repairing {video_dir.name}: fps {current_fps} -> {detected_fps}")
            meta["fps"] = detected_fps
            
            # Also fix duration if it's 0.0 or wrong
            if meta.get("duration", 0) == 0 and detected_fps > 1.0:
                frames = sorted(frames_dir.glob("frame_*.jpg"))
                if frames:
                    # Get max frame number
                    max_frame = 0
                    for frame in frames:
                        try:
                            frame_num = int(frame.stem.split("_")[1])
                            max_frame = max(max_frame, frame_num)
                        except (ValueError, IndexError):
                            continue
                    
                    if max_frame > 0:
                        estimated_duration = max_frame / detected_fps
                        meta["duration"] = round(estimated_duration, 3)
            
            # Save repaired metadata
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
            
            return True
    
    except Exception as e:
        logger.error(f"Error repairing {video_dir.name}: {e}")
    
    return False

def main():
    """Repair metadata for all videos in uploads directory."""
    uploads_dir = Path("uploads")
    
    if not uploads_dir.exists():
        logger.error("Uploads directory not found")
        return
    
    repaired = 0
    total = 0
    
    for video_dir in uploads_dir.iterdir():
        if video_dir.is_dir():
            total += 1
            if repair_video_metadata(video_dir):
                repaired += 1
    
    logger.info(f"Repaired {repaired} of {total} video metadata files")
    
    # Also check deduped videos
    dedup_repaired = 0
    dedup_total = 0
    
    for video_dir in uploads_dir.iterdir():
        if video_dir.is_dir() and "_dedup" in video_dir.name:
            dedup_total += 1
            if repair_video_metadata(video_dir):
                dedup_repaired += 1
    
    logger.info(f"Repaired {dedup_repaired} of {dedup_total} deduped video metadata files")

if __name__ == "__main__":
    main()