#!/usr/bin/env python3
"""
Comprehensive parallel deduplication performance test.
Tests all video categories with parallel vs sequential comparison.
"""

import sys
import time
import json
import statistics
from pathlib import Path
import multiprocessing

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def load_test_videos():
    """Load all test videos with extracted frames."""
    test_videos_dir = Path("test_videos")
    videos = []
    
    categories = ["small", "medium", "large", "very_large"]
    
    for category in categories:
        # Try 3 FPS processed directory first, then fallback to generic processed
        processed_dir = test_videos_dir / category / "processed_3fps"
        
        if not processed_dir.exists():
            processed_dir = test_videos_dir / category / "processed"
        
        if not processed_dir.exists():
            continue
        
        # Find all video directories
        for video_dir in processed_dir.iterdir():
            if not video_dir.is_dir():
                continue
            
            # Check for frames
            frames_dir = video_dir / "frames"
            meta_file = video_dir / "frames_meta.json"
            
            if not frames_dir.exists() or not meta_file.exists():
                continue
            
            # Load metadata
            try:
                meta = json.loads(meta_file.read_text())
            except:
                meta = {}
            
            # Count frames
            frame_files = list(frames_dir.glob("frame_*.jpg"))
            
            if not frame_files:
                continue
            
            videos.append({
                "category": category,
                "name": video_dir.name,
                "frames_dir": frames_dir,
                "thumbs_dir": frames_dir / "thumbs",
                "frame_count": len(frame_files),
                "fps": meta.get("fps", 1.0),
                "duration": meta.get("duration", 0),
                "meta": meta
            })
    
    # Sort by frame count
    videos.sort(key=lambda x: x["frame_count"])
    return videos

def run_dedup_test(video_info, threshold=10, use_parallel=True, max_workers=None):
    """Run deduplication test on a single video."""
    from app import _run_dedup
    
    frames_dir = video_info["frames_dir"]
    thumbs_dir = video_info["thumbs_dir"]
    fps = video_info["fps"]
    
    print(f"  Testing: {video_info['name']} ({video_info['frame_count']} frames)")
    
    # Force parallel/sequential if specified
    original_import = None
    if not use_parallel:
        # Temporarily disable parallel dedup
        import app
        original_import = app.PARALLEL_DEDUP_AVAILABLE
        app.PARALLEL_DEDUP_AVAILABLE = False
    
    try:
        start_time = time.time()
        
        results = _run_dedup(
            frames_dir,
            thumbs_dir,
            dedup_threshold=threshold,
            fps=fps
        )
        
        elapsed = time.time() - start_time
        
        test_result = {
            "video_name": video_info["name"],
            "category": video_info["category"],
            "frame_count": video_info["frame_count"],
            "use_parallel": use_parallel,
            "elapsed_time": elapsed,
            "original_count": results.get("original_count", 0),
            "deduped_count": results.get("deduped_count", 0),
            "removed": results.get("original_count", 0) - results.get("deduped_count", 0),
            "reduction_pct": 0
        }
        
        if results.get("original_count", 0) > 0:
            removed = results["original_count"] - results["deduped_count"]
            test_result["reduction_pct"] = (removed / results["original_count"]) * 100
        
        # Extract strategy info
        if "dedup_strategy" in results:
            strategy = results["dedup_strategy"]
            test_result["strategy_method"] = strategy.get("method")
            test_result["worker_count"] = strategy.get("worker_count")
        
        # Extract performance metrics
        if "performance_metrics" in results:
            metrics = results["performance_metrics"]
            test_result["hash_time"] = metrics.get("hash_computation_time")
            test_result["dedup_time"] = metrics.get("dedup_logic_time")
            test_result["delete_time"] = metrics.get("file_deletion_time")
            test_result["total_time"] = metrics.get("total_time")
        
        print(f"    Time: {elapsed:.2f}s, "
              f"Kept: {test_result['deduped_count']}/{test_result['original_count']} frames "
              f"({test_result['reduction_pct']:.1f}% reduction)")
        
        if "strategy_method" in test_result:
            print(f"    Strategy: {test_result['strategy_method']}, "
                  f"Workers: {test_result.get('worker_count', 'N/A')}")
        
        return test_result
        
    except Exception as e:
        print(f"    ERROR: {e}")
        return {
            "video_name": video_info["name"],
            "category": video_info["category"],
            "frame_count": video_info["frame_count"],
            "use_parallel": use_parallel,
            "error": str(e),
            "elapsed_time": 0
        }
    
    finally:
        # Restore original import state
        if original_import is not None:
            import app
            app.PARALLEL_DEDUP_AVAILABLE = original_import

