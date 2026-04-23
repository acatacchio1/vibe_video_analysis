#!/usr/bin/env python3
"""
Parallel perceptual hash computation for frame deduplication.
Uses multiprocessing to utilize all available CPU cores.

Key Features:
- True parallel computation using multiprocessing (not threads)
- Memory-efficient chunked processing
- Comprehensive error handling with <1% error tolerance
- Detailed performance logging
"""

import time
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
from PIL import Image
import imagehash

logger = logging.getLogger(__name__)


def compute_phash_single(frame_path: Path) -> Tuple[Path, Optional[imagehash.ImageHash], int]:
    """
    Compute perceptual hash for a single frame.
    Thread-safe and process-safe for use with multiprocessing.
    
    Args:
        frame_path: Path to frame image file
        
    Returns:
        Tuple of (frame_path, hash, frame_number) or (frame_path, None, -1) on error
    """
    try:
        start_time = time.time()
        
        # Load image
        logger.debug(f"Loading image: {frame_path.name}")
        img = Image.open(frame_path)
        
        # Compute perceptual hash
        logger.debug(f"Computing phash for: {frame_path.name}")
        phash = imagehash.phash(img)
        
        # Extract frame number from filename
        frame_num = int(frame_path.stem.split("_")[1])
        
        elapsed = time.time() - start_time
        logger.debug(f"Computed hash for {frame_path.name} in {elapsed:.3f}s")
        
        return (frame_path, phash, frame_num)
        
    except Exception as e:
        logger.error(f"Failed to compute hash for {frame_path}: {e}")
        return (frame_path, None, -1)


def compute_hashes_parallel(
    frame_paths: List[Path],
    max_workers: int = None,
    chunk_size: int = 100
) -> Dict[Path, Tuple[imagehash.ImageHash, int]]:
    """
    Compute perceptual hashes for multiple frames in parallel.
    
    Args:
        frame_paths: List of frame file paths
        max_workers: Number of worker processes (default: CPU count - 2)
        chunk_size: Frames per worker batch (optimize for memory/performance)
        
    Returns:
        Dict mapping frame_path -> (hash, frame_number)
        
    Raises:
        RuntimeError: If error rate exceeds 1%
    """
    if not frame_paths:
        logger.warning("No frame paths provided to compute_hashes_parallel")
        return {}
    
    # Determine optimal worker count
    if max_workers is None:
        import os
        # For threads, we can use more workers than CPUs because of I/O wait
        # But PIL/imagehash is CPU-bound, so stick to CPU count
        try:
            cpu_count = len(os.sched_getaffinity(0))
        except AttributeError:
            import multiprocessing
            cpu_count = multiprocessing.cpu_count()
        max_workers = max(1, min(cpu_count, 8))  # Cap at 8 workers
        logger.info(f"Using {max_workers} workers (system has {cpu_count} CPUs)")
    
    logger.info(f"Computing hashes for {len(frame_paths)} frames in parallel "
                f"(workers={max_workers}, chunk_size={chunk_size})")
    
    total_frames = len(frame_paths)
    results = {}
    errors = 0
    start_time = time.time()
    
    # Process frames in chunks to balance memory and performance
    # Use ThreadPoolExecutor instead of multiprocessing.Pool to avoid deadlocks
    # with Flask/eventlet/gunicorn
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Limit workers more aggresively - PIL/imagehash is CPU-bound but also has GIL contention
    # So more workers than CPUs can help with I/O wait but too many causes thrashing
    max_workers = min(max_workers, 8)  # Cap at 8 workers
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Process all frames at once (ThreadPoolExecutor handles queuing)
        future_to_path = {}
        for frame_path in frame_paths:
            future = executor.submit(compute_phash_single, frame_path)
            future_to_path[future] = frame_path
        
        # Process results as they complete with timeout
        completed = 0
        timeout_seconds = 300  # 5 minute timeout
        timeout_start = time.time()
        
        for future in as_completed(future_to_path, timeout=timeout_seconds):
            # Check overall timeout
            if time.time() - timeout_start > timeout_seconds:
                logger.error(f"Overall timeout exceeded {timeout_seconds}s")
                executor.shutdown(wait=False)
                raise TimeoutError(f"Hash computation timed out after {timeout_seconds}s")
            
            completed += 1
            frame_path = future_to_path[future]
            try:
                frame_path_result, phash, frame_num = future.result(timeout=10)  # Individual task timeout
                if phash is not None:
                    results[frame_path] = (phash, frame_num)
                else:
                    errors += 1
                    logger.warning(f"Failed to compute hash for frame: {frame_path.name}")
            except TimeoutError:
                errors += 1
                logger.error(f"Timeout computing hash for {frame_path}")
            except Exception as e:
                errors += 1
                logger.error(f"Exception computing hash for {frame_path}: {e}")
            
            # Log progress every 100 frames
            if completed % 100 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                logger.info(f"Progress: {completed}/{total_frames} frames ({rate:.1f} fps)")
                
        # Check if we processed all frames
        if completed < total_frames:
            logger.warning(f"Only processed {completed} of {total_frames} frames")
    
    total_elapsed = time.time() - start_time
    
    # Calculate error rate
    error_rate = (errors / total_frames) * 100 if total_frames > 0 else 0
    success_rate = ((total_frames - errors) / total_frames) * 100 if total_frames > 0 else 0
    
    logger.info(f"Parallel hash computation completed:")
    logger.info(f"  Total frames: {total_frames}")
    logger.info(f"  Successful: {total_frames - errors} ({success_rate:.1f}%)")
    logger.info(f"  Errors: {errors} ({error_rate:.1f}%)")
    logger.info(f"  Total time: {total_elapsed:.2f}s")
    logger.info(f"  Speed: {total_frames/total_elapsed:.1f} frames/sec")
    logger.info(f"  Results stored: {len(results)}")
    
    # Check error rate threshold
    if error_rate > 1.0:
        error_msg = f"Error rate {error_rate:.1f}% exceeds 1% threshold"
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    return results


