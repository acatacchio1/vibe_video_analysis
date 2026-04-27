"""
Unit tests for transcript utility functions
"""

import pytest
import json
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.utils.transcript import (
    get_video_directory_from_path,
    find_transcript_file,
    load_transcript,
    get_transcript_segments_with_end_times,
)


class TestGetVideoDirectoryFromPath:
    """Tests for get_video_directory_from_path function"""

    def test_get_video_directory_from_path_exact_match(self, tmp_path):
        """Test stem directory exists"""
        # Create uploads directory and video file
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir(parents=True)
        video_file = uploads_dir / "video_name.mp4"
        video_file.touch()
        
        # Create matching video directory
        video_dir = uploads_dir / "video_name"
        video_dir.mkdir()
        
        result = get_video_directory_from_path(video_file)
        assert result == video_dir

    def test_get_video_directory_from_path_720p_suffix(self, tmp_path):
        """Test video_720p.mp4 -> video/ exists"""
        # Create directory without suffix
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        # Video file has _720p suffix
        video_file = tmp_path / "uploads" / "video_name_720p.mp4"
        video_file.touch()
        
        result = get_video_directory_from_path(video_file)
        assert result == video_dir

    def test_get_video_directory_from_path_dedup_suffix(self, tmp_path):
        """Test video_dedup.mp4 -> video/ exists"""
        # Create directory without suffix
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        # Video file has _dedup suffix
        video_file = tmp_path / "uploads" / "video_name_dedup.mp4"
        video_file.touch()
        
        result = get_video_directory_from_path(video_file)
        assert result == video_dir

    def test_get_video_directory_from_path_both_suffixes(self, tmp_path):
        """Test video_dedup_720p.mp4 -> video/ exists"""
        # Create directory without suffixes
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        # Video file has both suffixes
        video_file = tmp_path / "uploads" / "video_name_dedup_720p.mp4"
        video_file.touch()
        
        result = get_video_directory_from_path(video_file)
        assert result == video_dir

    def test_get_video_directory_from_path_no_match(self, tmp_path):
        """Test no directory exists, returns base/stem"""
        # Create video file but no directory
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.parent.mkdir(parents=True)
        video_file.touch()
        
        result = get_video_directory_from_path(video_file)
        expected = tmp_path / "uploads" / "video_name"
        assert result == expected

    def test_get_video_directory_from_path_priority_order(self, tmp_path):
        """Test exact stem exists before stripped version"""
        # Create both directories
        exact_dir = tmp_path / "uploads" / "video_name_720p"
        exact_dir.mkdir(parents=True)
        stripped_dir = tmp_path / "uploads" / "video_name"
        stripped_dir.mkdir(parents=True)
        
        video_file = tmp_path / "uploads" / "video_name_720p.mp4"
        video_file.touch()
        
        result = get_video_directory_from_path(video_file)
        # Should return exact match (video_name_720p) not stripped (video_name)
        assert result == exact_dir


class TestFindTranscriptFile:
    """Tests for find_transcript_file function"""

    def test_find_transcript_file_primary(self, tmp_path):
        """Test transcript in video_dir"""
        # Create video directory and transcript
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        transcript_file = video_dir / "transcript.json"
        transcript_file.write_text('{"text": "test", "segments": []}')
        
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.touch()
        
        result = find_transcript_file(str(video_file))
        assert result == transcript_file

    def test_find_transcript_file_with_frames_dir(self, tmp_path):
        """Test transcript found via frames_dir"""
        # Create structure: uploads/video_name/frames/
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        frames_dir = video_dir / "frames"
        frames_dir.mkdir()
        
        transcript_file = video_dir / "transcript.json"
        transcript_file.write_text('{"text": "test", "segments": []}')
        
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.touch()
        
        result = find_transcript_file(str(video_file), str(frames_dir))
        assert result == transcript_file

    def test_find_transcript_file_not_found(self, tmp_path):
        """Test returns None when transcript not found"""
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.parent.mkdir(parents=True)
        video_file.touch()
        
        result = find_transcript_file(str(video_file))
        assert result is None

    def test_find_transcript_file_dedup_video(self, tmp_path):
        """Test transcript found for deduped video"""
        # Create original video directory with transcript
        original_dir = tmp_path / "uploads" / "video_name"
        original_dir.mkdir(parents=True)
        transcript_file = original_dir / "transcript.json"
        transcript_file.write_text('{"text": "test", "segments": []}')
        
        # Deduped video file
        video_file = tmp_path / "uploads" / "video_name_dedup.mp4"
        video_file.touch()
        
        result = find_transcript_file(str(video_file))
        assert result == transcript_file