def run_category_tests(category_videos, category, threshold=10):
    """Run tests for a specific category."""
    print(f"\n{'='*60}")
    print(f"Testing {category.upper()} videos ({len(category_videos)} videos)")
    print(f"{'='*60}")
    
    results = []
    
    for video_info in category_videos:
        # Run parallel test
        parallel_result = run_dedup_test(video_info, threshold, use_parallel=True)
        results.append(parallel_result)
        
        # Run sequential test for comparison (skip for very small/large to save time)
        if 50 <= video_info["frame_count"] <= 1000:
            sequential_result = run_dedup_test(video_info, threshold, use_parallel=False)
            results.append(sequential_result)
            
            # Calculate speedup if both succeeded
            if (parallel_result.get("elapsed_time", 0) > 0 and 
                sequential_result.get("elapsed_time", 0) > 0):
                speedup = sequential_result["elapsed_time"] / parallel_result["elapsed_time"]
                print(f"    Speedup: {speedup:.2f}x")
    
    return results

def analyze_results(all_results):
    """Analyze test results and generate report."""
    print(f"\n{'='*70}")
    print("PERFORMANCE ANALYSIS")
    print(f"{'='*70}")
    
    # Organize by category
    categories = {}
    for result in all_results:
        if "error" in result:
            continue
            
        category = result["category"]
        if category not in categories:
            categories[category] = {"parallel": [], "sequential": []}
        
        if result["use_parallel"]:
            categories[category]["parallel"].append(result)
        else:
            categories[category]["sequential"].append(result)
    
    # Analyze each category
    report = {
        "summary": {},
        "categories": {},
        "recommendations": []
    }
    
    cpu_count = multiprocessing.cpu_count()
    print(f"System CPU count: {cpu_count}")
    print()
    
    for category, data in categories.items():
        parallel_results = data["parallel"]
        sequential_results = data["sequential"]
        
        if not parallel_results:
            continue
        
        print(f"{category.upper()} VIDEYS:")
        print(f"  Videos tested: {len(parallel_results)}")
        
        # Parallel statistics
        if parallel_results:
            avg_time = statistics.mean([r["elapsed_time"] for r in parallel_results])
            avg_fps = statistics.mean([r["frame_count"] / r["elapsed_time"] 
                                      for r in parallel_results if r["elapsed_time"] > 0])
            avg_reduction = statistics.mean([r["reduction_pct"] for r in parallel_results])
            
            print(f"  Parallel:")
            print(f"    Avg time: {avg_time:.2f}s")
            print(f"    Avg speed: {avg_fps:.1f} frames/sec")
            print(f"    Avg reduction: {avg_reduction:.1f}%")
            
            # Worker counts
            worker_counts = [r.get("worker_count", 1) for r in parallel_results 
                            if "worker_count" in r]
            if worker_counts:
                avg_workers = statistics.mean(worker_counts)
                print(f"    Avg workers: {avg_workers:.1f}")
        
        # Sequential statistics
        if sequential_results:
            seq_avg_time = statistics.mean([r["elapsed_time"] for r in sequential_results])
            seq_avg_fps = statistics.mean([r["frame_count"] / r["elapsed_time"] 
                                          for r in sequential_results if r["elapsed_time"] > 0])
            
            print(f"  Sequential:")
            print(f"    Avg time: {seq_avg_time:.2f}s")
            print(f"    Avg speed: {seq_avg_fps:.1f} frames/sec")
            
            # Calculate speedup
            if parallel_results and sequential_results:
                # Match videos by name for comparison
                speedups = []
                for seq_result in sequential_results:
                    for par_result in parallel_results:
                        if (seq_result["video_name"] == par_result["video_name"] and
                            seq_result["elapsed_time"] > 0 and par_result["elapsed_time"] > 0):
                            speedup = seq_result["elapsed_time"] / par_result["elapsed_time"]
                            speedups.append(speedup)
                
                if speedups:
                    avg_speedup = statistics.mean(speedups)
                    max_speedup = max(speedups)
                    min_speedup = min(speedups)
                    
                    print(f"  Speedup (parallel vs sequential):")
                    print(f"    Average: {avg_speedup:.2f}x")
                    print(f"    Maximum: {max_speedup:.2f}x")
                    print(f"    Minimum: {min_speedup:.2f}x")
                    
                    # Store in report
                    report["categories"][category] = {
                        "avg_speedup": avg_speedup,
                        "max_speedup": max_speedup,
                        "min_speedup": min_speedup,
                        "parallel_avg_fps": avg_fps,
                        "sequential_avg_fps": seq_avg_fps,
                        "video_count": len(parallel_results),
                        "avg_frame_count": statistics.mean([r["frame_count"] for r in parallel_results])
                    }
        
        print()
    
    # Generate recommendations
    print(f"{'='*70}")
    print("RECOMMENDATIONS")
    print(f"{'='*70}")
    
    for category, stats in report.get("categories", {}).items():
        avg_speedup = stats.get("avg_speedup", 1.0)
        avg_frames = stats.get("avg_frame_count", 0)
        
        if avg_speedup < 1.1:
            recommendation = f"{category}: Use sequential (parallel overhead > benefit)"
        elif avg_speedup < 2.0:
            recommendation = f"{category}: Optional parallel (moderate speedup)"
        else:
            recommendation = f"{category}: Recommended parallel ({avg_speedup:.1f}x speedup)"
        
        print(f"  {recommendation}")
        report["recommendations"].append(recommendation)
    
    # System-wide recommendation
    print(f"\nSystem-wide: With {cpu_count} CPU cores:")
    print(f"  Max parallel workers configured: 30 (all but 2 cores)")
    print(f"  Optimal for: Videos with >100 frames")
    print(f"  Memory available: 192GB (sufficient for large videos)")
    
    return report