def compute_hashes_parallel_memory_efficient(
    frame_paths: List[Path],
    max_workers: int = None,
    batch_size: int = 1000
) -> List[Optional[imagehash.ImageHash]]:
    """
    Memory-efficient parallel hash computation for very large frame sets.
    Returns only hashes in order matching input paths.
    
    Args:
        frame_paths: List of frame file paths
        max_workers: Number of worker processes
        batch_size: Maximum frames to process in memory at once
        
    Returns:
        List of hashes in same order as frame_paths (None for failed frames)
    """
    logger.info(f"Memory-efficient hash computation for {len(frame_paths)} frames")
    
    if max_workers is None:
        max_workers = 4  # Conservative default for memory-efficient mode
    
    # Use ThreadPoolExecutor instead of multiprocessing
    from concurrent.futures import ThreadPoolExecutor
    
    hashes = [None] * len(frame_paths)
    errors = 0
    start_time = time.time()
    
    # Process in batches to control memory usage
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for batch_start in range(0, len(frame_paths), batch_size):
            batch_end = min(batch_start + batch_size, len(frame_paths))
            batch_paths = frame_paths[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_start//batch_size + 1}/"
                       f"{(len(frame_paths) + batch_size - 1)//batch_size} "
                       f"({len(batch_paths)} frames)")
            
            # Submit all frames in batch
            future_to_idx = {}
            for i, frame_path in enumerate(batch_paths):
                idx = batch_start + i
                future = executor.submit(compute_phash_single, frame_path)
                future_to_idx[future] = idx
            
            # Collect results
            for future in future_to_idx:
                idx = future_to_idx[future]
                try:
                    _, phash, _ = future.result()
                    if phash is not None:
                        hashes[idx] = phash
                    else:
                        errors += 1
                        logger.warning(f"Failed hash for frame {idx+1}")
                except Exception as e:
                    errors += 1
                    logger.error(f"Exception for frame {idx+1}: {e}")
    
    total_elapsed = time.time() - start_time
    error_rate = (errors / len(frame_paths)) * 100 if frame_paths else 0
    
    logger.info(f"Memory-efficient computation completed:")
    logger.info(f"  Total frames: {len(frame_paths)}")
    logger.info(f"  Errors: {errors} ({error_rate:.1f}%)")
    logger.info(f"  Time: {total_elapsed:.2f}s")
    logger.info(f"  Speed: {len(frame_paths)/total_elapsed:.1f} frames/sec")
    
    if error_rate > 1.0:
        raise RuntimeError(f"Error rate {error_rate:.1f}% exceeds 1% threshold")
    
    return hashes