class TestLoadTranscript:
    """Tests for load_transcript function"""

    def test_load_transcript_success(self, tmp_path):
        """Test loads and validates JSON"""
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        transcript_file = video_dir / "transcript.json"
        transcript_data = {
            "text": "Hello world",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "Hello"},
                {"start": 1.0, "end": 2.0, "text": "world"}
            ]
        }
        transcript_file.write_text(json.dumps(transcript_data))
        
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.touch()
        
        result = load_transcript(str(video_file))
        assert result == transcript_data

    def test_load_transcript_not_dict(self, tmp_path):
        """Test returns None for non-dict JSON (e.g., list)"""
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        transcript_file = video_dir / "transcript.json"
        # Write a list instead of dict
        transcript_file.write_text('[1, 2, 3]')
        
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.touch()
        
        result = load_transcript(str(video_file))
        assert result is None

    def test_load_transcript_malformed_json(self, tmp_path):
        """Test returns None for bad JSON"""
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        transcript_file = video_dir / "transcript.json"
        transcript_file.write_text('{invalid json}')
        
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.touch()
        
        result = load_transcript(str(video_file))
        assert result is None

    def test_load_transcript_adds_missing_fields(self, tmp_path):
        """Test adds text/segments if missing"""
        video_dir = tmp_path / "uploads" / "video_name"
        video_dir.mkdir(parents=True)
        transcript_file = video_dir / "transcript.json"
        # Write transcript without text or segments
        transcript_file.write_text('{"language": "en"}')
        
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.touch()
        
        result = load_transcript(str(video_file))
        assert result is not None
        assert "text" in result
        assert result["text"] == ""
        assert "segments" in result
        assert result["segments"] == []

    def test_load_transcript_not_found(self, tmp_path):
        """Test returns None when transcript file doesn't exist"""
        video_file = tmp_path / "uploads" / "video_name.mp4"
        video_file.parent.mkdir(parents=True)
        video_file.touch()
        
        result = load_transcript(str(video_file))
        assert result is None


class TestGetTranscriptSegmentsWithEndTimes:
    """Tests for get_transcript_segments_with_end_times function"""

    def test_get_transcript_segments_with_end_times_basic(self):
        """Test segments get end times"""
        transcript_data = {
            "text": "Hello world",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "Hello"},
                {"start": 1.0, "end": 2.0, "text": "world"}
            ]
        }
        
        result = get_transcript_segments_with_end_times(transcript_data)
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 1.0
        assert result[1]["start"] == 1.0
        assert result[1]["end"] == 2.0

    def test_get_transcript_segments_with_end_times_missing_end(self):
        """Test calculates end from next segment"""
        transcript_data = {
            "text": "Hello world",
            "segments": [
                {"start": 0.0, "text": "Hello"},  # Missing end
                {"start": 1.0, "end": 2.0, "text": "world"}
            ]
        }
        
        result = get_transcript_segments_with_end_times(transcript_data)
        assert len(result) == 2
        # First segment should get end from next segment's start
        assert result[0]["end"] == 1.0
        assert result[1]["end"] == 2.0

    def test_get_transcript_segments_with_end_times_last_segment(self):
        """Test adds 5s default for last segment"""
        transcript_data = {
            "text": "Hello",
            "segments": [
                {"start": 0.0, "text": "Hello"}  # Last segment, missing end
            ]
        }
        
        result = get_transcript_segments_with_end_times(transcript_data)
        assert len(result) == 1
        assert result[0]["end"] == 5.0  # start + 5.0 default

    def test_get_transcript_segments_with_end_times_invalid_entries(self):
        """Test skips non-dict entries"""
        transcript_data = {
            "text": "Test",
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "Valid"},
                "invalid_string_entry",  # Should be skipped
                123,  # Should be skipped
                {"start": 1.0, "end": 2.0, "text": "Another valid"}
            ]
        }
        
        result = get_transcript_segments_with_end_times(transcript_data)
        assert len(result) == 2  # Only the two dict entries
        assert result[0]["text"] == "Valid"
        assert result[1]["text"] == "Another valid"

    def test_get_transcript_segments_with_end_times_empty(self):
        """Test empty segments returns empty list"""
        # Test with empty segments
        transcript_data = {"text": "", "segments": []}
        result = get_transcript_segments_with_end_times(transcript_data)
        assert result == []
        
        # Test with no segments key
        transcript_data2 = {"text": "test"}
        result2 = get_transcript_segments_with_end_times(transcript_data2)
        assert result2 == []
        
        # Test with None
        result3 = get_transcript_segments_with_end_times(None)
        assert result3 == []

    def test_get_transcript_segments_with_end_times_missing_start(self):
        """Test adds default start if missing"""
        transcript_data = {
            "text": "Test",
            "segments": [
                {"text": "Hello"},  # Missing start
                {"start": 1.0, "text": "World"}
            ]
        }
        
        result = get_transcript_segments_with_end_times(transcript_data)
        assert len(result) == 2
        assert result[0]["start"] == 0.0  # Default
        assert result[0]["end"] == 1.0  # From next segment's start
        assert result[1]["start"] == 1.0
        assert result[1]["end"] == 6.0  # start + 5.0 (last segment)