#!/usr/bin/env python3
"""
Scene detection utilities using PySceneDetect.
Integrates with existing parallel deduplication system.

Key Features:
- Scene detection with adaptive thresholding
- Scene-based frame grouping for smarter deduplication
- Parallel scene processing for performance
- Integration with existing dedup pipeline
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass, asdict
import concurrent.futures

# Optional PySceneDetect import
PYSSCENEDETECT_AVAILABLE = False
logger = logging.getLogger(__name__)

try:
    # First check if OpenCV is available
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    logger.warning("OpenCV not available, PySceneDetect will not work")

if HAS_OPENCV:
    try:
        from scenedetect import VideoManager, SceneManager, ContentDetector, AdaptiveDetector
        from scenedetect import StatsManager, open_video, split_video_ffmpeg
        from scenedetect.scene_detector import SceneDetector
        from scenedetect.frame_timecode import FrameTimecode
        PYSSCENEDETECT_AVAILABLE = True
        logger.info("PySceneDetect loaded successfully")
    except ImportError as e:
        logger.warning(f"PySceneDetect not available: {e}")
else:
    logger.warning("OpenCV not available, PySceneDetect cannot be loaded")


@dataclass
class SceneInfo:
    """Information about a detected scene."""
    scene_id: int
    start_frame: int
    end_frame: int
    start_time: float  # seconds
    end_time: float    # seconds
    duration: float    # seconds
    frame_count: int
    scene_type: str = "content"  # content, transition, etc.
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


def detect_scenes_video(
    video_path: Union[str, Path],
    detector_type: str = "content",
    threshold: float = 30.0,
    min_scene_len: int = 15,
    window_width: int = 2,
    **kwargs
) -> List[SceneInfo]:
    """
    Detect scenes in a video file using PySceneDetect.
    
    Args:
        video_path: Path to video file
        detector_type: "content" (threshold-based) or "adaptive" (adaptive thresholding)
        threshold: Detection threshold (0-100)
        min_scene_len: Minimum scene length in frames
        window_width: Window size for adaptive detector
        **kwargs: Additional detector parameters
    
    Returns:
        List of SceneInfo objects
    """
    if not PYSSCENEDETECT_AVAILABLE:
        logger.warning("PySceneDetect not available, returning empty scene list")
        return []
    
    video_path = Path(video_path)
    if not video_path.exists():
        logger.error(f"Video file not found: {video_path}")
        return []
    
    logger.info(f"Detecting scenes in {video_path.name} (detector={detector_type}, threshold={threshold})")
    
    scenes = []
    start_time = time.time()
    
    try:
        # Create video manager
        video_manager = VideoManager([str(video_path)])
        
        # Create scene manager
        scene_manager = SceneManager()
        
        # Choose detector
        if detector_type.lower() == "adaptive":
            detector = AdaptiveDetector(
                adaptive_threshold=threshold,
                min_scene_len=min_scene_len,
                window_width=window_width,
                **kwargs
            )
        else:  # Default to content detector
            detector = ContentDetector(
                threshold=threshold,
                min_scene_len=min_scene_len,
                **kwargs
            )
        
        # Add detector to scene manager
        scene_manager.add_detector(detector)
        
        # Set downscale factor for faster processing (optional)
        video_manager.set_downscale_factor()
        
        # Start video manager
        video_manager.start()
        
        # Detect scenes
        scene_manager.detect_scenes(frame_source=video_manager)
        
        # Get scene list
        scene_list = scene_manager.get_scene_list()
        
        # Convert to SceneInfo objects
        for i, (start_timecode, end_timecode) in enumerate(scene_list):
            start_frame = start_timecode.get_frames()
            end_frame = end_timecode.get_frames()
            start_seconds = start_timecode.get_seconds()
            end_seconds = end_timecode.get_seconds()
            
            scene = SceneInfo(
                scene_id=i + 1,
                start_frame=start_frame,
                end_frame=end_frame,
                start_time=start_seconds,
                end_time=end_seconds,
                duration=end_seconds - start_seconds,
                frame_count=end_frame - start_frame + 1,
                scene_type="content",
                confidence=1.0  # PySceneDetect doesn't provide confidence scores
            )
            scenes.append(scene)
        
        detection_time = time.time() - start_time
        logger.info(f"Detected {len(scenes)} scenes in {detection_time:.2f}s")
        
        return scenes
        
    except Exception as e:
        logger.error(f"Scene detection failed: {e}", exc_info=True)
        return []


def detect_scenes_from_frames(
    frames_dir: Union[str, Path],
    fps: float = 30.0,
    detector_type: str = "content",
    threshold: float = 30.0,
    min_scene_len: int = 15,
    **kwargs
) -> List[SceneInfo]:
    """
    Detect scenes from extracted frames (alternative to video-based detection).
    
    Args:
        frames_dir: Directory containing frame images
        fps: Frames per second for time calculations
        detector_type: "content" or "adaptive"
        threshold: Detection threshold
        min_scene_len: Minimum scene length in frames
        **kwargs: Additional parameters
    
    Returns:
        List of SceneInfo objects
    """
    frames_dir = Path(frames_dir)
    if not frames_dir.exists():
        logger.error(f"Frames directory not found: {frames_dir}")
        return []
    
    # Get frame files
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    if not frame_files:
        logger.error(f"No frames found in {frames_dir}")
        return []
    
    logger.info(f"Detecting scenes from {len(frame_files)} frames (fps={fps})")
    
    # For now, use a simplified approach: group frames into scenes
    # based on perceptual hash similarity
    # TODO: Implement proper frame-based scene detection
    
    # Fallback: treat entire video as one scene
    scenes = [
        SceneInfo(
            scene_id=1,
            start_frame=1,
            end_frame=len(frame_files),
            start_time=0.0,
            end_time=len(frame_files) / fps,
            duration=len(frame_files) / fps,
            frame_count=len(frame_files),
            scene_type="content",
            confidence=1.0
        )
    ]
    
    logger.info(f"Created {len(scenes)} scene(s) from frames")
    return scenes


def group_frames_by_scene(
    frame_files: List[Path],
    scenes: List[SceneInfo],
    fps: float = 30.0
) -> Dict[int, List[Path]]:
    """
    Group frame files by scene.
    
    Args:
        frame_files: Sorted list of frame file paths
        scenes: List of detected scenes
        fps: Frames per second
    
    Returns:
        Dictionary mapping scene_id to list of frame paths
    """
    if not scenes:
        # No scenes detected, treat all frames as one scene
        return {1: frame_files}
    
    scene_groups = {}
    
    for scene in scenes:
        scene_frames = []
        start_idx = max(0, scene.start_frame - 1)  # Convert to 0-based
        end_idx = min(len(frame_files), scene.end_frame)  # end_frame is inclusive
        
        for i in range(start_idx, end_idx):
            if i < len(frame_files):
                scene_frames.append(frame_files[i])
        
        if scene_frames:
            scene_groups[scene.scene_id] = scene_frames
            logger.debug(f"Scene {scene.scene_id}: {len(scene_frames)} frames")
    
    return scene_groups


def save_scene_info(scenes: List[SceneInfo], output_path: Union[str, Path]) -> bool:
    """Save scene information to JSON file."""
    try:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        scenes_dict = [scene.to_dict() for scene in scenes]
        output_path.write_text(json.dumps(scenes_dict, indent=2))
        
        logger.info(f"Saved scene info to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save scene info: {e}")
        return False


def load_scene_info(scene_info_path: Union[str, Path]) -> List[SceneInfo]:
    """Load scene information from JSON file."""
    try:
        scene_info_path = Path(scene_info_path)
        if not scene_info_path.exists():
            logger.warning(f"Scene info file not found: {scene_info_path}")
            return []
        
        scenes_dict = json.loads(scene_info_path.read_text())
        scenes = []
        
        for scene_dict in scenes_dict:
            scene = SceneInfo(**scene_dict)
            scenes.append(scene)
        
        logger.info(f"Loaded {len(scenes)} scenes from {scene_info_path}")
        return scenes
        
    except Exception as e:
        logger.error(f"Failed to load scene info: {e}")
        return []


def detect_scenes_parallel(
    video_paths: List[Union[str, Path]],
    detector_type: str = "content",
    threshold: float = 30.0,
    max_workers: int = None,
    **kwargs
) -> Dict[str, List[SceneInfo]]:
    """
    Detect scenes in multiple videos in parallel.
    
    Args:
        video_paths: List of video file paths
        detector_type: Detector type
        threshold: Detection threshold
        max_workers: Maximum number of parallel workers
        **kwargs: Additional parameters
    
    Returns:
        Dictionary mapping video path to list of scenes
    """
    if not PYSSCENEDETECT_AVAILABLE:
        logger.warning("PySceneDetect not available, returning empty results")
        return {}
    
    if max_workers is None:
        import multiprocessing
        max_workers = min(multiprocessing.cpu_count() - 2, len(video_paths))
    
    logger.info(f"Detecting scenes in {len(video_paths)} videos with {max_workers} workers")
    
    results = {}
    start_time = time.time()
    
    def process_video(video_path):
        """Process a single video."""
        video_path = Path(video_path)
        try:
            scenes = detect_scenes_video(
                video_path,
                detector_type=detector_type,
                threshold=threshold,
                **kwargs
            )
            return str(video_path), scenes
        except Exception as e:
            logger.error(f"Failed to process {video_path}: {e}")
            return str(video_path), []
    
    # Process videos in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_video = {
            executor.submit(process_video, video_path): video_path 
            for video_path in video_paths
        }
        
        for future in concurrent.futures.as_completed(future_to_video):
            video_path, scenes = future.result()
            results[video_path] = scenes
            logger.info(f"Processed {Path(video_path).name}: {len(scenes)} scenes")
    
    total_time = time.time() - start_time
    logger.info(f"Parallel scene detection completed in {total_time:.2f}s")
    
    return results


def get_scene_statistics(scenes: List[SceneInfo]) -> Dict[str, Any]:
    """Calculate statistics for detected scenes."""
    if not scenes:
        return {}
    
    total_frames = sum(scene.frame_count for scene in scenes)
    total_duration = sum(scene.duration for scene in scenes)
    
    scene_durations = [scene.duration for scene in scenes]
    scene_frame_counts = [scene.frame_count for scene in scenes]
    
    return {
        "total_scenes": len(scenes),
        "total_frames": total_frames,
        "total_duration": total_duration,
        "avg_scene_duration": total_duration / len(scenes) if scenes else 0,
        "avg_scene_frames": total_frames / len(scenes) if scenes else 0,
        "min_scene_duration": min(scene_durations) if scene_durations else 0,
        "max_scene_duration": max(scene_durations) if scene_durations else 0,
        "min_scene_frames": min(scene_frame_counts) if scene_frame_counts else 0,
        "max_scene_frames": max(scene_frame_counts) if scene_frame_counts else 0,
    }


def integrate_scenes_with_dedup(
    frames_dir: Union[str, Path],
    scenes: List[SceneInfo],
    fps: float = 30.0,
    dedup_threshold: int = 10,
    use_parallel: bool = True
) -> Dict[str, Any]:
    """
    Integrate scene detection with deduplication.
    Performs deduplication within each scene separately.
    
    Args:
        frames_dir: Directory containing frames
        scenes: Detected scenes
        fps: Frames per second
        dedup_threshold: Deduplication threshold
        use_parallel: Use parallel deduplication
    
    Returns:
        Dictionary with deduplication results per scene
    """
    from src.utils.parallel_hash import compute_hashes_parallel
    from PIL import Image
    import imagehash
    
    frames_dir = Path(frames_dir)
    frame_files = sorted(frames_dir.glob("frame_*.jpg"))
    
    if not frame_files:
        logger.error(f"No frames found in {frames_dir}")
        return {}
    
    if not scenes:
        # No scenes detected, treat all frames as one scene
        scenes = [
            SceneInfo(
                scene_id=1,
                start_frame=1,
                end_frame=len(frame_files),
                start_time=0.0,
                end_time=len(frame_files) / fps,
                duration=len(frame_files) / fps,
                frame_count=len(frame_files),
                scene_type="content",
                confidence=1.0
            )
        ]
    
    logger.info(f"Integrating {len(scenes)} scenes with deduplication")
    
    # Group frames by scene
    scene_groups = group_frames_by_scene(frame_files, scenes, fps)
    
    results = {
        "total_scenes": len(scene_groups),
        "scenes": {},
        "overall_statistics": {
            "original_frames": len(frame_files),
            "total_deduped_frames": 0,
            "total_removed_frames": 0
        }
    }
    
    # Process each scene
    for scene_id, scene_frames in scene_groups.items():
        if not scene_frames:
            continue
        
        logger.info(f"Processing scene {scene_id}: {len(scene_frames)} frames")
        
        # Compute hashes for this scene
        try:
            if use_parallel and len(scene_frames) > 50:
                # Use parallel hash computation for larger scenes
                hash_results = compute_hashes_parallel(
                    scene_frames,
                    max_workers=min(8, len(scene_frames) // 10),
                    chunk_size=100
                )
                
                # Extract hashes in order
                hashes = []
                for fp in scene_frames:
                    if fp in hash_results:
                        phash, _ = hash_results[fp]
                        hashes.append(phash)
                    else:
                        # Fallback
                        hashes.append(imagehash.phash(Image.open(fp)))
            else:
                # Sequential hash computation
                hashes = [imagehash.phash(Image.open(fp)) for fp in scene_frames]
            
            # Run deduplication within scene
            keep_indices = [0]  # Always keep first frame
            prev_hash = hashes[0]
            
            for i in range(1, len(hashes)):
                if (prev_hash - hashes[i]) >= dedup_threshold:
                    keep_indices.append(i)
                    prev_hash = hashes[i]
            
            # Calculate scene statistics
            original_count = len(scene_frames)
            deduped_count = len(keep_indices)
            removed_count = original_count - deduped_count
            removed_pct = (removed_count / original_count * 100) if original_count > 0 else 0
            
            # Store results for this scene
            results["scenes"][scene_id] = {
                "scene_id": scene_id,
                "original_frames": original_count,
                "deduped_frames": deduped_count,
                "removed_frames": removed_count,
                "removed_percentage": removed_pct,
                "keep_indices": keep_indices
            }
            
            # Update overall statistics
            results["overall_statistics"]["total_deduped_frames"] += deduped_count
            results["overall_statistics"]["total_removed_frames"] += removed_count
            
            logger.info(f"Scene {scene_id}: {removed_count}/{original_count} frames removed ({removed_pct:.1f}%)")
            
        except Exception as e:
            logger.error(f"Failed to process scene {scene_id}: {e}")
            # Keep all frames in case of error
            results["scenes"][scene_id] = {
                "scene_id": scene_id,
                "original_frames": len(scene_frames),
                "deduped_frames": len(scene_frames),
                "removed_frames": 0,
                "removed_percentage": 0.0,
                "keep_indices": list(range(len(scene_frames))),
                "error": str(e)
            }
            results["overall_statistics"]["total_deduped_frames"] += len(scene_frames)
    
    # Calculate overall percentages
    total_original = results["overall_statistics"]["original_frames"]
    total_removed = results["overall_statistics"]["total_removed_frames"]
    total_deduped = results["overall_statistics"]["total_deduped_frames"]
    
    results["overall_statistics"]["removed_percentage"] = (
        total_removed / total_original * 100 if total_original > 0 else 0
    )
    results["overall_statistics"]["deduped_percentage"] = (
        total_deduped / total_original * 100 if total_original > 0 else 0
    )
    
    logger.info(f"Overall: {total_removed}/{total_original} frames removed ({results['overall_statistics']['removed_percentage']:.1f}%)")
    
    return results