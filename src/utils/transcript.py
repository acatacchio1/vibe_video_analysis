"""
Transcript loading utilities for consistent path resolution across the application.
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_video_directory_from_path(video_path: Path) -> Path:
    """
    Get the video directory for a given video file path.
    Handles both old and new naming conventions and deduped videos.
    
    Args:
        video_path: Path to video file (e.g., uploads/video_name_720p.mp4)
    
    Returns:
        Path to video directory (e.g., uploads/video_name)
    """
    base = video_path.parent  # Usually 'uploads' directory
    stem = video_path.stem
    
    # Generate candidate directory names in order of priority
    candidates = []
    
    # 1. Original stem (with all suffixes)
    candidates.append(stem)
    
    # 2. Without _720p suffix (if present)
    if '_720p' in stem:
        candidates.append(stem.replace('_720p', ''))
    
    # 3. Without _dedup suffix (if present)
    if '_dedup' in stem:
        candidates.append(stem.replace('_dedup', ''))
    
    # 4. Without both suffixes (if both present)
    if '_720p' in stem and '_dedup' in stem:
        candidates.append(stem.replace('_720p', '').replace('_dedup', ''))
    
    # 5. Special handling: if stem ends with _dedup_720p, try swapping removal order
    if stem.endswith('_dedup_720p'):
        candidates.append(stem.replace('_dedup_720p', ''))
    
    # Remove duplicates while preserving order
    unique_candidates = []
    seen = set()
    for cand in candidates:
        if cand not in seen:
            seen.add(cand)
            unique_candidates.append(cand)
    
    # Try each candidate
    for candidate in unique_candidates:
        video_dir = base / candidate
        if video_dir.exists():
            return video_dir
    
    # If no directory exists yet (video not processed),
    # return the most likely directory based on naming convention
    # Prefer directory without _720p (new convention)
    if '_720p' in stem:
        return base / stem.replace('_720p', '')
    
    return base / stem


def find_transcript_file(video_path: str, video_frames_dir: Optional[str] = None) -> Optional[Path]:
    """
    Find transcript.json file for a video using consistent path resolution.
    
    Args:
        video_path: Path to video file
        video_frames_dir: Optional path to frames directory (for additional search)
    
    Returns:
        Path to transcript.json if found, None otherwise
    """
    video_path_obj = Path(video_path)
    
    # Candidate paths in order of priority
    candidates = []
    
    # 1. Primary: video directory based on video path (handles dedup)
    video_dir = get_video_directory_from_path(video_path_obj)
    candidates.append(video_dir / "transcript.json")
    
    # 2. Alternative: parent of video_frames_dir if provided
    if video_frames_dir:
        frames_dir = Path(video_frames_dir)
        if frames_dir.exists():
            # For frames in uploads/video_name/frames/, parent is uploads/video_name/
            candidates.append(frames_dir.parent / "transcript.json")
            
            # Also check parent of parent for nested structures
            candidates.append(frames_dir.parent.parent / "transcript.json")
    
    # 3. Fallback: original stem directory (with _720p/_dedup if present)
    original_stem_dir = video_path_obj.parent / video_path_obj.stem
    candidates.append(original_stem_dir / "transcript.json")
    
    # 4. Additional fallback: without _dedup suffix
    if '_dedup' in video_path_obj.stem:
        base_stem = video_path_obj.stem.replace('_dedup', '')
        candidates.append(video_path_obj.parent / base_stem / "transcript.json")
    
    # Remove duplicates while preserving order
    unique_candidates = []
    seen = set()
    for cand in candidates:
        if str(cand) not in seen:
            seen.add(str(cand))
            unique_candidates.append(cand)
    
    # Try each candidate
    for transcript_path in unique_candidates:
        if transcript_path.exists():
            logger.info(f"Found transcript at: {transcript_path}")
            return transcript_path
    
    logger.warning(f"No transcript found for {video_path}. Checked locations: {unique_candidates}")
    return None


def load_transcript(video_path: str, video_frames_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Load transcript.json for a video.
    
    Args:
        video_path: Path to video file
        video_frames_dir: Optional path to frames directory
    
    Returns:
        Transcript dictionary if found and valid, None otherwise
    """
    transcript_path = find_transcript_file(video_path, video_frames_dir)
    
    if not transcript_path:
        return None
    
    try:
        transcript_data = json.loads(transcript_path.read_text())
        
        # Validate required structure
        if not isinstance(transcript_data, dict):
            logger.warning(f"Transcript {transcript_path} is not a dictionary")
            return None
        
        # Ensure text field exists (can be empty)
        if "text" not in transcript_data:
            transcript_data["text"] = ""
        
        # Ensure segments field exists
        if "segments" not in transcript_data:
            transcript_data["segments"] = []
        
        logger.info(f"Loaded transcript from {transcript_path}: {len(transcript_data.get('segments', []))} segments")
        return transcript_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse transcript {transcript_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading transcript {transcript_path}: {e}")
        return None


def get_transcript_segments_with_end_times(transcript_data: Dict[str, Any]) -> list:
    """
    Ensure transcript segments have end times and required fields.
    
    Args:
        transcript_data: Transcript dictionary
    
    Returns:
        List of segments with start, end, and text fields
    """
    if not transcript_data or "segments" not in transcript_data:
        return []
    
    segments = transcript_data["segments"]
    if not segments:
        return []
    
    # Validate and clean each segment
    valid_segments = []
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
            
        # Ensure required fields
        segment = seg.copy()
        
        # Add text field if missing
        if "text" not in segment:
            segment["text"] = ""
        
        # Add start time if missing
        if "start" not in segment:
            segment["start"] = 0
        
        # Add end time if missing
        if "end" not in segment:
            # Use next segment's start time, or start + 5 seconds
            if i + 1 < len(segments) and "start" in segments[i + 1]:
                segment["end"] = segments[i + 1]["start"]
            else:
                segment["end"] = segment["start"] + 5.0
        
        valid_segments.append(segment)
    
    return valid_segments