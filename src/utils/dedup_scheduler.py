#!/usr/bin/env python3
"""
Smart scheduler for deduplication strategy selection.
Determines optimal approach (parallel vs sequential) based on video characteristics.

Enhanced with scene-aware scheduling for better performance.
"""

import multiprocessing
import logging
import math
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Optional scene detection import
try:
    from src.utils.scene_detection import SceneInfo, detect_scenes_from_frames, group_frames_by_scene
    SCENE_DETECTION_AVAILABLE = True
except ImportError:
    SCENE_DETECTION_AVAILABLE = False


def should_use_parallel(frame_count: int, dedup_threshold: int, video_duration: float = 0) -> bool:
    """
    Determine if parallel processing is beneficial.
    
    Args:
        frame_count: Number of frames to process
        dedup_threshold: Deduplication threshold value
        video_duration: Video duration in seconds (optional)
        
    Returns:
        True if parallel processing is recommended
    """
    # Very small videos: sequential is faster (overhead dominates)
    if frame_count < 10:
        logger.debug(f"Sequential recommended: Only {frame_count} frames")
        return False
    
    # Very high thresholds: few comparisons needed
    if dedup_threshold >= 60 and frame_count < 100:
        logger.debug(f"Sequential recommended: High threshold ({dedup_threshold}) "
                    f"with only {frame_count} frames")
        return False
    
    # Very short videos with few frames
    if video_duration > 0 and video_duration < 5 and frame_count < 50:
        logger.debug(f"Sequential recommended: Short video ({video_duration}s)")
        return False
    
    # Default: use parallel for everything else
    logger.debug(f"Parallel recommended: {frame_count} frames, threshold={dedup_threshold}")
    return True


