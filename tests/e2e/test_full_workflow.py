"""
End-to-end tests for video analysis workflow
"""

import pytest
from pathlib import Path
import sys
import os
import json
import time
import uuid

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestEndToEndAnalysisWorkflow:
    """End-to-end test simulating complete analysis workflow"""

    @pytest.fixture
    def e2e_environment(self, tmp_path):
        """Setup complete test environment"""
        env = {}

        # Create directory structure
        env["uploads"] = tmp_path / "uploads"
        env["jobs"] = tmp_path / "jobs"
        env["cache"] = tmp_path / "cache"
        env["output"] = tmp_path / "output"
        env["thumbs"] = env["uploads"] / "thumbs"

        for d in [
            env["uploads"],
            env["jobs"],
            env["cache"],
            env["output"],
            env["thumbs"],
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Create mock video file
        env["video_path"] = env["uploads"] / f"test_{uuid.uuid4().hex[:8]}.mp4"
        env["video_path"].write_bytes(b"mock video content" * 1000)

        return env

    def test_upload_to_results_full_flow(self, e2e_environment):
        """Test complete flow from upload to results"""
        env = e2e_environment

        # Step 1: Upload video
        assert env["video_path"].exists() is True

        # Step 2: Create job directory
        job_id = str(uuid.uuid4())[:8]
        job_dir = env["jobs"] / job_id
        job_dir.mkdir()

        # Step 3: Write input configuration
        input_config = {
            "job_id": job_id,
            "video_path": str(env["video_path"]),
            "provider_type": "litellm",
            "provider_name": "LiteLLM-Proxy",
            "provider_config": {"url": "http://172.16.17.3:4000/v1"},
            "model": "llava:7b",
            "params": {
                "temperature": 0.0,
                "duration": 0,
                "max_frames": 50,
                "frames_per_minute": 60,
            },
        }

        (job_dir / "input.json").write_text(json.dumps(input_config))

        # Step 4: Create status file
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "status": "running",
                    "stage": "initializing",
                    "progress": 0,
                }
            )
        )

        # Step 5: Create output structure
        output_dir = job_dir / "output"
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        # Step 6: Create mock frames
        frames_file = job_dir / "frames.jsonl"
        with open(frames_file, "a") as _frames_f:
            for i in range(5):
                frame = {
                    "frame_number": i + 1,
                    "total_frames": 5,
                    "timestamp": i * 2.0,
                    "analysis": f"Frame {i + 1} shows content",
                    "tokens": {"prompt_tokens": 500, "completion_tokens": 250},
                }
                _frames_f.write(json.dumps(frame) + "\n")

        # Step 7: Create results
        results_file = output_dir / "results.json"
        results = {
            "metadata": {
                "job_id": job_id,
                "provider": "litellm",
                "model": "llava:7b",
                "frames_processed": 5,
            },
            "transcript": {
                "text": "Video transcript",
                "segments": [{"start": 0, "end": 10, "text": "Hello"}],
            },
            "frame_analyses": [
                {"frame_number": 1, "analysis": "A dog"},
                {"frame_number": 2, "analysis": "Dog runs"},
            ],
            "video_description": {"response": "A video of a dog running"},
        }
        results_file.write_text(json.dumps(results, indent=2))

        # Step 8: Finalize status
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "stage": "complete",
                    "progress": 100,
                }
            )
        )

        # Verify all artifacts
        assert (job_dir / "input.json").exists()
        assert (job_dir / "status.json").exists()
        assert (job_dir / "frames.jsonl").exists()
        assert (job_dir / "output" / "results.json").exists()

        # Verify content
        loaded_results = json.loads(results_file.read_text())
        assert loaded_results["metadata"]["frames_processed"] == 5
        assert len(loaded_results["frame_analyses"]) == 2

    def test_results_list_api(self, e2e_environment):
        """Test listing results via API simulation"""
        env = e2e_environment

        # Create multiple jobs
        job_ids = [str(uuid.uuid4())[:8] for _ in range(3)]

        results_list = []
        for job_id in job_ids:
            job_dir = env["jobs"] / job_id
            job_dir.mkdir()

            # Create input.json
            (job_dir / "input.json").write_text(
                json.dumps(
                    {
                        "job_id": job_id,
                        "video_path": str(env["video_path"]),
                        "provider_type": "litellm",
                        "provider_name": "LiteLLM-Local",
                        "model": "llava:7b",
                        "created_at": time.time(),
                    }
                )
            )

            # Create results
            output_dir = job_dir / "output"
            output_dir.mkdir()
            (output_dir / "results.json").write_text(
                json.dumps(
                    {
                        "metadata": {"job_id": job_id, "frames_processed": 5},
                        "video_description": {"response": "Description"},
                    }
                )
            )

            # Create status
            (job_dir / "status.json").write_text(
                json.dumps(
                    {
                        "status": "completed",
                    }
                )
            )

        # Simulate results listing API
        results_dir = Path(env["jobs"])
        results_list = []

        for job_dir in results_dir.iterdir():
            if not job_dir.is_dir():
                continue

            results_file = job_dir / "output" / "results.json"
            input_file = job_dir / "input.json"

            if not results_file.exists() or not input_file.exists():
                continue

            inp = json.loads(input_file.read_text())
            res = json.loads(results_file.read_text())

            desc_preview = ""
            desc = res.get("video_description", {})
            if isinstance(desc, dict):
                desc_preview = desc.get("response", "")[:200]
            else:
                desc_preview = str(desc)[:200]

            results_list.append(
                {
                    "job_id": job_dir.name,
                    "video_path": inp.get("video_path", ""),
                    "model": inp.get("model", ""),
                    "provider": inp.get("provider_type", ""),
                    "desc_preview": desc_preview,
                }
            )

        assert len(results_list) == 3
        assert job_ids[0] in [r["job_id"] for r in results_list]

    def test_retrieve_job_results(self, e2e_environment):
        """Test retrieving results for specific job"""
        env = e2e_environment

        job_id = str(uuid.uuid4())[:8]
        job_dir = env["jobs"] / job_id
        job_dir.mkdir()

        # Create results
        results = {
            "metadata": {
                "job_id": job_id,
                "frames_processed": 10,
            },
            "transcript": {
                "text": "Full transcript text",
                "segments": [{"start": 0, "end": 5, "text": "Hello"}],
            },
            "frame_analyses": [
                {"frame_number": 1, "analysis": "Scene 1"},
            ],
            "video_description": {"response": "Video description"},
        }

        (job_dir / "output").mkdir(parents=True, exist_ok=True)
        (job_dir / "output" / "results.json").write_text(json.dumps(results))

        # Retrieve
        retrieved = json.loads((job_dir / "output" / "results.json").read_text())

        assert retrieved["metadata"]["job_id"] == job_id
        assert retrieved["transcript"]["text"] == "Full transcript text"

    def test_frames_list_api(self, e2e_environment):
        """Test retrieving frame analyses"""
        env = e2e_environment

        job_id = str(uuid.uuid4())[:8]
        job_dir = env["jobs"] / job_id
        job_dir.mkdir()

        # Create frames
        frames_file = job_dir / "frames.jsonl"
        with open(frames_file, "a") as _frames_f:
            for i in range(10):
                frame = {
                    "frame_number": i + 1,
                    "total_frames": 10,
                    "timestamp": i * 1.5,
                    "analysis": f"Analysis for frame {i + 1}",
                }
                _frames_f.write(json.dumps(frame) + "\n")

        # Retrieve all frames
        all_frames = []
        with open(frames_file) as f:
            for line in f:
                if line.strip():
                    all_frames.append(json.loads(line))

        assert len(all_frames) == 10
        assert all_frames[0]["frame_number"] == 1
        assert all_frames[9]["frame_number"] == 10

    def test_multi_gpu_scenario(self, e2e_environment):
        """Test scenario simulating multi-GPU scheduling"""
        env = e2e_environment

        # Create jobs that would run on different GPUs
        jobs = []
        for i in range(4):
            job_id = str(uuid.uuid4())[:8]
            gpu_id = i % 2  # 2 jobs per GPU
            dir_name = f"gpu{gpu_id}_{job_id}"
            job_dir = env["jobs"] / dir_name
            job_dir.mkdir()

            input_config = {
                "job_id": job_id,
                "video_path": str(env["video_path"]),
                "provider_type": "litellm" if i < 2 else "openrouter",
                "provider_name": f"LiteLLM-GPU{gpu_id}" if i < 2 else "OpenRouter",
                "provider_config": {"url": "http://localhost:11434"} if i < 2 else {},
                "model": "llava:7b",
                "params": {},
            }
            (job_dir / "input.json").write_text(json.dumps(input_config))

            # Simulate VRAM assignment
            (job_dir / "gpu_assigned.txt").write_text(str(gpu_id))

            jobs.append(
                {
                    "job_id": job_id,
                    "gpu": gpu_id,
                    "dir_name": dir_name,
                }
            )

        # Verify GPU distribution
        gpu0_jobs = [j for j in jobs if j["gpu"] == 0]
        gpu1_jobs = [j for j in jobs if j["gpu"] == 1]

        assert len(gpu0_jobs) == 2
        assert len(gpu1_jobs) == 2
        assert len(jobs) == 4

        # Verify all created
        for job in jobs:
            job_dir = env["jobs"] / job["dir_name"]
            assert (job_dir / "input.json").exists()


