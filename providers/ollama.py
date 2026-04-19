import base64
import requests
import logging
from typing import Dict, List, Any, Optional
from .base import BaseProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):
    """Ollama local/remote provider"""

    def __init__(self, name: str, base_url: str):
        super().__init__(name, "ollama")
        self.base_url = base_url.rstrip("/")
        self.models = []
        self._test_connection()

    def _test_connection(self):
        """Test connection and populate models"""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                self.status = "online"
                self.models = resp.json().get("models", [])
                logger.info(
                    f"Connected to Ollama at {self.base_url}, found {len(self.models)} models"
                )
            else:
                self.status = "error"
                self.last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            self.status = "offline"
            self.last_error = str(e)
            logger.warning(f"Cannot connect to Ollama at {self.base_url}: {e}")

    def test_connection(self) -> bool:
        self._test_connection()
        return self.status == "online"

    def get_models(self) -> List[Dict[str, Any]]:
        if not self.models or self.status != "online":
            self._test_connection()

        # Enrich with VRAM estimates
        result = []
        for model in self.models:
            model_id = model.get("name", "unknown")
            result.append(
                {
                    "id": model_id,
                    "name": model_id,
                    "size": model.get("size", 0),
                    "parameter_size": model.get("details", {}).get(
                        "parameter_size", "unknown"
                    ),
                    "quantization": model.get("details", {}).get(
                        "quantization_level", "unknown"
                    ),
                    "vram_required": self.estimate_vram(model_id),
                    "modified": model.get("modified_at", ""),
                }
            )
        return result

    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        for model in self.models:
            if model.get("name") == model_id:
                return {
                    "id": model_id,
                    "size": model.get("size", 0),
                    "details": model.get("details", {}),
                }
        return None

    def estimate_vram(self, model_id: str) -> Optional[int]:
        """Estimate VRAM from model size + 2GB overhead"""
        for model in self.models:
            if model.get("name") == model_id:
                model_size = model.get("size", 0)
                # Add 2GB overhead for context, kv cache, etc.
                return model_size + (2 * 1024 * 1024 * 1024)
        return None

    def get_running_models(self) -> List[Dict[str, Any]]:
        """Get currently loaded models and their memory usage"""
        try:
            resp = requests.get(f"{self.base_url}/api/ps", timeout=5)
            if resp.status_code == 200:
                return resp.json().get("models", [])
        except Exception as e:
            logger.error(f"Error getting running models: {e}")
        return []

    def check_health(self):
        """Re-test connection and update status (alias for _test_connection)"""
        self._test_connection()

    def analyze_frame(
        self,
        frame_path: str,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> str:
        """
        Analyze a single frame (or run a text-only prompt when frame_path is empty).
        Uses the Ollama /api/chat REST endpoint directly so the worker never needs
        the `ollama` Python package and always talks to self.base_url.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        user_message: Dict[str, Any] = {"role": "user", "content": user_prompt or "Describe this image."}

        if frame_path:
            try:
                with open(frame_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")
                user_message["images"] = [image_b64]
            except Exception as e:
                logger.warning(f"Failed to read frame {frame_path}: {e}")

        messages.append(user_message)

        payload = {
            "model": model_id,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "think": False},
        }

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
        except Exception as e:
            raise RuntimeError(f"Ollama chat request failed ({self.base_url}): {e}") from e

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            "url": self.base_url,
            "models_count": len(self.models),
        }
