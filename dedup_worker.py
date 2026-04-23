#!/usr/bin/env python3
"""
Standalone deduplication worker that runs in a separate process.
Avoids eventlet/Flask threading issues by running in isolation.
"""

import sys
import os
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any

# Add current directory to path so we can import from src
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
import imagehash
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def compute_phash_single(args):
    """Compute perceptual hash for a single frame.
    Used with ProcessPoolExecutor (must be picklable)."""
    frame_path_str, frame_path_idx = args
    frame_path = Path(frame_path_str)
    try:
        img = Image.open(frame_path)
        phash = imagehash.phash(img)
        return (frame_path_str, phash, frame_path_idx, None)
    except Exception as e:
        return (frame_path_str, None, frame_path_idx, str(e))


def compute_hashes_parallel_processes(
    frame_paths: List[Path],
    max_workers: int = None,
    chunk_size: int = 100
) -> Dict[str, Any]:
    """Compute perceptual hashes using ProcessPoolExecutor (real processes)."""
    if not frame_paths:
        return {}
    
    if max_workers is None:
        max_workers = max(1, multiprocessing.cpu_count() - 2)
    
    logger.info(f"Computing hashes for {len(frame_paths)} frames using {max_workers} processes")
    
    results = {}
    errors = 0
    start_time = time.time()
    
    # Prepare arguments (must be picklable)
    args_list = [(str(fp), i) for i, fp in enumerate(frame_paths)]
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_idx = {}
        for i, arg in enumerate(args_list):
            future = executor.submit(compute_phash_single, arg)
            future_to_idx[future] = i
        
        # Process results as they complete
        completed = 0
        for future in as_completed(future_to_idx):
            completed += 1
            try:
                frame_path_str, phash, idx, error = future.result(timeout=30)
                if error:
                    errors += 1
                    logger.warning(f"Failed hash for {Path(frame_path_str).name}: {error}")
                elif phash is not None:
                    results[frame_path_str] = (phash, idx)
                else:
                    errors += 1
                    logger.warning(f"Empty hash for {Path(frame_path_str).name}")
            except TimeoutError:
                errors += 1
                logger.error(f"Timeout for frame {completed}")
            except Exception as e:
                errors += 1
                logger.error(f"Exception: {e}")
            
            # Log progress
            if completed % 100 == 0:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                logger.info(f"Progress: {completed}/{len(frame_paths)} frames ({rate:.1f} fps)")
    
    total_time = time.time() - start_time
    logger.info(f"Hash computation complete: {len(results)} successes, {errors} errors, {total_time:.2f}s")
    
    return results


def run_dedup_multi(
    frames_dir: Path,
    thresholds: List[int] = [5, 10, 15, 20, 30],
    max_workers: int = None
) -> Dict[str, Any]:
    """Run multi-threshold deduplication."""
    if not frames_dir.exists():
        raise ValueError(f"Frames directory not found: {frames_dir}")
    
    extracted_frames = sorted(frames_dir.glob("frame_*.jpg"))
    original_count = len(extracted_frames)
    
    if original_count <= 1:
        return {
            "results": [
                {
                    "threshold": t,
                    "original_count": original_count,
                    "deduped_count": original_count,
                    "dropped": 0,
                    "dropped_pct": 0
                }
                for t in thresholds
            ],
            "original_count": original_count,
            "fps": 1.0,
            "duration": 0.0
        }
    
    logger.info(f"Dedup for {frames_dir.parent.name}: {original_count} frames, {len(thresholds)} thresholds")
    
    # Compute hashes with real processes (no eventlet issues)
    hash_start = time.time()
    hash_results = compute_hashes_parallel_processes(
        extracted_frames,
        max_workers=max_workers,
        chunk_size=100
    )
    hash_time = time.time() - hash_start
    
    # Extract hashes in order
    hashes = []
    for fp in extracted_frames:
        if str(fp) in hash_results:
            phash, _ = hash_results[str(fp)]
            hashes.append(phash)
        else:
            # Fallback sequential
            try:
                hashes.append(imagehash.phash(Image.open(fp)))
            except Exception:
                hashes.append(imagehash.ImageHash([0] * 8))
    
    # Process thresholds and save keep indices
    threshold_results = {}
    keep_indices_by_threshold = {}
    for t in thresholds:
        if t <= 0:
            # Keep all frames for threshold 0
            threshold_results[t] = len(hashes)
            keep_indices_by_threshold[str(t)] = list(range(len(hashes)))  # Store as string key
            continue
        
        keep_indices = [0]
        prev = hashes[0]
        for i in range(1, len(hashes)):
            if (prev - hashes[i]) >= t:
                keep_indices.append(i)
                prev = hashes[i]
        threshold_results[t] = len(keep_indices)
        keep_indices_by_threshold[str(t)] = keep_indices  # Store as string key
    
    # Build results
    results = []
    for t in thresholds:
        kept = threshold_results.get(t, original_count)
        dropped = original_count - kept
        pct = round((dropped / original_count) * 100, 1) if original_count > 0 else 0
        
        results.append({
            "threshold": t,
            "original_count": original_count,
            "deduped_count": kept,
            "dropped": dropped,
            "dropped_pct": pct,
        })
    
    total_time = time.time() - hash_start
    
    logger.info(f"Dedup completed in {total_time:.2f}s (hash: {hash_time:.2f}s)")
    
    return {
        "results": results,
        "original_count": original_count,
        "fps": 1.0,
        "duration": 0.0,
        "performance_metrics": {
            "hash_computation_time": hash_time,
            "total_time": total_time
        },
        "keep_indices_by_threshold": keep_indices_by_threshold,
        "frame_paths": [str(fp) for fp in extracted_frames]  # Save frame paths in order
    }


def main():
    """Main entry point for standalone dedup worker."""
    if len(sys.argv) < 2:
        print("Usage: python dedup_worker.py <frames_dir> [thresholds...]")
        print("Example: python dedup_worker.py /path/to/frames 5 10 15 20 30")
        sys.exit(1)
    
    frames_dir = Path(sys.argv[1])
    thresholds = [5, 10, 15, 20, 30]
    
    if len(sys.argv) > 2:
        thresholds = []
        for arg in sys.argv[2:]:
            try:
                thresholds.append(int(arg))
            except ValueError:
                pass
    
    if not thresholds:
        thresholds = [5, 10, 15, 20, 30]
    
    try:
        result = run_dedup_multi(frames_dir, thresholds=thresholds)
        print(json.dumps(result, indent=2))
    except Exception as e:
        logger.error(f"Dedup failed: {e}", exc_info=True)
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()