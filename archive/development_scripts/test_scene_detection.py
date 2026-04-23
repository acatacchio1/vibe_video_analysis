#!/usr/bin/env python3
"""
Test scene detection integration with PySceneDetect.
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_scene_detection_availability():
    """Test if PySceneDetect is available."""
    logger.info("Testing PySceneDetect availability...")
    
    try:
        from src.utils.scene_detection import PYSSCENEDETECT_AVAILABLE
        if PYSSCENEDETECT_AVAILABLE:
            logger.info("✅ PySceneDetect is available")
            return True
        else:
            logger.warning("❌ PySceneDetect not available")
            return False
    except ImportError as e:
        logger.error(f"❌ Failed to import scene detection: {e}")
        return False


def test_scene_detection_on_video(video_path: Path):
    """Test scene detection on a video file."""
    if not video_path.exists():
        logger.error(f"Video not found: {video_path}")
        return None
    
    logger.info(f"Testing scene detection on {video_path.name}")
    
    try:
        from src.utils.scene_detection import detect_scenes_video
        
        start_time = time.time()
        scenes = detect_scenes_video(
            video_path,
            detector_type="content",
            threshold=30.0,
            min_scene_len=15
        )
        detection_time = time.time() - start_time
        
        if scenes:
            logger.info(f"✅ Detected {len(scenes)} scenes in {detection_time:.2f}s")
            
            # Calculate statistics
            total_frames = sum(scene.frame_count for scene in scenes)
            avg_scene_frames = total_frames / len(scenes) if scenes else 0
            
            stats = {
                "video": video_path.name,
                "scene_count": len(scenes),
                "total_frames": total_frames,
                "avg_scene_frames": avg_scene_frames,
                "detection_time": detection_time,
                "fps": total_frames / detection_time if detection_time > 0 else 0,
                "min_scene_frames": min(scene.frame_count for scene in scenes) if scenes else 0,
                "max_scene_frames": max(scene.frame_count for scene in scenes) if scenes else 0,
            }
            
            return stats
        else:
            logger.warning("❌ No scenes detected")
            return None
            
    except Exception as e:
        logger.error(f"❌ Scene detection failed: {e}")
        return None


def test_scene_detection_from_frames(frames_dir: Path, fps: float = 30.0):
    """Test scene detection from extracted frames."""
    if not frames_dir.exists():
        logger.error(f"Frames directory not found: {frames_dir}")
        return None
    
    frame_files = list(frames_dir.glob("frame_*.jpg"))
    if not frame_files:
        logger.error(f"No frames found in {frames_dir}")
        return None
    
    logger.info(f"Testing scene detection from {len(frame_files)} frames")
    
    try:
        from src.utils.scene_detection import detect_scenes_from_frames
        
        start_time = time.time()
        scenes = detect_scenes_from_frames(
            frames_dir,
            fps=fps,
            detector_type="content",
            threshold=30.0,
            min_scene_len=15
        )
        detection_time = time.time() - start_time
        
        if scenes:
            logger.info(f"✅ Created {len(scenes)} scene(s) in {detection_time:.2f}s")
            
            stats = {
                "frames_dir": str(frames_dir),
                "frame_count": len(frame_files),
                "scene_count": len(scenes),
                "detection_time": detection_time,
                "avg_scene_frames": len(frame_files) / len(scenes) if scenes else 0,
            }
            
            return stats
        else:
            logger.warning("❌ No scenes created")
            return None
            
    except Exception as e:
        logger.error(f"❌ Frame-based scene detection failed: {e}")
        return None


def test_scene_aware_dedup(frames_dir: Path, fps: float = 30.0):
    """Test scene-aware deduplication."""
    if not frames_dir.exists():
        logger.error(f"Frames directory not found: {frames_dir}")
        return None
    
    frame_files = list(frames_dir.glob("frame_*.jpg"))
    if not frame_files:
        logger.error(f"No frames found in {frames_dir}")
        return None
    
    logger.info(f"Testing scene-aware dedup on {len(frame_files)} frames")
    
    try:
        from src.utils.scene_detection import integrate_scenes_with_dedup, detect_scenes_from_frames
        
        # First detect scenes
        scenes = detect_scenes_from_frames(
            frames_dir,
            fps=fps,
            detector_type="content",
            threshold=30.0,
            min_scene_len=15
        )
        
        if not scenes:
            logger.warning("No scenes detected, testing with single scene")
        
        # Test with different dedup thresholds
        results = {}
        
        for dedup_threshold in [5, 10, 15, 20]:
            logger.info(f"  Testing dedup threshold={dedup_threshold}")
            
            start_time = time.time()
            dedup_results = integrate_scenes_with_dedup(
                frames_dir,
                scenes,
                fps=fps,
                dedup_threshold=dedup_threshold,
                use_parallel=True
            )
            dedup_time = time.time() - start_time
            
            if dedup_results:
                overall_stats = dedup_results.get("overall_statistics", {})
                results[dedup_threshold] = {
                    "original_frames": overall_stats.get("original_frames", 0),
                    "deduped_frames": overall_stats.get("total_deduped_frames", 0),
                    "removed_frames": overall_stats.get("total_removed_frames", 0),
                    "removed_percentage": overall_stats.get("removed_percentage", 0),
                    "processing_time": dedup_time,
                    "scene_count": dedup_results.get("total_scenes", 0),
                }
                
                logger.info(f"    Removed {results[dedup_threshold]['removed_frames']} frames "
                           f"({results[dedup_threshold]['removed_percentage']:.1f}%) in {dedup_time:.2f}s")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Scene-aware dedup failed: {e}")
        return None


def test_scene_aware_scheduler(frames_dir: Path, fps: float = 30.0):
    """Test scene-aware scheduling."""
    if not frames_dir.exists():
        logger.error(f"Frames directory not found: {frames_dir}")
        return None
    
    logger.info("Testing scene-aware scheduler...")
    
    try:
        from src.utils.dedup_scheduler import get_scene_aware_dedup_plan
        
        for dedup_threshold in [5, 10, 20]:
            plan = get_scene_aware_dedup_plan(
                frames_dir,
                dedup_threshold=dedup_threshold,
                fps=fps,
                available_memory_gb=192,
                scene_detection_threshold=30.0
            )
            
            strategy = plan.get("strategy", {})
            scene_stats = plan.get("scene_stats", {})
            
            logger.info(f"  Threshold={dedup_threshold}:")
            logger.info(f"    Strategy: {strategy.get('method', 'UNKNOWN')}")
            logger.info(f"    Workers: {strategy.get('worker_count', 1)}")
            logger.info(f"    Scenes: {scene_stats.get('scene_count', 0)}")
            logger.info(f"    Memory: {strategy.get('memory_estimate_gb', 0):.2f} GB")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Scene-aware scheduling failed: {e}")
        return False


def main():
    """Main test function."""
    logger.info("=" * 70)
    logger.info("SCENE DETECTION INTEGRATION TEST")
    logger.info("=" * 70)
    
    # Test 1: Check availability
    if not test_scene_detection_availability():
        logger.error("PySceneDetect not available. Skipping further tests.")
        return 1
    
    # Test 2: Test with video files
    logger.info("\n" + "=" * 40)
    logger.info("TEST 1: Video-based scene detection")
    logger.info("=" * 40)
    
    test_videos = [
        Path("test_videos/small/source/YTDown.com_YouTube_Squirrel-dropkicks-groundhog_Media_B7zDTlQP1-o_002_720p.mp4"),
        Path("test_videos/medium/source/YTDown.com_YouTube_Robots-vs-humans-Beijing-half-marathon-d_Media_1vUnusbzNMQ_002_720p.mp4"),
    ]
    
    video_results = []
    for video_path in test_videos:
        if video_path.exists():
            result = test_scene_detection_on_video(video_path)
            if result:
                video_results.append(result)
    
    # Test 3: Test with extracted frames
    logger.info("\n" + "=" * 40)
    logger.info("TEST 2: Frame-based scene detection")
    logger.info("=" * 40)
    
    test_frames_dirs = [
        Path("test_videos/small/processed_3fps/YTDown.com_YouTube_Squirrel-dropkicks-groundhog_Media_B7zDTlQP1-o_002_720p/frames"),
        Path("test_videos/medium/processed_3fps/YTDown.com_YouTube_Robots-vs-humans-Beijing-half-marathon-d_Media_1vUnusbzNMQ_002_720p/frames"),
    ]
    
    frame_results = []
    for frames_dir in test_frames_dirs:
        if frames_dir.exists():
            # Get FPS from metadata if available
            fps = 3.0  # Default for our test videos
            meta_path = frames_dir.parent / "frames_meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    fps = meta.get("fps", 3.0)
                except:
                    pass
            
            result = test_scene_detection_from_frames(frames_dir, fps)
            if result:
                frame_results.append(result)
    
    # Test 4: Test scene-aware dedup
    logger.info("\n" + "=" * 40)
    logger.info("TEST 3: Scene-aware deduplication")
    logger.info("=" * 40)
    
    dedup_results = {}
    for frames_dir in test_frames_dirs:
        if frames_dir.exists():
            # Get FPS from metadata
            fps = 3.0
            meta_path = frames_dir.parent / "frames_meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    fps = meta.get("fps", 3.0)
                except:
                    pass
            
            result = test_scene_aware_dedup(frames_dir, fps)
            if result:
                dedup_results[str(frames_dir)] = result
    
    # Test 5: Test scene-aware scheduler
    logger.info("\n" + "=" * 40)
    logger.info("TEST 4: Scene-aware scheduling")
    logger.info("=" * 40)
    
    for frames_dir in test_frames_dirs:
        if frames_dir.exists():
            fps = 3.0
            meta_path = frames_dir.parent / "frames_meta.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    fps = meta.get("fps", 3.0)
                except:
                    pass
            
            test_scene_aware_scheduler(frames_dir, fps)
    
    # Generate summary report
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)
    
    if video_results:
        logger.info(f"Video-based detection: {len(video_results)} videos processed")
        for result in video_results:
            logger.info(f"  {result['video']}: {result['scene_count']} scenes, "
                       f"{result['detection_time']:.2f}s, {result['fps']:.1f} frames/sec")
    
    if frame_results:
        logger.info(f"Frame-based detection: {len(frame_results)} frame sets processed")
        for result in frame_results:
            logger.info(f"  {result['frames_dir']}: {result['scene_count']} scenes, "
                       f"{result['frame_count']} frames")
    
    if dedup_results:
        logger.info(f"Scene-aware dedup: {len(dedup_results)} tests completed")
        for frames_dir, results in dedup_results.items():
            logger.info(f"  {Path(frames_dir).parent.name}:")
            for threshold, stats in results.items():
                logger.info(f"    Threshold {threshold}: {stats['removed_percentage']:.1f}% reduction, "
                           f"{stats['processing_time']:.2f}s")
    
    logger.info("\n✅ Scene detection integration test completed!")
    
    # Save results to file
    report = {
        "test_date": time.time(),
        "video_results": video_results,
        "frame_results": frame_results,
        "dedup_results": dedup_results,
    }
    
    report_file = Path("scene_detection_test_report.json")
    report_file.write_text(json.dumps(report, indent=2))
    logger.info(f"Report saved to: {report_file}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())