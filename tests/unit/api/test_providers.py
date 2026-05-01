"""
Test providers API blueprint
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
class TestProvidersAPI:
    """Test providers API endpoints"""

    def test_list_providers(self, client, app):
        """GET /api/providers returns list of providers"""
        mock_providers = app.config["_mock_providers"]

        # Setup mock provider dicts
        litellm_provider = mock_providers["LiteLLM-Proxy"]
        litellm_provider.to_dict.return_value = {
            "name": "LiteLLM-Proxy",
            "type": "litellm",
            "url": "http://172.16.17.3:4000/v1",
            "status": "online",
        }

        openrouter_provider = mock_providers["OpenRouter"]
        openrouter_provider.to_dict.return_value = {
            "name": "OpenRouter",
            "type": "openrouter",
            "status": "online",
        }

        response = client.get("/api/providers")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 2
        provider_names = [p["name"] for p in data]
        assert "LiteLLM-Proxy" in provider_names
        assert "OpenRouter" in provider_names

    def test_get_litellm_models_no_server(self, client, app):
        """GET /api/providers/litellm/models returns 200 with provider status"""
        mock_models = [
            {"id": "qwen3-27b-q8", "name": "Qwen3 27B Q8"},
            {"id": "vision-best", "name": "Vision Best"},
        ]

        with patch("src.api.providers.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": mock_models}
            mock_get.return_value = mock_response

            with patch("src.api.providers.LiteLLMProvider") as MockProvider:
                mock_provider = MagicMock()
                mock_provider.get_models.return_value = mock_models
                mock_provider.status = "online"
                MockProvider.return_value = mock_provider

                response = client.get("/api/providers/litellm/models")
                assert response.status_code == 200
                data = response.get_json()
                assert "models" in data
                assert len(data["models"]) == 2
                assert data["status"] == "online"

    def test_get_litellm_models_success(self, client, app):
        """GET /api/providers/litellm/models returns models from LiteLLMProvider"""
        mock_models = [
            {"id": "qwen3-27b-q8", "name": "Qwen3 27B Q8"},
            {"id": "qwen3-27b-best", "name": "Qwen3 27B Best"},
            {"id": "vision-best", "name": "Vision Best"},
        ]

        with patch("src.api.providers.LiteLLMProvider") as MockProvider:
            mock_provider = MagicMock()
            mock_provider.get_models.return_value = mock_models
            mock_provider.status = "online"
            MockProvider.return_value = mock_provider

            response = client.get("/api/providers/litellm/models")
            assert response.status_code == 200
            data = response.get_json()
            assert "models" in data
            assert len(data["models"]) == 3
            assert data["server"] == "http://172.16.17.3:4000/v1"

    def test_get_openrouter_models_no_key(self, client, app):
        """GET /api/providers/openrouter/models without API key returns 400"""
        # We need to mock get_openrouter_api_key BEFORE the route handler reads it
        # Since the module was already imported, we patch it at the module level
        import src.api.providers as providers_module

        with patch.object(providers_module, 'get_openrouter_api_key', return_value=None):
            response = client.get("/api/providers/openrouter/models")
            assert response.status_code == 400
            data = response.get_json()
            assert "error" in data
            assert "OpenRouter API key not configured" in data["error"]

    def test_get_openrouter_models_success(self, client, app):
        """GET /api/providers/openrouter/models returns models when API key is available"""
        mock_providers = app.config["_mock_providers"]
        openrouter_provider = mock_providers["OpenRouter"]
        openrouter_provider.get_models.return_value = [
            {"id": "openai/gpt-4", "name": "GPT-4"},
            {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus"}
        ]

        import src.api.providers as providers_module

        # We need to mock both get_openrouter_api_key AND make sure get_providers returns our mocked providers
        with patch.object(providers_module, 'get_openrouter_api_key', return_value="test_api_key"):
            with patch.object(providers_module, 'get_providers', return_value=mock_providers):
                response = client.get("/api/providers/openrouter/models")
                assert response.status_code == 200
                data = response.get_json()
                assert "models" in data
                assert len(data["models"]) == 2
                openrouter_provider.get_models.assert_called_once()

    def test_estimate_openrouter_cost_no_model(self, client, app):
        """GET /api/providers/openrouter/cost without model returns 400"""
        response = client.get("/api/providers/openrouter/cost")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "Missing model parameter" in data["error"]

    def test_estimate_openrouter_cost_success(self, client, app):
        """GET /api/providers/openrouter/cost returns cost estimate"""
        mock_providers = app.config["_mock_providers"]
        openrouter_provider = mock_providers["OpenRouter"]
        openrouter_provider.estimate_cost.return_value = {
            "total": 0.015,
            "prompt_cost": 0.010,
            "completion_cost": 0.005,
            "currency": "USD"
        }

        import src.api.providers as providers_module

        with patch.object(providers_module, 'get_openrouter_api_key', return_value="test_key"):
            with patch.object(providers_module, 'get_providers', return_value=mock_providers):
                response = client.get(
                    "/api/providers/openrouter/cost?model=openai/gpt-4&frames=1000"
                )
                assert response.status_code == 200
                data = response.get_json()
                assert "total" in data
                assert data["total"] == 0.015
                openrouter_provider.estimate_cost.assert_called_once_with("openai/gpt-4", 1000)

    def test_get_openrouter_balance_no_key(self, client, app):
        """GET /api/providers/openrouter/balance without API key returns 400"""
        import src.api.providers as providers_module

        with patch.object(providers_module, 'get_openrouter_api_key', return_value=None):
            response = client.get("/api/providers/openrouter/balance")
            assert response.status_code == 400
            data = response.get_json()
            assert "error" in data
            assert "OpenRouter API key not configured" in data["error"]

    def test_get_openrouter_balance_success(self, client, app):
        """GET /api/providers/openrouter/balance returns balance when API key is available"""
        mock_providers = app.config["_mock_providers"]

        import src.api.providers as providers_module

        with patch.object(providers_module, 'get_openrouter_api_key', return_value="test_api_key"):
            with patch.object(providers_module, 'get_providers', return_value=mock_providers):
                with patch("src.api.providers.requests.get") as mock_get:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.json.return_value = {
                        "data": {
                            "balance": 10.5,
                            "usage": 2.3,
                            "limit": 100
                        }
                    }
                    mock_get.return_value = mock_response

                    response = client.get("/api/providers/openrouter/balance")
                    assert response.status_code == 200
                    data = response.get_json()
                    assert "balance" in data
                    assert data["balance"] == 10.5
                    mock_get.assert_called_once()
