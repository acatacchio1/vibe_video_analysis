"""
Test videos API blueprint
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest

# Blueprint imports removed: happen at pytest collection time before fixtures inject mocks


@pytest.mark.unit
@pytest.mark.api
@pytest.mark.api
class TestVideosAPI:
    """Test videos API endpoints"""

    def test_list_videos_empty(self, client, app, tmp_path):
        """GET /api/videos with no videos returns empty lists"""
        import src.api.videos as videos_module

        with patch.object(videos_module.Path, "glob", return_value=[]):
            response = client.get("/api/videos")
            assert response.status_code == 200
            data = response.get_json()
            assert "source_videos" in data
            assert "processed_videos" in data
            assert data["source_videos"] == []
            assert data["processed_videos"] == []

    def test_delete_video_not_found(self, client, app):
        """DELETE /api/videos/<filename> returns 404 for non-existent video"""
        response = client.delete("/api/videos/nonexistent.mp4")
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data

    def test_get_video_frames_meta(self, client, app, temp_video_with_frames):
        """GET /api/videos/<filename>/frames returns frame metadata"""
        video_data = temp_video_with_frames
        
        # Mock get_video_directory to return our temp directory
        with patch("src.api.videos.get_video_directory") as mock_get_dir:
            mock_get_dir.return_value = video_data["video_dir"]
            
            response = client.get("/api/videos/test_video.mp4/frames")
            assert response.status_code == 200
            data = response.get_json()
            assert "frame_count" in data
            assert data["frame_count"] == 5
            assert "fps" in data
            assert data["fps"] == 1.0
            assert "duration" in data
            assert data["duration"] == 5.0

    def test_get_video_frames_index(self, client, app, temp_video_with_frames):
        """GET /api/videos/<filename>/frames_index returns frame timestamp index"""
        video_data = temp_video_with_frames
        
        with patch("src.api.videos.get_video_directory") as mock_get_dir:
            mock_get_dir.return_value = video_data["video_dir"]
            
            response = client.get("/api/videos/test_video.mp4/frames_index")
            assert response.status_code == 200
            data = response.get_json()
            assert isinstance(data, dict)
            assert len(data) == 5
            assert data["1"] == 0.0
            assert data["5"] == 4.0

    def test_get_video_transcript(self, client, app, temp_video_with_frames):
        """GET /api/videos/<filename>/transcript returns transcript data"""
        video_data = temp_video_with_frames
        
        with patch("src.api.videos.get_video_directory") as mock_get_dir:
            mock_get_dir.return_value = video_data["video_dir"]
            
            response = client.get("/api/videos/test_video.mp4/transcript")
            assert response.status_code == 200
            data = response.get_json()
            assert "text" in data
            assert data["text"] == "Hello world test transcript"
            assert "segments" in data
            assert len(data["segments"]) == 2

    def test_get_video_transcript_not_found(self, client, app, temp_video_with_frames):
        """GET /api/videos/<filename>/transcript returns empty transcript when file doesn't exist"""
        video_data = temp_video_with_frames
        
        with patch("src.api.videos.get_video_directory") as mock_get_dir:
            mock_get_dir.return_value = video_data["video_dir"]
            
            # Delete transcript file
            (video_data["video_dir"] / "transcript.json").unlink()
            
            response = client.get("/api/videos/test_video.mp4/transcript")
            assert response.status_code == 200
            data = response.get_json()
            assert data == {"segments": [], "text": "", "language": None, "whisper_model": None}

    def test_get_video_frame_not_found(self, client, app, temp_video_with_frames):
        """GET /api/videos/<filename>/frames/<n> returns 404 for non-existent frame"""
        video_data = temp_video_with_frames
        
        with patch("src.api.videos.get_video_directory") as mock_get_dir:
            mock_get_dir.return_value = video_data["video_dir"]
            
            response = client.get("/api/videos/test_video.mp4/frames/999")
            assert response.status_code == 404
            data = response.get_json()
            assert "error" in data

    def test_get_video_frame_thumb_fallback(self, client, app, temp_video_with_frames):
        """GET /api/videos/<filename>/frames/<n>/thumb falls back to full frame if no thumb"""
        video_data = temp_video_with_frames
        
        with patch("src.api.videos.get_video_directory") as mock_get_dir:
            mock_get_dir.return_value = video_data["video_dir"]
            
            # Delete thumb file
            thumb_path = video_data["thumbs_dir"] / "thumb_000001.jpg"
            thumb_path.unlink()
            
            # Mock send_file to capture what would be sent
            with patch("src.api.videos.send_file") as mock_send_file:
                mock_send_file.return_value = MagicMock()
                
                response = client.get("/api/videos/test_video.mp4/frames/1/thumb")
                # Should still return 200, just falls back to full frame
                assert response.status_code == 200

    def test_get_thumbnail_not_found(self, client, app):
        """GET /api/thumbnail/<filename> returns 404 when thumbnail doesn't exist"""
        # Mock get_thumbnail_path to return non-existent path
        with patch("src.api.videos.get_thumbnail_path") as mock_get_thumb:
            mock_get_thumb.return_value = "/nonexistent/path.jpg"
            
            response = client.get("/api/thumbnail/test_video.mp4")
            assert response.status_code == 404
            data = response.get_json()
            assert "error" in data

    def test_upload_video_no_file(self, client, app):
        """POST /api/videos/upload with no file returns error"""
        response = client.post("/api/videos/upload")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_upload_video_empty_filename(self, client, app):
        """POST /api/videos/upload with empty filename returns error"""
        # Create a mock file upload with empty filename
        data = {"file": (b"", "")}  # Empty filename
        
        response = client.post(
            "/api/videos/upload",
            data=data,
            content_type="multipart/form-data"
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_delete_all_source_videos(self, client, app, tmp_path):
        """DELETE /api/videos/source/all deletes all source videos"""
        # Directly patch upload_dir.glob to return our test files
        import src.api.videos as videos_module
        
        # Create test directory and files
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir(exist_ok=True)
        
        # Create source videos
        (uploads_dir / "video1.mp4").write_bytes(b"test1")
        (uploads_dir / "video2_720p.mp4").write_bytes(b"test2")
        
        # Create a processed video (should not be deleted)
        (uploads_dir / "video3_dedup.mp4").write_bytes(b"test3")
        
        # Mock the upload directory glob to return our test files
        test_files = [uploads_dir / "video1.mp4", uploads_dir / "video2_720p.mp4", uploads_dir / "video3_dedup.mp4"]
        
        with patch.object(videos_module.Path, "glob") as mock_glob:
            mock_glob.return_value = test_files
            
            # Mock the _delete_one_video function to track calls
            calls = []
            
            def mock_delete(filepath, base):
                calls.append(filepath.name)
                return {"success": True}
            
            videos_module._delete_one_video = mock_delete
            
            response = client.delete("/api/videos/source/all")
            assert response.status_code == 200
            data = response.get_json()
            assert data["deleted"] == 2  # Only source videos
            assert "video1.mp4" in calls
            assert "video2_720p.mp4" in calls
            assert "video3_dedup.mp4" not in calls  # Processed video should not be deleted

    def test_delete_all_processed_videos(self, client, app, tmp_path):
        """DELETE /api/videos/processed/all deletes all processed videos"""
        # Directly patch upload_dir.glob to return our test files
        import src.api.videos as videos_module
        
        # Create test directory and files
        uploads_dir = tmp_path / "uploads"
        uploads_dir.mkdir(exist_ok=True)
        
        # Create processed videos
        (uploads_dir / "video1_dedup.mp4").write_bytes(b"test1")
        (uploads_dir / "video2_dedup.mp4").write_bytes(b"test2")
        
        # Create a source video (should not be deleted)
        (uploads_dir / "video3.mp4").write_bytes(b"test3")
        
        # Mock the upload directory glob to return our test files
        test_files = [uploads_dir / "video1_dedup.mp4", uploads_dir / "video2_dedup.mp4", uploads_dir / "video3.mp4"]
        
        with patch.object(videos_module.Path, "glob") as mock_glob:
            mock_glob.return_value = test_files
            
            # Mock the _delete_one_video function to track calls
            calls = []
            
            def mock_delete(filepath, base):
                calls.append(filepath.name)
                return {"success": True}
            
            videos_module._delete_one_video = mock_delete
            
            response = client.delete("/api/videos/processed/all")
            assert response.status_code == 200
            data = response.get_json()
            assert data["deleted"] == 2  # Only processed videos
            assert "video1_dedup.mp4" in calls
            assert "video2_dedup.mp4" in calls
            assert "video3.mp4" not in calls  # Source video should not be deleted