#!/usr/bin/env python3
"""
Test parallel deduplication with real video frames.
"""

import sys
import time
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_real_video_dedup():
    """Test deduplication with real video frames."""
    print("Testing parallel deduplication with real video frames...")
    
    # Find a video with frames
    uploads_dir = Path("uploads")
    video_dirs = list(uploads_dir.glob("*/frames"))
    
    if not video_dirs:
        print("No videos with frames found in uploads directory")
        return False
    
    # Use the first video with frames
    frames_dir = video_dirs[0]
    video_dir = frames_dir.parent
    thumbs_dir = frames_dir / "thumbs"
    
    print(f"Testing with video: {video_dir.name}")
    print(f"Frames directory: {frames_dir}")
    
    # Check if frames exist
    frame_files = list(frames_dir.glob("frame_*.jpg"))
    
    if not frame_files:
        print("No frame files found")
        return False
    
    print(f"Found {len(frame_files)} frame files")
    
    # Check if metadata exists
    meta_path = video_dir / "frames_meta.json"
    fps = 30.0  # Default FPS
    
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            fps = meta.get("fps", 30.0)
            print(f"Video metadata: FPS={fps}, Duration={meta.get('duration', 'unknown')}")
        except Exception as e:
            print(f"Error reading metadata: {e}")
    
    # Test the parallel deduplication
    try:
        from app import _run_dedup
        
        print(f"\nRunning deduplication with threshold=10, FPS={fps}...")
        start_time = time.time()
        
        results = _run_dedup(
            frames_dir,
            thumbs_dir,
            dedup_threshold=10,
            fps=fps
        )
        
        elapsed = time.time() - start_time
        
        print(f"\nDeduplication completed in {elapsed:.2f}s")
        print(f"Original frames: {results.get('original_count', 'N/A')}")
        print(f"Deduped frames: {results.get('deduped_count', 'N/A')}")
        
        if 'dedup_strategy' in results:
            strategy = results['dedup_strategy']
            print(f"Strategy used: {strategy.get('method', 'unknown')}")
            print(f"Worker count: {strategy.get('worker_count', 'N/A')}")
            print(f"Reason: {strategy.get('reason', 'N/A')}")
        
        if 'performance_metrics' in results:
            metrics = results['performance_metrics']
            print(f"\nPerformance metrics:")
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    if 'time' in key.lower():
                        print(f"  {key}: {value:.2f}s")
                    else:
                        print(f"  {key}: {value}")
        
        # Check if results are reasonable
        if 'original_count' in results and 'deduped_count' in results:
            original = results['original_count']
            deduped = results['deduped_count']
            
            if deduped <= original:
                print(f"\n✓ Deduplication successful: {deduped}/{original} frames kept")
                return True
            else:
                print(f"\n✗ Error: deduped_count ({deduped}) > original_count ({original})")
                return False
        else:
            print("\n✗ Error: Missing required fields in results")
            return False
            
    except Exception as e:
        print(f"\n✗ Error during deduplication: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_parallel_hash_utility():
    """Test parallel hash computation utility."""
    print("\n" + "="*60)
    print("Testing parallel hash computation utility...")
    
    # Find some frame files
    frames_dir = Path("uploads")
    frame_files = list(frames_dir.rglob("frame_*.jpg"))
    
    if len(frame_files) < 10:
        print(f"Need at least 10 frame files, found {len(frame_files)}")
        return False
    
    # Take first 20 frames for testing
    test_frames = frame_files[:20]
    print(f"Testing with {len(test_frames)} frame files")
    
    try:
        from src.utils.parallel_hash import compute_hashes_parallel
        
        start_time = time.time()
        
        hash_results = compute_hashes_parallel(
            test_frames,
            max_workers=4,
            chunk_size=5
        )
        
        elapsed = time.time() - start_time
        
        print(f"\nHash computation completed in {elapsed:.2f}s")
        print(f"Successfully computed {len(hash_results)}/{len(test_frames)} hashes")
        print(f"Speed: {len(test_frames)/elapsed:.1f} frames/sec")
        
        if len(hash_results) > 0:
            print("✓ Parallel hash computation successful")
            return True
        else:
            print("✗ No hashes computed")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    """Run tests."""
    print("="*70)
    print("PARALLEL DEDUPLICATION TEST - REAL DATA")
    print("="*70)
    print()
    
    # Test 1: Real video deduplication
    print("Test 1: Real Video Deduplication")
    print("-"*40)
    test1_passed = test_real_video_dedup()
    
    # Test 2: Parallel hash utility
    print("\n" + "="*60)
    print("Test 2: Parallel Hash Utility")
    print("-"*40)
    test2_passed = test_parallel_hash_utility()
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    if test1_passed:
        print("✓ Test 1: Real Video Deduplication - PASSED")
    else:
        print("✗ Test 1: Real Video Deduplication - FAILED")
    
    if test2_passed:
        print("✓ Test 2: Parallel Hash Utility - PASSED")
    else:
        print("✗ Test 2: Parallel Hash Utility - FAILED")
    
    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print("\n⚠️ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())