#!/usr/bin/env python3
"""
Test script for parallel deduplication implementation.
Run this to verify the parallel deduplication system works.
"""

import sys
import time
import tempfile
import json
from pathlib import Path
import shutil
import multiprocessing

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def create_test_frames(test_dir: Path, frame_count: int = 100):
    """Create test frame images for deduplication testing."""
    frames_dir = test_dir / "frames"
    thumbs_dir = frames_dir / "thumbs"
    
    frames_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(exist_ok=True)
    
    print(f"Creating {frame_count} test frames...")
    
    frame_paths = []
    for i in range(1, frame_count + 1):
        # Create frame file
        frame_path = frames_dir / f"frame_{i:06d}.jpg"
        
        # Create deterministic "image" data
        # Every 5 frames are similar (for dedup testing)
        similarity_group = i % 5
        
        # Write test data
        content = f"TEST_FRAME_{similarity_group}_SEQ_{i}".encode() * 100
        frame_path.write_bytes(content)
        frame_paths.append(frame_path)
        
        # Create thumbnail
        thumb_path = thumbs_dir / f"thumb_{i:06d}.jpg"
        thumb_content = f"TEST_THUMB_{i}".encode() * 10
        thumb_path.write_bytes(thumb_content)
    
    # Create metadata
    meta_path = test_dir / "frames_meta.json"
    meta_path.write_text(json.dumps({
        "fps": 30.0,
        "duration": frame_count / 30.0,
        "frame_count": frame_count
    }))
    
    print(f"Created {len(frame_paths)} test frames in {frames_dir}")
    return frames_dir, thumbs_dir, frame_paths


