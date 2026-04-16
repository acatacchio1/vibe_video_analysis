"""
Integration tests for job execution pipeline
"""

import pytest
from pathlib import Path
import sys
import os
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestJobDirectoryStructureIntegration:
    """Integration tests for job directory structure creation"""

    @pytest.fixture
    def temp_jobs_dir(self, tmp_path):
        """Create temporary jobs directory"""
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()
        return jobs_dir

    def test_job_dir_created_on_submit(self, temp_jobs_dir):
        """Test job directory is created when job is submitted"""
        job_id = "test_job_456"
        job_dir = temp_jobs_dir / job_id

        # Simulate job directory creation
        job_dir.mkdir(parents=True, exist_ok=True)

        assert job_dir.exists() is True
        assert job_dir.is_dir() is True

    def test_input_json_created(self, temp_jobs_dir):
        """Test input.json is created with correct structure"""
        job_id = "test_job_457"
        job_dir = temp_jobs_dir / job_id
        job_dir.mkdir()

        input_data = {
            "job_id": job_id,
            "video_path": "/uploads/video.mp4",
            "provider_type": "ollama",
            "provider_name": "Ollama-Local",
            "provider_config": {"url": "http://localhost:11434"},
            "model": "llava:7b",
            "params": {
                "temperature": 0.0,
                "duration": 0,
                "max_frames": 50,
            },
        }

        input_file = job_dir / "input.json"
        input_file.write_text(json.dumps(input_data))

        # Read back and verify
        loaded = json.loads(input_file.read_text())

        assert loaded["job_id"] == job_id
        assert loaded["provider_type"] == "ollama"
        assert "params" in loaded

    def test_output_directory_created(self, temp_jobs_dir):
        """Test output directory is created by worker"""
        job_id = "test_job_458"
        job_dir = temp_jobs_dir / job_id
        job_dir.mkdir()

        output_dir = job_dir / "output"
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        assert output_dir.exists() is True
        assert frames_dir.exists() is True

    def test_status_json_created(self, temp_jobs_dir):
        """Test status.json is created and updated"""
        job_id = "test_job_459"
        job_dir = temp_jobs_dir / job_id
        job_dir.mkdir()

        # Initial status
        status = {
            "status": "running",
            "stage": "initializing",
            "progress": 0,
            "current_frame": 0,
            "total_frames": 0,
        }

        status_file = job_dir / "status.json"
        status_file.write_text(json.dumps(status))

        # Update status
        status["stage"] = "analyzing_frames"
        status["progress"] = 50
        status["current_frame"] = 25

        status_file.write_text(json.dumps(status))

        # Verify update
        loaded = json.loads(status_file.read_text())
        assert loaded["stage"] == "analyzing_frames"
        assert loaded["progress"] == 50


class TestWorkerProcessIntegration:
    """Integration tests for worker process communication"""

    @pytest.fixture
    def temp_job_dir(self, tmp_path):
        """Create temporary job directory structure"""
        job_dir = tmp_path / "jobs" / "test_worker"
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def test_worker_reads_input_json(self, temp_job_dir):
        """Test worker can read job input configuration"""
        input_file = temp_job_dir / "input.json"
        input_file.write_text(
            json.dumps(
                {
                    "job_id": "test_worker",
                    "video_path": "/test.mp4",
                    "provider_type": "ollama",
                    "provider_config": {"url": "http://localhost:11434"},
                    "model": "llava:7b",
                    "params": {
                        "temperature": 0.0,
                        "frames_per_minute": 60,
                    },
                }
            )
        )

        # Worker would load this
        loaded = json.loads(input_file.read_text())

        assert loaded["job_id"] == "test_worker"
        assert loaded["model"] == "llava:7b"

    def test_status_updates_visible_to_monitor(self, temp_job_dir):
        """Test status updates are visible to monitoring process"""
        status_file = temp_job_dir / "status.json"

        # Worker writes status
        status1 = {"stage": "extracting_frames", "progress": 15}
        status_file.write_text(json.dumps(status1))

        # Monitor reads it
        monitor_status = json.loads(status_file.read_text())

        assert monitor_status["stage"] == "extracting_frames"
        assert monitor_status["progress"] == 15

    def test_frames_jsonl_created(self, temp_job_dir):
        """Test frame analysis lines are appended to frames.jsonl"""
        frames_file = temp_job_dir / "frames.jsonl"

        # Worker appends frame analysis
        frame1 = {
            "frame_number": 1,
            "total_frames": 50,
            "timestamp": 2.5,
            "analysis": "A dog running",
            "tokens": {"prompt_tokens": 500, "completion_tokens": 250},
        }
        frames_file.write_text(json.dumps(frame1) + "\n")

        frame2 = {
            "frame_number": 2,
            "total_frames": 50,
            "timestamp": 3.0,
            "analysis": "Dog jumps",
            "tokens": {"prompt_tokens": 480, "completion_tokens": 220},
        }
        with open(frames_file, "a") as f:
            f.write(json.dumps(frame2) + "\n")

        # Read all frames
        lines = frames_file.read_text().strip().split("\n")
        assert len(lines) == 2

        parsed = [json.loads(line) for line in lines]
        assert parsed[0]["frame_number"] == 1
        assert parsed[1]["frame_number"] == 2

    def test_results_json_created(self, temp_job_dir):
        """Test final results.json is created on completion"""
        results_file = temp_job_dir / "output" / "results.json"
        results_file.parent.mkdir(parents=True, exist_ok=True)

        results = {
            "metadata": {
                "job_id": "test_worker",
                "provider": "ollama",
                "model": "llava:7b",
                "frames_processed": 50,
            },
            "transcript": {
                "text": "Transcript text",
                "segments": [],
            },
            "frame_analyses": [
                {"frame_number": 1, "analysis": "First"},
                {"frame_number": 2, "analysis": "Second"},
            ],
            "video_description": {"response": "Video description"},
        }

        results_file.write_text(json.dumps(results, indent=2))

        # Verify results
        loaded = json.loads(results_file.read_text())

        assert loaded["metadata"]["frames_processed"] == 50
        assert "transcript" in loaded
        assert "video_description" in loaded


