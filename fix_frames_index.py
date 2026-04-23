#!/usr/bin/env python3
"""
Fix existing frames_index.json files by converting frame numbers to seconds.
"""
import json
import logging
from pathlib import Path
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def detect_fps_for_index(frames_index: dict) -> float:
    """
    Detect FPS from frames_index values (which might be in frame numbers).
    Returns estimated FPS or 29.97 default.
    """
    if not frames_index:
        return 29.97
    
    # Get max timestamp
    max_ts = max(frames_index.values())
    
    # If max timestamp < 3600 (1 hour), likely already in seconds
    if max_ts < 3600:
        return 29.97  # Can't detect from seconds
    
    # Try to detect FPS from typical video durations
    common_fps = [23.976, 24.0, 25.0, 29.97, 30.0]
    common_durations = [30, 60, 120, 300, 420, 600, 900, 1800, 3600]
    
    best_fps = 29.97
    best_error = float('inf')
    
    for fps in common_fps:
        for duration in common_durations:
            expected_max_frames = duration * fps
            error = abs(max_ts - expected_max_frames) / expected_max_frames
            
            if error < best_error and error < 0.3:  # Within 30%
                best_error = error
                best_fps = fps
    
    logger.info(f"Detected FPS {best_fps} from max timestamp {max_ts}")
    return best_fps

def fix_frames_index(video_dir: Path) -> bool:
    """Fix frames_index.json for a video directory."""
    index_path = video_dir / "frames_index.json"
    meta_path = video_dir / "frames_meta.json"
    
    if not index_path.exists():
        return False
    
    try:
        # Load current index
        with open(index_path) as f:
            frames_index = json.load(f)
        
        # Check if needs fixing
        max_ts = max(frames_index.values()) if frames_index else 0
        
        # If max timestamp > 1000, likely in frame numbers (videos rarely > 1000s)
        if max_ts > 1000:
            logger.info(f"Fixing {video_dir.name}: timestamps appear to be frame numbers (max={max_ts})")
            
            # Detect FPS
            detected_fps = detect_fps_for_index(frames_index)
            
            # Convert frame numbers to seconds
            fixed_index = {}
            for frame_num, frame_ts in frames_index.items():
                seconds = frame_ts / detected_fps
                fixed_index[frame_num] = round(seconds, 3)
            
            # Save fixed index
            with open(index_path, 'w') as f:
                json.dump(fixed_index, f)
            
            # Also update metadata if exists
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)
                
                # Update FPS in metadata if wrong
                current_fps = meta.get("fps", 1.0)
                if abs(current_fps - detected_fps) > 0.1:
                    meta["fps"] = detected_fps
                    # Update duration
                    meta["duration"] = round(max(fixed_index.values()), 3)
                    
                    with open(meta_path, 'w') as f:
                        json.dump(meta, f)
                    
                    logger.info(f"Updated metadata: fps {current_fps} -> {detected_fps}")
            
            return True
        
        else:
            logger.debug(f"{video_dir.name}: timestamps already in seconds (max={max_ts}s)")
            return False
    
    except Exception as e:
        logger.error(f"Error fixing {video_dir.name}: {e}")
    
    return False

def main():
    """Fix frames_index.json for all videos in uploads directory."""
    uploads_dir = Path("uploads")
    
    if not uploads_dir.exists():
        logger.error("Uploads directory not found")
        return
    
    fixed = 0
    total = 0
    
    for video_dir in uploads_dir.iterdir():
        if video_dir.is_dir():
            total += 1
            if fix_frames_index(video_dir):
                fixed += 1
    
    logger.info(f"Fixed {fixed} of {total} frames_index.json files")

if __name__ == "__main__":
    main()