def test_parallel_hash_computation():
    """Test parallel hash computation utility."""
    print("\n" + "="*60)
    print("TEST 1: Parallel Hash Computation")
    print("="*60)
    
    try:
        from src.utils.parallel_hash import compute_hashes_parallel, benchmark_parallel_vs_sequential
        
        # Create test frames
        test_dir = Path(tempfile.mkdtemp(prefix="test_hash_"))
        frames_dir, thumbs_dir, frame_paths = create_test_frames(test_dir, 50)
        
        # Test parallel computation
        print(f"Testing parallel hash computation with {len(frame_paths)} frames...")
        start_time = time.time()
        
        hash_results = compute_hashes_parallel(
            frame_paths,
            max_workers=4,  # Use 4 workers for testing
            chunk_size=10
        )
        
        elapsed = time.time() - start_time
        
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Results: {len(hash_results)} successful hashes")
        print(f"  Speed: {len(frame_paths)/elapsed:.1f} frames/sec")
        
        # Verify results
        success_rate = (len(hash_results) / len(frame_paths)) * 100
        print(f"  Success rate: {success_rate:.1f}%")
        
        assert success_rate >= 99.0, f"Success rate {success_rate}% below 99% threshold"
        
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
        
        print("✓ Parallel hash computation test PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Parallel hash computation test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_parallel_file_operations():
    """Test parallel file operations utility."""
    print("\n" + "="*60)
    print("TEST 2: Parallel File Operations")
    print("="*60)
    
    try:
        from src.utils.parallel_file_ops import delete_frames_parallel
        
        # Create test frames
        test_dir = Path(tempfile.mkdtemp(prefix="test_fileops_"))
        frames_dir, thumbs_dir, frame_paths = create_test_frames(test_dir, 20)
        
        # Test parallel deletion
        print(f"Testing parallel file deletion with {len(frame_paths)} frames...")
        
        # Select some frames to delete
        frames_to_delete = frame_paths[:10]  # Delete first 10 frames
        
        delete_stats = delete_frames_parallel(
            frames_to_delete,
            thumbs_dir,
            max_workers=2
        )
        
        print(f"  Total: {delete_stats['total']}")
        print(f"  Successful: {delete_stats['successful']}")
        print(f"  Failed: {delete_stats['failed']}")
        print(f"  Success rate: {delete_stats['success_rate']}%")
        
        # Verify deletion
        remaining_frames = len(list(frames_dir.glob("frame_*.jpg")))
        expected_remaining = len(frame_paths) - delete_stats["successful"]
        
        print(f"  Remaining frames: {remaining_frames} (expected: {expected_remaining})")
        
        assert delete_stats["success_rate"] >= 95.0, \
            f"Success rate {delete_stats['success_rate']}% below 95%"
        
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
        
        print("✓ Parallel file operations test PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Parallel file operations test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dedup_scheduler():
    """Test deduplication scheduler logic."""
    print("\n" + "="*60)
    print("TEST 3: Deduplication Scheduler")
    print("="*60)
    
    try:
        from src.utils.dedup_scheduler import (
            get_dedup_strategy,
            should_use_parallel,
            get_optimal_worker_count,
            estimate_memory_requirements
        )
        
        cpu_count = multiprocessing.cpu_count()
        print(f"System CPU count: {cpu_count}")
        
        # Test strategy selection
        test_cases = [
            (5, 10, 0.5, "Very small video"),
            (100, 10, 10.0, "Medium video"),
            (1000, 10, 100.0, "Large video"),
            (10000, 10, 1000.0, "Very large video"),
        ]
        
        for frame_count, threshold, duration, description in test_cases:
            strategy = get_dedup_strategy(
                frame_count=frame_count,
                dedup_threshold=threshold,
                video_duration=duration,
                available_memory_gb=192
            )
            
            print(f"\n{description}:")
            print(f"  Frames: {frame_count}, Threshold: {threshold}")
            print(f"  Method: {'PARALLEL' if strategy['use_parallel'] else 'SEQUENTIAL'}")
            print(f"  Workers: {strategy['worker_count']}")
            print(f"  Reason: {strategy['reason']}")
            
            # Verify strategy makes sense
            if frame_count < 50:
                # Small videos might use sequential
                assert strategy['worker_count'] <= 4
            else:
                # Larger videos should use parallel
                assert strategy['use_parallel'] is True
                assert strategy['worker_count'] <= cpu_count
        
        # Test memory estimation
        estimates = estimate_memory_requirements(
            frame_count=1000,
            frame_resolution=(1920, 1080)
        )
        
        print(f"\nMemory estimates for 1000 frames:")
        print(f"  Image data: {estimates['image_memory_gb']} GB")
        print(f"  Process overhead: {estimates['process_memory_gb']} GB")
        print(f"  Total estimate: {estimates['total_gb']} GB")
        
        assert estimates['total_gb'] > 0
        assert estimates['total_gb'] < 10.0  # Should be reasonable
        
        print("✓ Deduplication scheduler test PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Deduplication scheduler test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integrated_dedup():
    """Test integrated deduplication functionality."""
    print("\n" + "="*60)
    print("TEST 4: Integrated Deduplication")
    print("="*60)
    
    try:
        from app import _run_dedup
        
        # Create test frames
        test_dir = Path(tempfile.mkdtemp(prefix="test_integrated_"))
        frames_dir, thumbs_dir, frame_paths = create_test_frames(test_dir, 100)
        
        # Test deduplication
        print(f"Testing integrated deduplication with {len(frame_paths)} frames...")
        
        start_time = time.time()
        
        results = _run_dedup(
            frames_dir,
            thumbs_dir,
            dedup_threshold=10,
            fps=30.0
        )
        
        elapsed = time.time() - start_time
        
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Original frames: {results['original_count']}")
        print(f"  Deduped frames: {results['deduped_count']}")
        print(f"  Removed: {results['original_count'] - results['deduped_count']}")
        
        # Verify results are sane
        assert results['original_count'] == len(frame_paths)
        assert results['deduped_count'] <= results['original_count']
        assert results['deduped_count'] >= 20  # At least 20 unique frames in our pattern
        
        # Check strategy info
        if 'dedup_strategy' in results:
            strategy = results['dedup_strategy']
            print(f"  Strategy: {strategy['method']}")
            print(f"  Workers: {strategy['worker_count']}")
            print(f"  Reason: {strategy['reason']}")
        
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
        
        print("✓ Integrated deduplication test PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Integrated deduplication test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_performance_benchmark():
    """Run performance benchmarks."""
    print("\n" + "="*60)
    print("TEST 5: Performance Benchmark")
    print("="*60)
    
    try:
        from src.utils.parallel_hash import benchmark_parallel_vs_sequential
        
        # Create test frames
        test_dir = Path(tempfile.mkdtemp(prefix="test_benchmark_"))
        frames_dir, thumbs_dir, frame_paths = create_test_frames(test_dir, 200)
        
        print(f"Running benchmark with {len(frame_paths)} frames...")
        
        # Run benchmark
        benchmark_results = benchmark_parallel_vs_sequential(
            frame_paths,
            max_workers=4  # Use 4 workers for benchmark
        )
        
        print(f"\nBenchmark Results:")
        print(f"  Frame count: {benchmark_results['frame_count']}")
        print(f"  Sequential time: {benchmark_results['sequential']['time_seconds']}s")
        print(f"  Parallel time: {benchmark_results['parallel']['time_seconds']}s")
        print(f"  Speedup: {benchmark_results['comparison']['speedup']}x")
        print(f"  Accuracy: {benchmark_results['comparison']['accuracy_percent']}%")
        print(f"  Time saved: {benchmark_results['comparison']['time_saved_seconds']}s")
        
        # Verify benchmark results
        assert benchmark_results['frame_count'] == len(frame_paths)
        assert benchmark_results['comparison']['speedup'] > 0
        assert benchmark_results['comparison']['accuracy_percent'] >= 95.0
        
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
        
        print("\n✓ Performance benchmark test PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Performance benchmark test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("="*70)
    print("PARALLEL DEDUPLICATION TEST SUITE")
    print("="*70)
    print(f"System: {multiprocessing.cpu_count()} CPUs available")
    print()
    
    tests = [
        test_parallel_hash_computation,
        test_parallel_file_operations,
        test_dedup_scheduler,
        test_integrated_dedup,
        test_performance_benchmark
    ]
    
    results = []
    for test_func in tests:
        try:
            success = test_func()
            results.append((test_func.__name__, success))
        except Exception as e:
            print(f"Error in {test_func.__name__}: {e}")
            results.append((test_func.__name__, False))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = 0
    failed = 0
    
    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {test_name}")
        
        if success:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())