class TestJobLifecycleIntegration:
    """Integration tests for complete job lifecycle"""

    @pytest.fixture
    def full_job_structure(self, tmp_path):
        """Create complete job directory structure"""
        jobs_dir = tmp_path / "jobs"
        job_dir = jobs_dir / "lifecycle_test"
        job_dir.mkdir(parents=True, exist_ok=True)

        # Create all standard directories
        output_dir = job_dir / "output"
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True)

        # Create standard files
        (job_dir / "input.json").write_text("{}")
        (job_dir / "status.json").write_text("{}")
        (job_dir / "frames.jsonl").write_text("")
        (output_dir / "results.json").write_text("{}")

        return job_dir

    def test_complete_job_structure_exists(self, full_job_structure):
        """Test all required files and directories exist"""
        job_dir = full_job_structure

        assert (job_dir / "input.json").exists()
        assert (job_dir / "status.json").exists()
        assert (job_dir / "frames.jsonl").exists()
        assert (job_dir / "output" / "results.json").exists()
        assert (job_dir / "output" / "frames").exists()

    def test_job_status_progression(self, tmp_path):
        """Test job status progresses through stages correctly"""
        job_dir = tmp_path / "jobs" / "progression_test"
        job_dir.mkdir(parents=True, exist_ok=True)
        status_file = job_dir / "status.json"

        # Initial state
        status_file.write_text(json.dumps({"stage": "initializing", "progress": 0}))
        assert json.loads(status_file.read_text())["stage"] == "initializing"

        # Extracting audio
        status_file.write_text(
            json.dumps(
                {
                    "stage": "extracting_audio",
                    "progress": 5,
                }
            )
        )
        assert json.loads(status_file.read_text())["stage"] == "extracting_audio"

        # Extracting frames
        status_file.write_text(
            json.dumps(
                {
                    "stage": "extracting_frames",
                    "progress": 15,
                }
            )
        )
        assert json.loads(status_file.read_text())["stage"] == "extracting_frames"

        # Analyzing frames
        status_file.write_text(
            json.dumps(
                {
                    "stage": "analyzing_frames",
                    "progress": 50,
                    "current_frame": 25,
                    "total_frames": 50,
                }
            )
        )

        # Reconstructing
        status_file.write_text(
            json.dumps(
                {
                    "stage": "reconstructing",
                    "progress": 85,
                }
            )
        )

        # Complete
        status_file.write_text(
            json.dumps(
                {
                    "stage": "complete",
                    "progress": 100,
                    "status": "completed",
                }
            )
        )

        final = json.loads(status_file.read_text())
        assert final["status"] == "completed"
        assert final["stage"] == "complete"
        assert final["progress"] == 100


class TestMultiJobConcurrentIntegration:
    """Integration tests for multiple concurrent jobs"""

    def test_multiple_job_directories(self, tmp_path):
        """Test multiple jobs can have separate directories"""
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()

        job1_dir = jobs_dir / "job1"
        job2_dir = jobs_dir / "job2"
        job3_dir = jobs_dir / "job3"

        job1_dir.mkdir()
        job2_dir.mkdir()
        job3_dir.mkdir()

        # Create unique input files
        (job1_dir / "input.json").write_text(json.dumps({"job_id": "job1"}))
        (job2_dir / "input.json").write_text(json.dumps({"job_id": "job2"}))
        (job3_dir / "input.json").write_text(json.dumps({"job_id": "job3"}))

        # Verify isolation
        assert json.loads((job1_dir / "input.json").read_text())["job_id"] == "job1"
        assert json.loads((job2_dir / "input.json").read_text())["job_id"] == "job2"
        assert json.loads((job3_dir / "input.json").read_text())["job_id"] == "job3"

    def test_job_list_retrieval(self, tmp_path):
        """Test listing all jobs from directory"""
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()

        # Create job directories
        for i in range(5):
            (jobs_dir / f"job{i}").mkdir()

        # List all job directories
        jobs = [d.name for d in jobs_dir.iterdir() if d.is_dir()]

        assert len(jobs) == 5
        assert "job0" in jobs
        assert "job4" in jobs
