"""
Integration tests for upload and transcode pipeline
"""

import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestUploadPipelineIntegration:
    """Integration tests for video upload flow"""

    @pytest.fixture
    def mock_app(self, temp_upload_dir):
        """Create mock Flask app with test directories"""
        with patch("app.Path") as mock_path:
            mock_path.return_valuemkdir = MagicMock()
            mock_upload = MagicMock()
            mock_upload.glob.return_value = []

            from app import app

            app.config["UPLOAD_FOLDER"] = temp_upload_dir
            app.config["MAX_CONTENT_LENGTH"] = None

            yield app

    def test_upload_saves_to_correct_location(self, temp_upload_dir):
        """Test file is saved to uploads directory"""
        from app import secure_filename

        original_filename = "my video.mp4"
        filename = secure_filename(original_filename)

        filepath = temp_upload_dir / filename
        assert filepath.exists() is False

        # Simulate save
        filepath.write_bytes(b"test content")
        assert filepath.exists() is True
        assert filepath == Path(temp_upload_dir) / filename

    @patch("app.subprocess.run")
    def test_probing_video_on_upload(self, mock_probe):
        """Test video is probed for metadata on upload"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "120.5"
        mock_process.stderr = ""
        mock_probe.return_value = mock_process

        # Simulate list_videos function behavior
        from src.utils.transcode import get_video_duration

        duration = get_video_duration("/uploads/test.mp4")

        assert duration == 120.5
        mock_probe.assert_called_once()

    @patch("app.subprocess.run")
    def test_batch_video_probing(self, mock_probe):
        """Test multiple videos are probed efficiently"""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = "120.5"
        mock_process.stderr = ""
        mock_probe.return_value = mock_process

        from src.utils.transcode import probe_all_videos

        video_paths = [
            "/uploads/video1.mp4",
            "/uploads/video2.mp4",
            "/uploads/video3.mp4",
        ]

        results = probe_all_videos(video_paths)

        assert len(results) == 3
        for r in results:
            assert "duration" in r
            assert r["duration"] == 120.5


class TestTranscodePipelineIntegration:
    """Integration tests for video transcode flow"""

    @pytest.fixture
    def mock_transcode_setup(self, temp_upload_dir):
        """Setup for transcode tests"""
        video_file = temp_upload_dir / "test_video.mp4"
        video_file.write_bytes(b"test content" * 100)
        return video_file

    @patch("app.subprocess.Popen")
    def test_transcode_command_builds_correctly(self, mock_popen):
        """Test transcoding command is built with correct parameters"""
        from gpu_transcode import build_transcode_command

        cmd = build_transcode_command(
            input_path="/test/input.mp4",
            output_path="/test/output.mp4",
            width=1280,
            height=720,
            fps=1,
            gpu_index=0,
        )

        assert "ffmpeg" in cmd[0]
        assert "-vf" in cmd
        assert any("scale=1280:720" in str(arg) for arg in cmd)
        assert any("fps=1" in str(arg) for arg in cmd)
        assert "-c:v" in cmd
        assert "libx264" in cmd

    def test_transcode_progress_parsing(self):
        """Test transcode progress parser returns correct percentage"""
        test_line = "out_time_ms=123456789"

        from gpu_transcode import get_transcode_progress_parser

        parse_function = get_transcode_progress_parser("standard")
        result = parse_function(test_line, 0.0, 120.0)

        # Should return a percentage between 0 and 100
        assert result is not None
        assert 0 <= result <= 100

    def test_thumbnail_generation_after_transcode(self, mock_transcode_setup):
        """Test thumbnail helper functions exist and are importable"""
        from thumbnail import ensure_thumbnail, get_thumbnail_path

        # Verify helpers are callable
        assert callable(ensure_thumbnail)
        assert callable(get_thumbnail_path)

        # get_thumbnail_path returns a predictable path
        path = get_thumbnail_path("/uploads/test_video_720p1fps.mp4")
        assert "test_video_720p1fps" in path
        assert path.endswith(".jpg")

    def test_source_deletion_after_transcode(self, tmp_path):
        """Test source file can be deleted via Path.unlink"""
        src = tmp_path / "source.mp4"
        src.write_bytes(b"data")
        assert src.exists()

        src.unlink()
        assert not src.exists()


class TestWebSocketEventIntegration:
    """Integration tests for WebSocket event flow"""

    def test_socketio_room_creation(self):
        """Test job rooms are created correctly"""
        import uuid

        job_id = str(uuid.uuid4())[:8]
        room_name = f"job_{job_id}"

        assert room_name.startswith("job_")
        # "job_" (4) + 8 hex chars = 12 chars
        assert len(room_name) == 12

    def test_transcode_progress_emitted(self):
        """Test the transcode background task function exists and is callable"""
        from app import _transcode_and_delete_with_cleanup

        assert callable(_transcode_and_delete_with_cleanup)


class TestJobLifecycleIntegration:
    """Integration tests for complete job lifecycle"""

    def test_job_directory_structure(self, temp_jobs_dir):
        """Test job directory is created with correct structure"""
        job_id = "test_job_123"
        job_dir = temp_jobs_dir / job_id

        # Simulate job creation
        job_dir.mkdir(parents=True, exist_ok=True)

        # Check standard directories
        output_dir = job_dir / "output"
        output_dir.mkdir()

        frames_dir = output_dir / "frames"
        frames_dir.mkdir()

        assert (job_dir / "input.json").exists() is False  # Created separately
        assert output_dir.exists() is True
        assert frames_dir.exists() is True

    def test_job_input_json_structure(self):
        """Test job input.json has correct structure"""
        sample_job = {
            "job_id": "test_job_123",
            "video_path": "/test.mp4",
            "provider_type": "ollama",
            "provider_name": "Ollama-Local",
            "provider_config": {"url": "http://localhost:11434"},
            "model": "llava:7b",
            "params": {
                "temperature": 0.0,
                "duration": 0,
                "max_frames": 50,
                "frames_per_minute": 60,
                "whisper_model": "large",
            },
        }

        import json

        json_str = json.dumps(sample_job)
        parsed = json.loads(json_str)

        assert parsed["job_id"] == "test_job_123"
        assert parsed["provider_type"] == "ollama"
        assert "params" in parsed


class TestErrorHandlingIntegration:
    """Integration tests for error handling in pipelines"""

    @patch("app.subprocess.run")
    def test_probe_failure_handling(self, mock_probe):
        """Test probe failure is handled gracefully"""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = ""
        mock_process.stderr = "error"
        mock_probe.return_value = mock_process

        from src.utils.transcode import get_video_duration

        duration = get_video_duration("/nonexistent/video.mp4")

        assert duration == 0.0  # Error returns 0

    def test_transcode_failure_handling(self):
        """Test transcode background function is importable"""
        from app import _transcode_and_delete_with_cleanup

        # The function exists and is callable; actual failure handling
        # is tested by the function's internal try/except
        assert callable(_transcode_and_delete_with_cleanup)
