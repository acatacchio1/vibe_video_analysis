"""Test jobs blueprint routes"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.mark.unit
@pytest.mark.api
class TestJobsAPI:
    def test_list_jobs_empty(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_manager.get_all_jobs.return_value = []

        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []

    def test_list_jobs_returns_job_list(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_job = MagicMock()
        mock_job.to_dict.return_value = {
            "job_id": "test_job_123",
            "status": "running",
            "provider_type": "ollama",
            "model_id": "llava:7b",
        }
        mock_manager.get_all_jobs.return_value = [mock_job]

        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["job_id"] == "test_job_123"

    def test_running_jobs(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_job = MagicMock()
        mock_job.to_dict.return_value = {"job_id": "running_1", "status": "running"}
        mock_manager.get_running_jobs.return_value = [mock_job]

        resp = client.get("/api/jobs/running")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["job_id"] == "running_1"

    def test_queued_jobs(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_job = MagicMock()
        mock_job.to_dict.return_value = {"job_id": "queued_1", "status": "queued"}
        mock_manager.get_queued_jobs.return_value = [mock_job]

        resp = client.get("/api/jobs/queued")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["job_id"] == "queued_1"

    def test_get_job_found(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_manager.get_job.return_value = MagicMock(
            job_id="test_job_123",
            to_dict=MagicMock(return_value={"job_id": "test_job_123", "status": "running"})
        )

        resp = client.get("/api/jobs/test_job_123")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["job_id"] == "test_job_123"

    def test_get_job_not_found(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_manager.get_job.return_value = None

        resp = client.get("/api/jobs/nonexistent")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_get_job_frames_empty(self, client, app, temp_job_with_results):
        resp = client.get(f"/api/jobs/{temp_job_with_results['job_dir'].name}/frames")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_get_job_frames_with_pagination(self, client, app, temp_job_with_results):
        job_id = temp_job_with_results["job_dir"].name
        resp = client.get(f"/api/jobs/{job_id}/frames?limit=1&offset=0")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) <= 1

    def test_get_job_frames_no_file(self, client, app):
        resp = client.get("/api/jobs/nonexistent_frames_job/frames")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []

    def test_get_job_results_not_found(self, client, app):
        resp = client.get("/api/jobs/nonexistent_job/results")
        assert resp.status_code == 404
        data = resp.get_json()
        assert "error" in data

    def test_get_job_results_success(self, client, app, temp_job_with_results, tmp_path):
        job_id = temp_job_with_results["job_dir"].name
        jobs_parent = temp_job_with_results["job_dir"].parent
        with patch("src.api.jobs.Path") as mock_path:
            def path_side_effect(*args, **kwargs):
                if args == ("jobs",):
                    return jobs_parent
                if len(args) >= 1 and args[0] == jobs_parent:
                    return Path(*args, **kwargs)
                return Path(*args, **kwargs)
            mock_path.side_effect = path_side_effect
            resp = client.get(f"/api/jobs/{job_id}/results")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "metadata" in data
            assert data["metadata"]["job_id"] == "test_job_123"

    def test_cancel_job_success(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_manager.cancel_job.return_value = True

        with patch("src.api.jobs.os.killpg"), \
             patch("src.api.jobs.os.kill"):
            resp = client.delete("/api/jobs/test_job_123")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            mock_manager.cancel_job.assert_called_once_with("test_job_123")

    def test_cancel_job_failure(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_manager.cancel_job.return_value = False

        with patch("src.api.jobs.os.killpg"), \
             patch("src.api.jobs.os.kill"):
            resp = client.delete("/api/jobs/test_job_456")
            assert resp.status_code == 400
            data = resp.get_json()
            assert "error" in data

    def test_update_priority(self, client, app):
        mock_manager = app.config["_mock_vram_manager"]
        mock_manager.update_priority.return_value = True

        resp = client.post("/api/jobs/test_job_123/priority", json={"priority": 5})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        mock_manager.update_priority.assert_called_once_with("test_job_123", 5)