def get_optimal_worker_count(frame_count: int, available_cores: int = None) -> int:
    """
    Calculate optimal number of worker processes.
    
    Args:
        frame_count: Number of frames to process
        available_cores: Available CPU cores (default: system count)
        
    Returns:
        Optimal worker count
    """
    if available_cores is None:
        available_cores = multiprocessing.cpu_count()
    
    # All but 2 cores for large workloads
    max_workers = max(1, available_cores - 2)
    
    if frame_count < 50:
        # Very small: minimize overhead
        optimal = max(1, min(2, frame_count // 5 + 1))
        logger.debug(f"Small workload ({frame_count} frames): Using {optimal} workers")
        
    elif frame_count < 200:
        # Small: scale gradually
        optimal = max(2, min(max_workers // 2, frame_count // 20 + 2))
        logger.debug(f"Medium workload ({frame_count} frames): Using {optimal} workers")
        
    elif frame_count < 1000:
        # Medium: use more workers
        optimal = max(4, min(max_workers, frame_count // 50 + 4))
        logger.debug(f"Large workload ({frame_count} frames): Using {optimal} workers")
        
    else:
        # Large: use maximum workers
        optimal = max_workers
        logger.debug(f"Very large workload ({frame_count} frames): Using {optimal} workers (max)")
    
    return optimal


def estimate_memory_requirements(
    frame_count: int, 
    frame_resolution: tuple = (1920, 1080),
    frame_size_kb: int = None
) -> Dict[str, float]:
    """
    Estimate memory requirements for deduplication.
    
    Args:
        frame_count: Number of frames
        frame_resolution: Frame resolution (width, height)
        frame_size_kb: Average frame size in KB (if known)
        
    Returns:
        Dictionary with memory estimates in GB
    """
    if frame_size_kb is None:
        # Estimate based on resolution
        width, height = frame_resolution
        pixels = width * height
        # Rough estimate: 0.5 bytes per pixel for compressed JPEG
        frame_size_kb = max(50, pixels * 0.5 / 1024)
    
    # Images in memory
    image_memory_gb = (frame_count * frame_size_kb) / 1024 / 1024
    
    # Hash storage (negligible)
    hash_memory_gb = (frame_count * 64 / 8) / 1024 / 1024 / 1024  # 64-bit hashes
    
    # Process overhead
    worker_count = get_optimal_worker_count(frame_count)
    process_memory_gb = worker_count * 0.05  # ~50MB per process
    
    # Total estimate
    total_memory_gb = image_memory_gb + hash_memory_gb + process_memory_gb + 0.5  # +0.5GB buffer
    
    estimates = {
        "image_memory_gb": round(image_memory_gb, 2),
        "hash_memory_gb": round(hash_memory_gb, 4),
        "process_memory_gb": round(process_memory_gb, 2),
        "buffer_gb": 0.5,
        "total_gb": round(total_memory_gb, 2),
        "worker_count": worker_count,
        "frame_count": frame_count
    }
    
    logger.info(f"Memory estimates for {frame_count} frames:")
    logger.info(f"  Image data: {estimates['image_memory_gb']} GB")
    logger.info(f"  Process overhead: {estimates['process_memory_gb']} GB")
    logger.info(f"  Total estimate: {estimates['total_gb']} GB")
    
    return estimates


def check_memory_safety(estimated_memory_gb: float, available_memory_gb: float = 192) -> bool:
    """
    Check if memory usage is within safe limits.
    
    Args:
        estimated_memory_gb: Estimated memory requirement
        available_memory_gb: Available system memory
        
    Returns:
        True if memory usage is safe
    """
    safety_threshold = available_memory_gb * 0.75  # Use max 75% of available
    
    if estimated_memory_gb > safety_threshold:
        logger.warning(f"Memory estimate ({estimated_memory_gb} GB) exceeds "
                      f"75% of available ({available_memory_gb} GB)")
        return False
    
    if estimated_memory_gb > available_memory_gb:
        logger.error(f"Memory estimate ({estimated_memory_gb} GB) exceeds "
                    f"available memory ({available_memory_gb} GB)")
        return False
    
    logger.debug(f"Memory safe: {estimated_memory_gb} GB <= {safety_threshold} GB (75% of available)")
    return True


def get_dedup_strategy(
    frame_count: int,
    dedup_threshold: int,
    video_duration: float = 0,
    available_memory_gb: float = 192
) -> Dict[str, Any]:
    """
    Determine optimal deduplication strategy.
    
    Args:
        frame_count: Number of frames
        dedup_threshold: Deduplication threshold
        video_duration: Video duration in seconds
        available_memory_gb: Available system memory
        
    Returns:
        Dictionary with strategy recommendations
    """
    strategy = {
        "frame_count": frame_count,
        "threshold": dedup_threshold,
        "duration": video_duration,
        "use_parallel": should_use_parallel(frame_count, dedup_threshold, video_duration),
        "reason": ""
    }
    
    # Memory check
    memory_estimates = estimate_memory_requirements(frame_count)
    memory_safe = check_memory_safety(memory_estimates["total_gb"], available_memory_gb)
    
    if not memory_safe:
        strategy["use_parallel"] = False
        strategy["reason"] = "Memory safety check failed"
        logger.warning(f"Memory unsafe: Falling back to sequential processing")
    
    # Determine worker count if parallel
    if strategy["use_parallel"]:
        strategy["worker_count"] = get_optimal_worker_count(frame_count)
        strategy["reason"] = f"Parallel with {strategy['worker_count']} workers recommended"
    else:
        strategy["worker_count"] = 1
        if not strategy.get("reason"):
            strategy["reason"] = "Sequential processing recommended"
    
    # Add memory info
    strategy.update({
        "memory_estimates": memory_estimates,
        "memory_safe": memory_safe,
        "available_memory_gb": available_memory_gb
    })
    
    logger.info(f"Dedup strategy for {frame_count} frames, threshold={dedup_threshold}:")
    logger.info(f"  Method: {'PARALLEL' if strategy['use_parallel'] else 'SEQUENTIAL'}")
    logger.info(f"  Workers: {strategy['worker_count']}")
    logger.info(f"  Reason: {strategy['reason']}")
    logger.info(f"  Memory estimate: {memory_estimates['total_gb']} GB")
    logger.info(f"  Memory safe: {memory_safe}")
    
    return strategy


def log_dedup_start(strategy: Dict[str, Any]) -> None:
    """
    Log deduplication start with strategy details.
    
    Args:
        strategy: Strategy dictionary from get_dedup_strategy
    """
    logger.info("=" * 60)
    logger.info("DEDUPLICATION START")
    logger.info("=" * 60)
    logger.info(f"Frame count: {strategy['frame_count']}")
    logger.info(f"Threshold: {strategy['threshold']}")
    logger.info(f"Duration: {strategy['duration']}s")
    logger.info(f"Method: {'PARALLEL' if strategy['use_parallel'] else 'SEQUENTIAL'}")
    
    if strategy['use_parallel']:
        logger.info(f"Workers: {strategy['worker_count']}")
        logger.info(f"Memory estimate: {strategy['memory_estimates']['total_gb']} GB")
    
    logger.info(f"Reason: {strategy['reason']}")
    logger.info("=" * 60)


def log_dedup_completion(
    strategy: Dict[str, Any],
    results: Dict[str, Any],
    performance: Dict[str, float]
) -> None:
    """
    Log deduplication completion with results.
    
    Args:
        strategy: Strategy dictionary
        results: Deduplication results
        performance: Performance metrics
    """
    logger.info("=" * 60)
    logger.info("DEDUPLICATION COMPLETE")
    logger.info("=" * 60)
    
    # Results summary
    if "original_count" in results and "deduped_count" in results:
        original = results["original_count"]
        deduped = results["deduped_count"]
        removed = original - deduped
        reduction = (removed / original * 100) if original > 0 else 0
        
        logger.info(f"Results:")
        logger.info(f"  Original frames: {original}")
        logger.info(f"  Deduped frames: {deduped}")
        logger.info(f"  Removed: {removed} ({reduction:.1f}%)")
    
    # Performance summary
    if performance:
        logger.info(f"Performance:")
        for key, value in performance.items():
            if isinstance(value, float):
                logger.info(f"  {key.replace('_', ' ').title()}: {value:.3f}s")
            else:
                logger.info(f"  {key.replace('_', ' ').title()}: {value}")
    
    # Strategy effectiveness
    if strategy['use_parallel'] and 'speedup' in performance:
        speedup = performance['speedup']
        logger.info(f"Parallel effectiveness: {speedup:.2f}x speedup")
        
        if speedup < 1.0:
            logger.warning(f"Parallel was slower than sequential!")
        elif speedup < 2.0:
            logger.info(f"Moderate speedup achieved")
        else:
            logger.info(f"Significant speedup achieved")
    
    logger.info("=" * 60)


# ============================================================================
# Scene-aware scheduling
# ============================================================================

def get_scene_aware_strategy(
    frame_count: int,
    dedup_threshold: int,
    video_duration: float = 0,
    available_memory_gb: float = 64,
    scene_count: int = 0,
    avg_scene_frames: int = 0,
    use_scene_aware: bool = True
) -> Dict[str, Any]:
    """
    Get deduplication strategy considering scene information.
    
    Args:
        frame_count: Total number of frames
        dedup_threshold: Deduplication threshold
        video_duration: Video duration in seconds
        available_memory_gb: Available system memory in GB
        scene_count: Number of detected scenes (0 for auto-detect)
        avg_scene_frames: Average frames per scene (0 for auto-calculate)
        use_scene_aware: Whether to use scene-aware scheduling
    
    Returns:
        Strategy dictionary with scene information
    """
    if not use_scene_aware or not SCENE_DETECTION_AVAILABLE or scene_count == 0:
        # Fall back to regular strategy
        return get_dedup_strategy(
            frame_count=frame_count,
            dedup_threshold=dedup_threshold,
            video_duration=video_duration,
            available_memory_gb=available_memory_gb
        )
    
    logger.info(f"Scene-aware strategy with {scene_count} scenes, avg {avg_scene_frames} frames/scene")
    
    # Calculate memory requirements per scene
    memory_per_scene = estimate_memory_requirements(
        frame_count=avg_scene_frames
    )
    
    total_memory_estimate = memory_per_scene["total_gb"] * scene_count
    memory_safe = total_memory_estimate <= available_memory_gb * 0.8  # 80% safety margin
    
    # Determine if parallel is beneficial at scene level
    use_parallel = should_use_parallel(avg_scene_frames, dedup_threshold, video_duration / scene_count)
    
    # Scene-aware worker count: spread workers across scenes
    if use_parallel:
        system_cores = multiprocessing.cpu_count()
        max_workers = max(1, system_cores - 2)
        
        # Distribute workers based on scene complexity
        if avg_scene_frames < 50:
            workers_per_scene = max(1, min(2, avg_scene_frames // 10 + 1))
        elif avg_scene_frames < 200:
            workers_per_scene = max(2, min(4, avg_scene_frames // 50 + 2))
        else:
            workers_per_scene = max(4, min(8, avg_scene_frames // 100 + 4))
        
        # Total workers across all scenes (limited by system)
        total_workers = min(max_workers, workers_per_scene * scene_count)
        
        # If we have more scenes than workers, process scenes in batches
        if scene_count > total_workers:
            logger.info(f"Processing {scene_count} scenes in batches with {total_workers} workers")
            worker_count = total_workers
            batch_size = max(1, scene_count // total_workers)
        else:
            logger.info(f"Processing {scene_count} scenes with {total_workers} workers")
            worker_count = min(total_workers, scene_count)
            batch_size = 1
    else:
        worker_count = 1
        batch_size = scene_count
    
    strategy = {
        "use_parallel": use_parallel,
        "worker_count": worker_count,
        "reason": f"Scene-aware: {scene_count} scenes, {avg_scene_frames} frames/scene",
        "method": "PARALLEL" if use_parallel else "SEQUENTIAL",
        "memory_estimate_gb": total_memory_estimate,
        "memory_safe": memory_safe,
        "scene_aware": True,
        "scene_count": scene_count,
        "avg_scene_frames": avg_scene_frames,
        "batch_size": batch_size,
        "workers_per_scene": workers_per_scene if use_parallel else 1
    }
    
    return strategy


def analyze_scenes_for_dedup(
    frames_dir: Path,
    fps: float = 30.0,
    scene_detection_threshold: float = 30.0,
    min_scene_length: int = 15
) -> Tuple[List[SceneInfo], Dict[str, Any]]:
    """
    Analyze video frames to detect scenes and calculate deduplication strategy.
    
    Args:
        frames_dir: Directory containing frame images
        fps: Frames per second
        scene_detection_threshold: Threshold for scene detection
        min_scene_length: Minimum scene length in frames
    
    Returns:
        Tuple of (scenes list, statistics dict)
    """
    if not SCENE_DETECTION_AVAILABLE:
        logger.warning("Scene detection not available")
        return [], {}
    
    try:
        # Detect scenes from frames
        scenes = detect_scenes_from_frames(
            frames_dir,
            fps=fps,
            detector_type="content",
            threshold=scene_detection_threshold,
            min_scene_len=min_scene_length
        )
        
        if not scenes:
            logger.info("No scenes detected, treating as single scene")
            scenes = [
                SceneInfo(
                    scene_id=1,
                    start_frame=1,
                    end_frame=len(list(frames_dir.glob("frame_*.jpg"))),
                    start_time=0.0,
                    end_time=0.0,
                    duration=0.0,
                    frame_count=len(list(frames_dir.glob("frame_*.jpg"))),
                    scene_type="content",
                    confidence=1.0
                )
            ]
        
        # Calculate scene statistics
        stats = {
            "scene_count": len(scenes),
            "total_frames": sum(scene.frame_count for scene in scenes),
            "avg_scene_frames": sum(scene.frame_count for scene in scenes) / len(scenes) if scenes else 0,
            "min_scene_frames": min(scene.frame_count for scene in scenes) if scenes else 0,
            "max_scene_frames": max(scene.frame_count for scene in scenes) if scenes else 0,
            "avg_scene_duration": sum(scene.duration for scene in scenes) / len(scenes) if scenes else 0,
        }
        
        logger.info(f"Scene analysis: {stats['scene_count']} scenes, "
                   f"{stats['avg_scene_frames']:.1f} avg frames/scene")
        
        return scenes, stats
        
    except Exception as e:
        logger.error(f"Scene analysis failed: {e}", exc_info=True)
        return [], {}


def get_scene_aware_dedup_plan(
    frames_dir: Path,
    dedup_threshold: int,
    fps: float = 30.0,
    available_memory_gb: float = 64,
    scene_detection_threshold: float = 30.0
) -> Dict[str, Any]:
    """
    Create a comprehensive deduplication plan with scene awareness.
    
    Args:
        frames_dir: Directory containing frame images
        dedup_threshold: Deduplication threshold
        fps: Frames per second
        available_memory_gb: Available system memory in GB
        scene_detection_threshold: Threshold for scene detection
    
    Returns:
        Comprehensive deduplication plan
    """
    # Analyze scenes
    scenes, scene_stats = analyze_scenes_for_dedup(
        frames_dir,
        fps=fps,
        scene_detection_threshold=scene_detection_threshold
    )
    
    # Get scene-aware strategy
    strategy = get_scene_aware_strategy(
        frame_count=scene_stats.get("total_frames", 0),
        dedup_threshold=dedup_threshold,
        video_duration=scene_stats.get("total_frames", 0) / fps if fps > 0 else 0,
        available_memory_gb=available_memory_gb,
        scene_count=scene_stats.get("scene_count", 0),
        avg_scene_frames=scene_stats.get("avg_scene_frames", 0),
        use_scene_aware=len(scenes) > 0
    )
    
    # Create comprehensive plan
    plan = {
        "strategy": strategy,
        "scenes": [scene.to_dict() for scene in scenes] if scenes else [],
        "scene_stats": scene_stats,
        "frames_dir": str(frames_dir),
        "dedup_threshold": dedup_threshold,
        "fps": fps,
        "estimated_memory_gb": strategy.get("memory_estimate_gb", 0),
        "memory_safe": strategy.get("memory_safe", False),
        "recommended_approach": strategy.get("method", "UNKNOWN"),
        "execution_plan": {
            "process_scenes_in_batches": strategy.get("batch_size", 1) > 1,
            "batch_size": strategy.get("batch_size", 1),
            "workers_per_scene": strategy.get("workers_per_scene", 1),
            "total_workers": strategy.get("worker_count", 1)
        }
    }
    
    logger.info(f"Scene-aware dedup plan created:")
    logger.info(f"  Scenes: {len(scenes)}")
    logger.info(f"  Strategy: {strategy.get('method', 'UNKNOWN')}")
    logger.info(f"  Workers: {strategy.get('worker_count', 1)}")
    logger.info(f"  Memory: {strategy.get('memory_estimate_gb', 0):.2f} GB ({'SAFE' if strategy.get('memory_safe', False) else 'WARNING'})")
    
    return plan