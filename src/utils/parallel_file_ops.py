#!/usr/bin/env python3
"""
Parallel file operations for deduplication cleanup.
Uses multiprocessing for concurrent file deletion and management.
"""

import multiprocessing
import time
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

logger = logging.getLogger(__name__)


def delete_frame_and_thumb(args: Tuple[Path, Path]) -> Tuple[Path, bool, Optional[str]]:
    """
    Delete a frame and its corresponding thumbnail.
    Designed for use with multiprocessing starmap.
    
    Args:
        args: Tuple of (frame_path, thumbs_dir)
        
    Returns:
        Tuple of (frame_path, success, error_message)
    """
    frame_path, thumbs_dir = args
    
    try:
        # Delete frame file
        if frame_path.exists():
            frame_path.unlink()
            logger.debug(f"Deleted frame: {frame_path.name}")
        
        # Delete thumbnail file
        thumb_name = frame_path.name.replace("frame_", "thumb_")
        thumb_path = thumbs_dir / thumb_name
        if thumb_path.exists():
            thumb_path.unlink()
            logger.debug(f"Deleted thumbnail: {thumb_name}")
        
        return (frame_path, True, None)
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to delete {frame_path}: {error_msg}")
        return (frame_path, False, error_msg)


def delete_frames_parallel(
    frame_paths: List[Path],
    thumbs_dir: Path,
    max_workers: int = None
) -> Dict[str, Any]:
    """
    Delete multiple frames and thumbnails in parallel.
    
    Args:
        frame_paths: List of frame paths to delete
        thumbs_dir: Directory containing thumbnails
        max_workers: Number of worker processes
        
    Returns:
        Dictionary with deletion statistics
    """
    if not frame_paths:
        logger.info("No frames to delete")
        return {
            "total": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": 100.0,
            "time_seconds": 0.0
        }
    
    # Determine worker count
    if max_workers is None:
        cpu_count = multiprocessing.cpu_count()
        max_workers = max(1, min(cpu_count - 2, len(frame_paths) // 10 + 1))
    
    logger.info(f"Deleting {len(frame_paths)} frames in parallel "
                f"(workers={max_workers})")
    
    # Prepare arguments for multiprocessing
    delete_args = [(fp, thumbs_dir) for fp in frame_paths]
    
    start_time = time.time()
    successful = 0
    failed = 0
    errors = []
    
    with multiprocessing.Pool(processes=max_workers) as pool:
        # Use imap_unordered for better performance with many files
        results = pool.imap_unordered(delete_frame_and_thumb, delete_args)
        
        for i, (frame_path, success, error_msg) in enumerate(results):
            if success:
                successful += 1
                if (i + 1) % 100 == 0:
                    logger.info(f"Deleted {i + 1}/{len(frame_paths)} frames")
            else:
                failed += 1
                errors.append(f"{frame_path.name}: {error_msg}")
    
    elapsed = time.time() - start_time
    success_rate = (successful / len(frame_paths)) * 100 if frame_paths else 100.0
    
    logger.info(f"Parallel deletion completed:")
    logger.info(f"  Total frames: {len(frame_paths)}")
    logger.info(f"  Successful: {successful} ({success_rate:.1f}%)")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Time: {elapsed:.2f}s")
    logger.info(f"  Speed: {len(frame_paths)/elapsed:.1f} files/sec")
    
    if failed > 0:
        logger.warning(f"Failed deletions ({failed} frames):")
        for error in errors[:10]:  # Show first 10 errors
            logger.warning(f"  {error}")
        if len(errors) > 10:
            logger.warning(f"  ... and {len(errors) - 10} more errors")
    
    return {
        "total": len(frame_paths),
        "successful": successful,
        "failed": failed,
        "success_rate": round(success_rate, 1),
        "time_seconds": round(elapsed, 3),
        "speed_fps": round(len(frame_paths) / elapsed, 1) if elapsed > 0 else 0,
        "errors": errors[:20]  # Return up to 20 errors
    }


def copy_frames_parallel(
    source_paths: List[Tuple[Path, Path]],
    max_workers: int = None
) -> Dict[str, Any]:
    """
    Copy multiple frames in parallel.
    
    Args:
        source_paths: List of (source_path, dest_path) tuples
        max_workers: Number of worker processes
        
    Returns:
        Dictionary with copy statistics
    """
    if not source_paths:
        return {"total": 0, "successful": 0, "failed": 0, "time_seconds": 0.0}
    
    import shutil
    
    def copy_single(args):
        src, dst = args
        try:
            shutil.copy2(src, dst)
            return (src, dst, True, None)
        except Exception as e:
            return (src, dst, False, str(e))
    
    if max_workers is None:
        cpu_count = multiprocessing.cpu_count()
        max_workers = max(1, cpu_count - 2)
    
    logger.info(f"Copying {len(source_paths)} files in parallel (workers={max_workers})")
    
    start_time = time.time()
    successful = 0
    failed = 0
    
    with multiprocessing.Pool(processes=max_workers) as pool:
        results = pool.map(copy_single, source_paths)
        
        for src, dst, success, error in results:
            if success:
                successful += 1
            else:
                failed += 1
                logger.error(f"Failed to copy {src} to {dst}: {error}")
    
    elapsed = time.time() - start_time
    
    logger.info(f"Parallel copy completed:")
    logger.info(f"  Total files: {len(source_paths)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Time: {elapsed:.2f}s")
    
    return {
        "total": len(source_paths),
        "successful": successful,
        "failed": failed,
        "time_seconds": round(elapsed, 3)
    }


def get_optimal_worker_count(
    operation_count: int,
    operation_type: str = "delete"
) -> int:
    """
    Calculate optimal number of workers for file operations.
    
    Args:
        operation_count: Number of files to process
        operation_type: Type of operation ("delete", "copy", "hash")
        
    Returns:
        Optimal worker count
    """
    cpu_count = multiprocessing.cpu_count()
    
    if operation_count <= 10:
        # Small operations: use fewer workers to minimize overhead
        return max(1, min(2, cpu_count // 4))
    
    elif operation_count <= 100:
        # Medium operations: scale with CPU count
        return max(1, min(cpu_count // 2, operation_count // 10 + 1))
    
    else:
        # Large operations: use most CPUs but leave some free
        base_workers = max(1, cpu_count - 2)
        
        # Adjust based on operation type
        if operation_type == "hash":
            # Hash computation is CPU-intensive, use more workers
            return base_workers
        elif operation_type == "delete":
            # Deletion is I/O intensive, use fewer workers for SSD optimization
            return min(base_workers, 16)  # Cap at 16 for SSD optimization
        else:  # copy or other
            return min(base_workers, 8)  # Conservative default
    
    
def validate_deletion_results(
    frame_paths: List[Path],
    thumbs_dir: Path,
    deletion_stats: Dict[str, Any]
) -> bool:
    """
    Validate that files were actually deleted.
    
    Args:
        frame_paths: Original frame paths
        thumbs_dir: Thumbnail directory
        deletion_stats: Statistics from delete_frames_parallel
        
    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating file deletion...")
    
    remaining_frames = []
    remaining_thumbs = []
    
    # Check frames
    for frame_path in frame_paths:
        if frame_path.exists():
            remaining_frames.append(frame_path)
    
    # Check thumbnails
    for frame_path in frame_paths:
        thumb_name = frame_path.name.replace("frame_", "thumb_")
        thumb_path = thumbs_dir / thumb_name
        if thumb_path.exists():
            remaining_thumbs.append(thumb_path)
    
    if remaining_frames or remaining_thumbs:
        logger.warning(f"Validation failed:")
        logger.warning(f"  Remaining frames: {len(remaining_frames)}")
        logger.warning(f"  Remaining thumbnails: {len(remaining_thumbs)}")
        
        # Log first few remaining files
        for frame in remaining_frames[:5]:
            logger.warning(f"    Frame still exists: {frame}")
        for thumb in remaining_thumbs[:5]:
            logger.warning(f"    Thumb still exists: {thumb}")
        
        if len(remaining_frames) > 5:
            logger.warning(f"    ... and {len(remaining_frames) - 5} more frames")
        if len(remaining_thumbs) > 5:
            logger.warning(f"    ... and {len(remaining_thumbs) - 5} more thumbs")
        
        return False
    else:
        logger.info("Validation passed: All files deleted successfully")
        return True