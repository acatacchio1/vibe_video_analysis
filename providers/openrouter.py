import base64
import requests
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import BaseProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseProvider):
    """OpenRouter API provider with pricing"""

    API_URL = "https://openrouter.ai/api/v1"
    CACHE_FILE = Path("cache/openrouter_pricing.json")
    CACHE_TTL = 3600  # 1 hour

    def __init__(self, name: str, api_key: str):
        super().__init__(name, "openrouter")
        self.api_key = api_key
        self.pricing_cache = {}
        self._load_cached_pricing()
        self._test_connection()

    def _test_connection(self):
        """Test API key validity"""
        try:
            resp = requests.get(
                f"{self.API_URL}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            if resp.status_code == 200:
                self.status = "online"
                self._update_pricing_cache(resp.json().get("data", []))
            elif resp.status_code == 401:
                self.status = "error"
                self.last_error = "Invalid API key"
            else:
                self.status = "error"
                self.last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            self.status = "offline"
            self.last_error = str(e)

    def test_connection(self) -> bool:
        self._test_connection()
        return self.status == "online"

    def _load_cached_pricing(self):
        """Load pricing from cache file"""
        try:
            if self.CACHE_FILE.exists():
                cache_data = json.loads(self.CACHE_FILE.read_text())
                if time.time() - cache_data.get("timestamp", 0) < self.CACHE_TTL:
                    self.pricing_cache = cache_data.get("pricing", {})
                    logger.info(
                        f"Loaded {len(self.pricing_cache)} models from pricing cache"
                    )
        except Exception as e:
            logger.warning(f"Failed to load pricing cache: {e}")

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    def _update_pricing_cache(self, models_data: List[Dict]):
        """Update pricing cache from API response"""
        self.pricing_cache = {}
        for model in models_data:
            model_id = model.get("id")
            if model_id:
                pricing = model.get("pricing") or {}
                self.pricing_cache[model_id] = {
                    "name": model.get("name", model_id),
                    "description": model.get("description", ""),
                    "context_length": model.get("context_length", 0),
                    "pricing": {
                        "prompt": self._safe_float(pricing.get("prompt")),
                        "completion": self._safe_float(pricing.get("completion")),
                        "image": self._safe_float(pricing.get("image")),
                    },
                    "architecture": model.get("architecture") or {},
                    "top_provider": model.get("top_provider") or {},
                }

        # Save to cache
        try:
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.CACHE_FILE.write_text(
                json.dumps({"timestamp": time.time(), "pricing": self.pricing_cache})
            )
        except Exception as e:
            logger.warning(f"Failed to save pricing cache: {e}")

    def get_models(self) -> List[Dict[str, Any]]:
        """Return list of available models with pricing"""
        # Only attempt a live refresh when there are no cached models at all.
        # If we have cached pricing, serve it even when offline so that a
        # transient DNS/network failure doesn't wipe out the model list.
        if not self.pricing_cache:
            self._test_connection()

        result = []
        for model_id, info in self.pricing_cache.items():
            pricing = info.get("pricing", {})
            result.append(
                {
                    "id": model_id,
                    "name": info.get("name", model_id),
                    "description": info.get("description", ""),
                    "context_length": info.get("context_length", 0),
                    "pricing_prompt": pricing.get("prompt", 0),
                    "pricing_completion": pricing.get("completion", 0),
                    "pricing_image": pricing.get("image", 0),
                    "vram_required": None,  # Cloud-based, no local VRAM
                }
            )

        # Sort by name
        result.sort(key=lambda x: x["name"])
        return result

    def get_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        return self.pricing_cache.get(model_id)

    def get_pricing(self, model_id: str) -> Dict[str, float]:
        """Get pricing for specific model"""
        info = self.pricing_cache.get(model_id, {})
        pricing = info.get("pricing", {})
        return {
            "prompt": pricing.get("prompt", 0),
            "completion": pricing.get("completion", 0),
            "image": pricing.get("image", 0),
        }

    def estimate_cost(
        self, model_id: str, frame_count: int, include_transcript: bool = True
    ) -> Dict[str, float]:
        """Estimate cost range for analysis

        Assumptions:
        - Frame analysis: 500-1500 prompt tokens, 200-800 completion tokens per frame
        - Each frame includes image
        - Transcript (if present): 1000-3000 prompt tokens, 500-1500 completion tokens
        """
        pricing = self.get_pricing(model_id)

        # Per frame estimates
        min_prompt_tokens = frame_count * 500
        max_prompt_tokens = frame_count * 1500
        min_completion_tokens = frame_count * 200
        max_completion_tokens = frame_count * 800
        image_cost = frame_count * pricing.get("image", 0)

        # Transcript processing
        if include_transcript:
            min_prompt_tokens += 1000
            max_prompt_tokens += 3000
            min_completion_tokens += 500
            max_completion_tokens += 1500

        # Video reconstruction (final step)
        min_prompt_tokens += 2000
        max_prompt_tokens += 5000
        min_completion_tokens += 500
        max_completion_tokens += 2000

        min_cost = (
            (min_prompt_tokens / 1000) * pricing.get("prompt", 0)
            + (min_completion_tokens / 1000) * pricing.get("completion", 0)
            + image_cost
        )
        max_cost = (
            (max_prompt_tokens / 1000) * pricing.get("prompt", 0)
            + (max_completion_tokens / 1000) * pricing.get("completion", 0)
            + image_cost
        )

        return {
            "min": min_cost,
            "max": max_cost,
            "avg": (min_cost + max_cost) / 2,
            "currency": "USD",
        }

    def calculate_cost(
        self,
        model_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        image_count: int = 0,
    ) -> float:
        """Calculate actual cost from token usage"""
        pricing = self.get_pricing(model_id)
        prompt_cost = (prompt_tokens / 1000) * pricing.get("prompt", 0)
        completion_cost = (completion_tokens / 1000) * pricing.get("completion", 0)
        image_cost = image_count * pricing.get("image", 0)
        return prompt_cost + completion_cost + image_cost

    def estimate_vram(self, model_id: str) -> Optional[int]:
        """OpenRouter is cloud-based, no local VRAM required"""
        return 0  # 0 means no local VRAM needed

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
        Uses the OpenRouter /chat/completions endpoint (OpenAI-compatible).
        Images are sent as base64-encoded data URIs in the vision content format.
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if frame_path:
            try:
                with open(frame_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("utf-8")
                user_content = [
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
                f"{self.API_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"OpenRouter chat request failed: {e}") from e

    def to_dict(self) -> Dict[str, Any]:
        return {
            **super().to_dict(),
            "models_count": len(self.pricing_cache),
            "cached_pricing_age": int(
                time.time()
                - json.loads(self.CACHE_FILE.read_text()).get("timestamp", 0)
            )
            if self.CACHE_FILE.exists()
            else None,
        }
