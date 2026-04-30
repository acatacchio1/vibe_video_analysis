"""
Test LLM API blueprint
"""
import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


@pytest.mark.unit
@pytest.mark.api
class TestLLMAPI:
    """Test LLM API endpoints"""

    def test_llm_chat_success(self, client, app):
        """POST /api/llm/chat with valid data returns job_id"""
        mock_chat_queue = app.config["_mock_chat_queue_manager"]
        mock_chat_queue.submit_job.return_value = "chat_abc12345"

        response = client.post(
            "/api/llm/chat",
            json={
                "provider_type": "litellm",
                "model": "qwen3-27b-q8",
                "prompt": "Test prompt",
                "temperature": 0.1,
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["job_id"] == "chat_abc12345"
        assert "message" in data
        mock_chat_queue.submit_job.assert_called_once()

    def test_llm_chat_missing_model(self, client, app):
        """POST /api/llm/chat without model returns 400"""
        response = client.post(
            "/api/llm/chat",
            json={
                "provider_type": "litellm",
                "prompt": "Test prompt",
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Model is required" in data["error"]

    def test_llm_chat_missing_prompt_and_content(self, client, app):
        """POST /api/llm/chat without prompt or content returns 400"""
        response = client.post(
            "/api/llm/chat",
            json={
                "provider_type": "litellm",
                "model": "qwen3-27b-q8",
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Prompt or content is required" in data["error"]

    def test_llm_chat_openrouter_no_key(self, client, app):
        """POST /api/llm/chat for OpenRouter without API key returns 400"""
        # Mock get_openrouter_api_key to return None
        with patch("src.api.llm.get_openrouter_api_key") as mock_get_key:
            mock_get_key.return_value = None

            response = client.post(
                "/api/llm/chat",
                json={
                    "provider_type": "openrouter",
                    "model": "openai/gpt-4",
                    "prompt": "Test prompt",
                },
            )
            assert response.status_code == 400
            data = response.get_json()
            assert "error" in data
            assert "OpenRouter API key not configured" in data["error"]

    def test_llm_chat_value_error(self, client, app):
        """POST /api/llm/chat handles ValueError from queue manager (400)"""
        mock_chat_queue = app.config["_mock_chat_queue_manager"]
        mock_chat_queue.submit_job.side_effect = ValueError("Invalid parameters")

        response = client.post(
            "/api/llm/chat",
            json={
                "provider_type": "litellm",
                "model": "qwen3-27b-q8",
                "prompt": "Test prompt",
            },
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Invalid parameters" in data["error"]

    def test_llm_chat_generic_error(self, client, app):
        """POST /api/llm/chat handles generic exceptions (500)"""
        mock_chat_queue = app.config["_mock_chat_queue_manager"]
        mock_chat_queue.submit_job.side_effect = RuntimeError("Something went wrong")

        response = client.post(
            "/api/llm/chat",
            json={
                "provider_type": "litellm",
                "model": "qwen3-27b-q8",
                "prompt": "Test prompt",
            },
        )
        assert response.status_code == 500
        data = response.get_json()
        assert "error" in data
        assert "Internal error" in data["error"]

    def test_llm_chat_status_found(self, client, app):
        """GET /api/llm/chat/<id> returns job status"""
        mock_chat_queue = app.config["_mock_chat_queue_manager"]
        mock_chat_queue.get_job_status.return_value = {
            "job_id": "chat_abc12345",
            "status": "pending",
            "queue_position": 1,
        }

        response = client.get("/api/llm/chat/chat_abc12345")
        assert response.status_code == 200
        data = response.get_json()
        assert data["job_id"] == "chat_abc12345"
        assert data["status"] == "pending"
        mock_chat_queue.get_job_status.assert_called_once_with("chat_abc12345")

    def test_llm_chat_status_not_found(self, client, app):
        """GET /api/llm/chat/<id> returns 404 for non-existent job"""
        mock_chat_queue = app.config["_mock_chat_queue_manager"]
        mock_chat_queue.get_job_status.return_value = None

        response = client.get("/api/llm/chat/nonexistent")
        assert response.status_code == 404
        data = response.get_json()
        assert "error" in data
        mock_chat_queue.get_job_status.assert_called_once_with("nonexistent")

    def test_cancel_llm_chat(self, client, app):
        """DELETE /api/llm/chat/<id> cancels job"""
        mock_chat_queue = app.config["_mock_chat_queue_manager"]
        mock_chat_queue.cancel_job.return_value = True

        response = client.delete("/api/llm/chat/chat_abc12345")
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        mock_chat_queue.cancel_job.assert_called_once_with("chat_abc12345")

    def test_cancel_llm_chat_failure(self, client, app):
        """DELETE /api/llm/chat/<id> returns 400 when cancel fails"""
        mock_chat_queue = app.config["_mock_chat_queue_manager"]
        mock_chat_queue.cancel_job.return_value = False

        response = client.delete("/api/llm/chat/chat_abc12345")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_llm_queue_stats(self, client, app):
        """GET /api/llm/queue/stats returns queue statistics"""
        mock_chat_queue = app.config["_mock_chat_queue_manager"]
        mock_chat_queue.get_queue_stats.return_value = {
            "total_jobs": 5,
            "queued": 3,
            "running": 2,
            "recent_completed": 0,
        }

        response = client.get("/api/llm/queue/stats")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total_jobs"] == 5
        assert data["queued"] == 3
        assert data["running"] == 2
        assert data["recent_completed"] == 0
        mock_chat_queue.get_queue_stats.assert_called_once()