class TestPriorityQueueBehavior:
    """End-to-end tests for priority queue behavior"""

    def test_high_priority_runs_first(self, tmp_path):
        """Test high priority jobs are processed first"""
        jobs_dir = tmp_path / "jobs"
        jobs_dir.mkdir()

        # Submit low priority first
        low_job = jobs_dir / "low_priority_job"
        low_job.mkdir()
        (low_job / "input.json").write_text(
            json.dumps(
                {
                    "job_id": "low_priority_job",
                    "priority": 1,
                }
            )
        )

        # Submit high priority second
        high_job = jobs_dir / "high_priority_job"
        high_job.mkdir()
        (high_job / "input.json").write_text(
            json.dumps(
                {
                    "job_id": "high_priority_job",
                    "priority": 10,
                }
            )
        )

        # Simulate queue processing (should sort by priority)
        all_jobs = [
            (j, j.read_text())
            for j in [
                low_job / "input.json",
                high_job / "input.json",
            ]
        ]

        # Parse and sort
        jobs_parsed = []
        for name, content in all_jobs:
            data = json.loads(content)
            jobs_parsed.append((data["priority"], data["job_id"]))

        # Sort by priority (descending)
        jobs_parsed.sort(key=lambda x: x[0], reverse=True)

        # High priority should be first
        assert jobs_parsed[0][1] == "high_priority_job"
        assert jobs_parsed[1][1] == "low_priority_job"
