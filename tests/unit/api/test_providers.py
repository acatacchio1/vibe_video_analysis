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
        ollama_provider = mock_providers["Ollama-Local"]
        ollama_provider.to_dict.return_value = {
            "name": "Ollama-Local",
            "type": "ollama",
            "url": "http://localhost:11434",
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
        assert "Ollama-Local" in provider_names
        assert "OpenRouter" in provider_names

    def test_get_ollama_instances(self, client, app):
        """GET /api/providers/ollama-instances returns known instances"""
        mock_disc = app.config["_mock_discovery"]
        mock_disc.get_known_hosts.return_value = [
            "http://localhost:11434",
            "http://192.168.1.237:11434",
        ]

        response = client.get("/api/providers/ollama-instances")
        assert response.status_code == 200
        data = response.get_json()
        assert "instances" in data
        assert isinstance(data["instances"], list)
        assert len(data["instances"]) == 2

    def test_update_ollama_instances(self, client, app, mock_api_error, mock_socketio, mock_providers_dict, mock_monitor, mock_chat_queue_manager, mock_vram_manager):
        """POST /api/providers/ollama-instances updates known instances"""
        import shutil
        
        # Mock discovery and the Path module functions
        with patch("discovery.discovery") as mock_discovery, \
             patch("src.api.providers.Path.exists", return_value=False), \
             patch("src.api.providers.Path.write_text"):
            mock_discovery.set_known_hosts = MagicMock()
            
            response = client.post(
                "/api/providers/ollama-instances",
                json={
                    "instances": [
                        "http://localhost:11434",
                        "http://192.168.1.237:11434"
                    ]
                }
            )
            assert response.status_code == 200

    def test_update_ollama_instances_invalid(self, client, app):
        """POST /api/providers/ollama-instances with non-list returns 400"""
        response = client.post(
            "/api/providers/ollama-instances",
            json={
                "instances": "not a list"  # Should be a list
            }
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "instances must be a list" in data["error"]

    def test_get_ollama_models_no_server(self, client, app):
        """GET /api/providers/ollama/models without server URL returns 400"""
        response = client.get("/api/providers/ollama/models")
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
        assert "No server URL" in data["error"]

    def test_get_ollama_models_success(self, client, app):
        """GET /api/providers/ollama/models returns models from server"""
        # Mock OllamaProvider before the request
        with patch("src.api.providers.OllamaProvider") as mock_provider_class:
            mock_provider = MagicMock()
            mock_provider.get_models.return_value = [
                {"name": "llama3:8b", "size": "4.7GB"},
                {"name": "llava:7b", "size": "4.3GB"}
            ]
            mock_provider.status = "online"
            mock_provider_class.return_value = mock_provider
            
            response = client.get("/api/providers/ollama/models?server=http://localhost:11434")
            assert response.status_code == 200
            data = response.get_json()
            assert "server" in data
            assert data["server"] == "http://localhost:11434"
            assert "models" in data
            assert len(data["models"]) == 2
            assert "status" in data
            assert data["status"] == "online"
            
            mock_provider_class.assert_called_once_with("temp", "http://localhost:11434")
            mock_provider.get_models.assert_called_once()

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

    def test_discover_ollama(self, client, app):
        """GET /api/providers/discover triggers Ollama discovery"""
        import src.api.providers as providers_module
        
        with patch.object(providers_module, 'discovery') as mock_discovery:
            mock_discovery.scan.return_value = [
                "http://192.168.1.237:11434",
                "http://192.168.1.241:11434"
            ]
            
            mock_providers_dict = {"Ollama-Local": MagicMock()}
            with patch.object(providers_module, 'get_providers', return_value=mock_providers_dict):
                with patch.object(providers_module, 'OllamaProvider') as mock_provider_class:
                    mock_provider = MagicMock()
                    mock_provider_class.return_value = mock_provider
                    
                    response = client.get("/api/providers/discover")
                    assert response.status_code == 200
                    data = response.get_json()
                    assert "discovered" in data
                    assert data["discovered"] == 2
                    assert "urls" in data
                    assert len(data["urls"]) == 2
                    
                    mock_discovery.scan.assert_called_once_with(force=True)
                    assert mock_provider_class.call_count == 2