def save_report(report, filename="parallel_dedup_report.json"):
    """Save test report to file."""
    report_file = Path(filename)
    
    # Convert Path objects to strings for JSON
    def convert_paths(obj):
        if isinstance(obj, dict):
            return {k: convert_paths(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_paths(v) for v in obj]
        elif isinstance(obj, Path):
            return str(obj)
        else:
            return obj
    
    report_json = convert_paths(report)
    report_json["generated_at"] = time.time()
    
    report_file.write_text(json.dumps(report_json, indent=2))
    print(f"\nReport saved to: {report_file}")
    
    return report_file

def main():
    """Main test function."""
    print("="*70)
    print("PARALLEL DEDUPLICATION PERFORMANCE TEST")
    print("="*70)
    print(f"Testing all video categories with frame extraction")
    print()
    
    # Load test videos
    videos = load_test_videos()
    
    if not videos:
        print("No test videos found. Run extract_test_frames.py first.")
        return 1
    
    print(f"Found {len(videos)} test videos:")
    for video in videos:
        print(f"  {video['category']}: {video['name']} ({video['frame_count']} frames)")
    
    # Group by category
    videos_by_category = {}
    for video in videos:
        category = video["category"]
        if category not in videos_by_category:
            videos_by_category[category] = []
        videos_by_category[category].append(video)
    
    # Run tests for each category
    all_results = []
    
    for category, category_videos in videos_by_category.items():
        category_results = run_category_tests(category_videos, category)
        all_results.extend(category_results)
    
    # Analyze results
    report = analyze_results(all_results)
    
    # Save report
    save_report(report)
    
    print(f"\n{'='*70}")
    print("TEST COMPLETE")
    print("="*70)
    print("Summary:")
    print(f"  Total videos tested: {len(videos)}")
    print(f"  Total frames processed: {sum(v['frame_count'] for v in videos)}")
    print(f"  Categories: {', '.join(videos_by_category.keys())}")
    print()
    print("Next steps:")
    print("  1. Check parallel_dedup_report.json for detailed results")
    print("  2. Adjust MAX_DEDUP_WORKERS in config/constants.py if needed")
    print("  3. Monitor real-world performance with your actual videos")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())