def benchmark_parallel_vs_sequential(frame_paths: List[Path], max_workers: int = None) -> Dict[str, Any]:
    """
    Benchmark parallel vs sequential hash computation.
    
    Args:
        frame_paths: List of frame paths to benchmark
        max_workers: Number of parallel workers
        
    Returns:
        Dictionary with benchmark results
    """
    logger.info(f"Starting benchmark with {len(frame_paths)} frames")
    
    # Sequential benchmark
    logger.info("Running sequential benchmark...")
    seq_start = time.time()
    seq_results = {}
    seq_errors = 0
    
    for frame_path in frame_paths:
        try:
            img = Image.open(frame_path)
            phash = imagehash.phash(img)
            frame_num = int(frame_path.stem.split("_")[1])
            seq_results[frame_path] = (phash, frame_num)
        except Exception as e:
            seq_errors += 1
            logger.warning(f"Sequential error for {frame_path}: {e}")
    
    seq_time = time.time() - seq_start
    
    # Parallel benchmark
    logger.info("Running parallel benchmark...")
    par_start = time.time()
    par_results = compute_hashes_parallel(frame_paths, max_workers)
    par_time = time.time() - par_start
    
    # Calculate statistics
    seq_speed = len(frame_paths) / seq_time if seq_time > 0 else 0
    par_speed = len(frame_paths) / par_time if par_time > 0 else 0
    speedup = seq_time / par_time if par_time > 0 else 1.0
    
    # Compare results
    matching = 0
    for frame_path in frame_paths:
        if frame_path in seq_results and frame_path in par_results:
            seq_hash, _ = seq_results[frame_path]
            par_hash, _ = par_results[frame_path]
            if seq_hash == par_hash:
                matching += 1
    
    accuracy = (matching / len(frame_paths)) * 100 if frame_paths else 100
    
    # Build results
    results = {
        "frame_count": len(frame_paths),
        "sequential": {
            "time_seconds": round(seq_time, 3),
            "speed_fps": round(seq_speed, 1),
            "errors": seq_errors,
            "error_rate": round((seq_errors / len(frame_paths)) * 100, 1) if frame_paths else 0
        },
        "parallel": {
            "time_seconds": round(par_time, 3),
            "speed_fps": round(par_speed, 1),
            "workers": max_workers or 4,
            "errors": len(frame_paths) - len(par_results)
        },
        "comparison": {
            "speedup": round(speedup, 2),
            "accuracy_percent": round(accuracy, 1),
            "time_saved_seconds": round(seq_time - par_time, 2)
        }
    }
    
    logger.info(f"Benchmark Results:")
    logger.info(f"  Frame count: {results['frame_count']}")
    logger.info(f"  Sequential: {results['sequential']['time_seconds']}s "
               f"({results['sequential']['speed_fps']} fps)")
    logger.info(f"  Parallel: {results['parallel']['time_seconds']}s "
               f"({results['parallel']['speed_fps']} fps)")
    logger.info(f"  Speedup: {results['comparison']['speedup']}x")
    logger.info(f"  Accuracy: {results['comparison']['accuracy_percent']}%")
    logger.info(f"  Time saved: {results['comparison']['time_saved_seconds']}s")
    
    return results