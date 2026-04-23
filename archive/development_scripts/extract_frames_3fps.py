#!/usr/bin/env python3
"""
Extract frames from test videos at 3 FPS.
"""

import subprocess
import json
import time
from pathlib import Path
import shutil
import sys
import concurrent.futures

def extract_frames_at_3fps(video_path: Path, output_dir: Path):
    """
    Extract frames from video at 3 FPS.
    
    Args:
        video_path: Path to video file
        output_dir: Directory to save frames
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create frames directory
    frames_dir = output_dir / "frames"
    thumbs_dir = frames_dir / "thumbs"
    frames_dir.mkdir(exist_ok=True)
    thumbs_dir.mkdir(exist_ok=True)
    
    print(f"Extracting frames from {video_path.name} at 3 FPS...")
    print(f"  Video path: {video_path}")
    print(f"  Output dir: {output_dir}")
    
    # Use ffmpeg to extract frames at 10 FPS
    frame_pattern = frames_dir / "frame_%06d.jpg"
    
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", "fps=3",  # Extract at 3 FPS (no scaling for faster extraction)
        "-q:v", "2",  # JPEG quality (2=high quality)
        "-loglevel", "error",
        "-threads", "8",  # Use multiple threads
        str(frame_pattern)
    ]
    
    try:
        start_time = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        extract_time = time.time() - start_time
        
        if result.returncode != 0:
            print(f"  Error extracting frames: {result.stderr}")
            return None
        
        # Count extracted frames
        frame_files = list(frames_dir.glob("frame_*.jpg"))
        
        if not frame_files:
            print(f"  No frames extracted!")
            return None
        
        print(f"  Extracted {len(frame_files)} frames in {extract_time:.1f}s")
        
        # Skip thumbnails for faster extraction - can be created on demand
        print(f"  Skipping thumbnail creation for faster extraction...")
        # Thumbnails can be created on demand when needed
        
        # Get video duration using ffprobe
        duration = get_video_duration(video_path)
        
        # Create metadata
        metadata = {
            "video_name": video_path.name,
            "fps": 3.0,
            "duration": duration,
            "frame_count": len(frame_files),
            "extract_time": extract_time,
            "source_path": str(video_path),
            "extracted_at": time.time()
        }
        
        meta_file = output_dir / "frames_meta.json"
        meta_file.write_text(json.dumps(metadata, indent=2))
        
        print(f"  Saved metadata to {meta_file}")
        
        return {
            "frames_dir": frames_dir,
            "thumbs_dir": thumbs_dir,
            "frame_files": frame_files,
            "metadata": metadata,
            "output_dir": output_dir
        }
        
    except subprocess.TimeoutExpired:
        print(f"  Frame extraction timed out after 5 minutes")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

def get_video_duration(video_path: Path) -> float:
    """Get video duration using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except:
        pass
    
    return 0.0

def extract_all_test_videos_at_3fps():
    """Extract frames from all test videos at 3 FPS."""
    test_videos_dir = Path("test_videos")
    
    if not test_videos_dir.exists():
        print(f"Test videos directory not found: {test_videos_dir}")
        return {}
    
    results = {}
    
    # Process each category
    categories = ["small", "medium", "large", "very_large"]
    
    for category in categories:
        source_dir = test_videos_dir / category / "source"
        processed_dir = test_videos_dir / category / "processed_3fps"
        
        if not source_dir.exists():
            print(f"No source directory for {category}")
            continue
        
        # Find video files
        video_files = list(source_dir.glob("*.mp4")) + list(source_dir.glob("*.mov")) + \
                     list(source_dir.glob("*.avi")) + list(source_dir.glob("*.mkv"))
        
        if not video_files:
            print(f"No video files found in {source_dir}")
            continue
        
        print(f"\n{'='*60}")
        print(f"Processing {category.upper()} videos at 3 FPS")
        print(f"{'='*60}")
        
        # Clean processed directory
        if processed_dir.exists():
            shutil.rmtree(processed_dir)
        
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        category_results = []
        
        # Process videos with ThreadPoolExecutor for faster processing
        print(f"Processing {len(video_files)} videos in parallel...")
        
        def process_video(video_file):
            # Create output directory for this video
            video_stem = video_file.stem
            video_output_dir = processed_dir / video_stem
            
            print(f"  Processing: {video_file.name}")
            
            result = extract_frames_at_3fps(video_file, video_output_dir)
            
            if result:
                return {
                    "video_name": video_file.name,
                    "frame_count": len(result["frame_files"]),
                    "duration": result["metadata"]["duration"],
                    "fps": 3.0,
                    "extract_time": result["metadata"]["extract_time"],
                    "frames_dir": result["frames_dir"],
                    "metadata": result["metadata"]
                }
            return None
        
        # Use ThreadPoolExecutor to process videos in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_video = {executor.submit(process_video, video_file): video_file 
                              for video_file in video_files}
            
            for future in concurrent.futures.as_completed(future_to_video):
                result = future.result()
                if result:
                    category_results.append(result)
        
        results[category] = category_results
    
    return results

def main():
    """Main function."""
    print("="*70)
    print("TEST VIDEO FRAME EXTRACTION AT 3 FPS")
    print("="*70)
    
    # Check for ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: ffmpeg not found. Please install ffmpeg first.")
        print("On Ubuntu/Debian: sudo apt-get install ffmpeg")
        print("On macOS: brew install ffmpeg")
        return 1
    
    # Extract frames
    results = extract_all_test_videos_at_3fps()
    
    if not any(results.values()):
        print("\nNo frames extracted. Check your test videos directory.")
        return 1
    
    # Generate summary
    print(f"\n{'='*60}")
    print("EXTRACTION SUMMARY")
    print(f"{'='*60}")
    
    total_frames = 0
    total_videos = 0
    
    for category, videos in results.items():
        if videos:
            category_frames = sum(v["frame_count"] for v in videos)
            total_frames += category_frames
            total_videos += len(videos)
            
            print(f"\n{category.upper()}:")
            print(f"  Videos: {len(videos)}")
            print(f"  Total frames: {category_frames}")
            
            for video in videos:
                print(f"  - {video['video_name']}: {video['frame_count']} frames")
    
    print(f"\n{'='*60}")
    print(f"TOTAL: {total_videos} videos, {total_frames} frames at 3 FPS")
    print(f"{'='*60}")
    
    # Save results
    report_file = Path("test_videos/extraction_report_3fps.json")
    report = {
        "extraction_date": time.time(),
        "fps": 3.0,
        "categories": results
    }
    
    report_file.write_text(json.dumps(report, indent=2))
    
    print(f"\n✅ Frame extraction at 3 FPS complete!")
    print(f"Extraction report: {report_file}")
    print(f"\nNext steps:")
    print(f"1. Run parallel deduplication tests on the extracted frames")
    print(f"2. Check extracted frames in: test_videos/*/processed_3fps/")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
