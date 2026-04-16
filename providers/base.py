from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BaseProvider(ABC):
    """Abstract base class for AI providers (Ollama, OpenRouter, etc.)"""

    def __init__(self, name: str, provider_type: str):
        self.name = name
        self.provider_type = provider_type
        self.status = "unknown"  # online, offline, error
        self.last_error = None

    @abstractmethod
    def get_models(self) -> List[Dict[str, Any]]:
        """Return list of available models with metadata"""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if provider is reachable"""
        pass

    @abstractmethod
    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a specific model"""
        pass

    @abstractmethod
    def estimate_vram(self, model_id: str) -> Optional[int]:
        """Estimate VRAM required for model in bytes, or None if cloud-based"""
        pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.provider_type,
            "status": self.status,
            "last_error": self.last_error,
        }
