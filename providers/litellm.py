import base64
import requests
import logging
from typing import Dict, List, Any, Optional
from .base import BaseProvider

logger = logging.getLogger(__name__)


API_BASE = "http://172.16.17.3:4000/v1"

_VRAM_PER_MODEL = 4 * 1024 * 1024 * 1024


class LiteLLMProvider(BaseProvider):
    """LiteLLM proxy provider — OpenAI-compatible API format"""

    def __init__(self, name: str, api_url: str):
        super().__init__(name, "litellm")
        self.api_url = api_url.rstrip("/")
        self._models_cache: List[Dict[str, Any]] = []
        self._test_connection()

    def _test_connection(self):
        """Test connectivity via GET {api_url}/models and cache model list."""
        try:
            resp = requests.get(
                f"{self.api_url}/models",
                headers={"Authorization": "Bearer "},
                timeout=10,
            )
            if resp.status_code == 200:
                self.status = "online"
                raw = resp.json().get("data", [])
                self._models_cache = [
                    {"id": m.get("id"), "name": m.get("name", m.get("id"))}
                    for m in raw
                    if m.get("id")
                ]
                logger.info(
                    f"Connected to LiteLLM at {self.api_url}, found {len(self._models_cache)} models"
                )
            else:
                self.status = "error"
                self.last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            self.status = "offline"
            self.last_error = str(e)
            logger.warning(f"Cannot connect to LiteLLM at {self.api_url}: {e}")

    def test_connection(self) -> bool:
        self._test_connection()
        return self.status == "online"

    def get_models(self) -> List[Dict[str, Any]]:
        """Return available models (enriched with VRAM estimate)."""
        if not self._models_cache or self.status != "online":
            self._test_connection()

        result = []
        for m in self._models_cache:
            result.append(
                {
                    "id": m["id"],
                    "name": m["name"],
                    "vram_required": _VRAM_PER_MODEL,
                }
            )
        result.sort(key=lambda x: x["name"])
        return result

    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get info for a single model from the cached list."""
        for m in self._models_cache:
            if m["id"] == model_id:
                return {
                    "id": m["id"],
                    "name": m["name"],
                    "vram_required": _VRAM_PER_MODEL,
                }
        return None

    def estimate_vram(self, model_id: str) -> Optional[int]:
        """Return hardcoded 4 GB per model (local processing overhead)."""
        for m in self._models_cache:
            if m["id"] == model_id:
                return _VRAM_PER_MODEL
        return None

    def analyze_frame(
        self,
        frame_path: str,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> str:
        """
        Analyze a single frame (or text-only when frame_path is empty).
        Uses the OpenAI-compatible /chat/completions endpoint.
        Images are sent as base64 data URIs in the image_url content format.
        """
        messages: List[Dict[str, Any]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if frame_path:
            try:
                with open(frame_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")
                user_content: Any = [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                    {
                        "type": "text",
                        "text": user_prompt or "Describe this image.",
                    },
                ]
            except Exception as e:
                logger.warning(f"Failed to read frame {frame_path}: {e}")
                user_content = user_prompt or "Describe this image."
        else:
            user_content = user_prompt or "Describe this image."

        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
        }

        try:
            resp = requests.post(
                f"{self.api_url}/chat/completions",
                headers={
                    "Authorization": "Bearer ",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(
                f"LiteLLM chat request failed ({self.api_url}): {e}"
            ) from e

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            "api_url": self.api_url,
            "models_count": len(self._models_cache),
        }
