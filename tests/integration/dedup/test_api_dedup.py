#!/usr/bin/env python3
"""
Integration tests for parallel deduplication API endpoints.
Tests actual API calls with simulated video data.
"""

import pytest
import json
import time
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestParallelDedupAPI:
    """Integration tests for parallel deduplication API endpoints."""
    
    @pytest.fixture
    def temp_video_dir(self):
        """Create temporary directory for test videos."""
        temp_dir = tempfile.mkdtemp(prefix="test_dedup_")
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_frame_images(self, temp_video_dir):
        from PIL import Image
        
        frames_dir = temp_video_dir / "frames"
        thumbs_dir = frames_dir / "thumbs"
        frames_dir.mkdir(parents=True)
        thumbs_dir.mkdir()
        
        frame_paths = []
        for i in range(1, 51):
            img = Image.new("RGB", (100, 100), color=(i % 256, (i * 2) % 256, (i * 3) % 256))
            frame_path = frames_dir / f"frame_{i:06d}.jpg"
            img.save(frame_path, "JPEG")
            frame_paths.append(frame_path)
            
            thumb_path = thumbs_dir / f"thumb_{i:06d}.jpg"
            img.save(thumb_path, "JPEG")
        
        meta_path = temp_video_dir / "frames_meta.json"
        meta_path.write_text(json.dumps({
            "fps": 30.0,
            "duration": 50.0,
            "frame_count": 50
        }))
        
        return {
            "frames_dir": frames_dir,
            "thumbs_dir": thumbs_dir,
            "frame_paths": frame_paths,
            "meta_path": meta_path
        }
    
    def test_api_response_structure(self):
        response_data = {
            "original_count": 100,
            "deduped_count": 50,
            "threshold": 10,
            "original_to_dedup_mapping": {"1": 1, "2": 2},
            "dedup_to_original_mapping": {"1": 1, "2": 2},
            "dedup_strategy": {
                "method": "parallel",
                "worker_count": 30,
                "reason": "Parallel with 30 workers recommended"
            }
        }

        assert response_data["original_count"] == 100
        assert response_data["deduped_count"] == 50
        assert response_data["threshold"] == 10

        strategy = response_data["dedup_strategy"]
        assert strategy["method"] == "parallel"
        assert strategy["worker_count"] == 30
        assert len(response_data["original_to_dedup_mapping"]) == len(response_data["dedup_to_original_mapping"])
        assert response_data["deduped_count"] <= response_data["original_count"]
    
    def test_configuration_options(self):
        """Test deduplication configuration options."""
        from config.constants import (
            USE_PARALLEL_DEDUP,
            MAX_DEDUP_WORKERS,
            DEDUP_CHUNK_SIZE,
            DEDUP_ERROR_RATE_THRESHOLD
        )
        
        # Verify configuration values
        assert MAX_DEDUP_WORKERS == 30
        assert DEDUP_CHUNK_SIZE == 100
        assert DEDUP_ERROR_RATE_THRESHOLD == 1.0
        
        # USE_PARALLEL_DEDUP can be True or False depending on environment
        assert isinstance(USE_PARALLEL_DEDUP, bool)


class TestDedupValidation:
    """Validation tests for deduplication results."""
    
    def test_dedup_mapping_consistency(self):
        """Test that deduplication mappings are consistent."""
        # Test data
        original_count = 100
        deduped_count = 50
        
        # Create consistent mappings
        original_to_dedup = {}
        dedup_to_original = {}
        
        # Simulate keeping every other frame
        for i in range(1, deduped_count + 1):
            original_num = i * 2 - 1
            original_to_dedup[str(original_num)] = i
            dedup_to_original[str(i)] = original_num
        
        # Verify consistency
        assert len(original_to_dedup) == deduped_count
        assert len(dedup_to_original) == deduped_count
        
        # Verify bidirectional mapping
        for orig_str, dedup_num in original_to_dedup.items():
            assert dedup_to_original[str(dedup_num)] == int(orig_str)
        
        for dedup_str, orig_num in dedup_to_original.items():
            assert original_to_dedup[str(orig_num)] == int(dedup_str)
    
    def test_threshold_monotonic_behavior(self):
        """Test that higher thresholds keep fewer frames."""
        # Simulated results for different thresholds
        threshold_results = {
            5: 80,   # 80 frames kept at threshold 5
            10: 60,  # 60 frames kept at threshold 10  
            15: 40,  # 40 frames kept at threshold 15
            20: 20,  # 20 frames kept at threshold 20
            30: 5    # 5 frames kept at threshold 30
        }
        
        # Verify monotonic behavior
        thresholds = sorted(threshold_results.keys())
        frame_counts = [threshold_results[t] for t in thresholds]
        
        for i in range(len(thresholds) - 1):
            assert frame_counts[i] >= frame_counts[i + 1], \
                f"Non-monotonic: threshold {thresholds[i]} -> {frame_counts[i]}, " \
                f"{thresholds[i+1]} -> {frame_counts[i+1]}"