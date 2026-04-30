"""Enhanced API client for CLI operations."""
import json
import time
from pathlib import Path
from typing import Any, Optional

import requests
from requests.exceptions import RequestException

__all__ = ["APIClient", "api_error"]

API_BASE = "http://127.0.0.1:10000"


class APIClient:
    """HTTP client for the video-analyzer-web REST API."""

    def __init__(self, base_url: str | None = None, timeout: int = 300):
        self.base_url = (base_url or API_BASE).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    # ---- Connection checks ----

    @staticmethod
    def is_running(base_url: str = API_BASE) -> bool:
        """Check if the server is reachable."""
        try:
            resp = requests.get(f"{base_url.rstrip('/')}/api/videos", timeout=3)
            return resp.status_code == 200
        except RequestException:
            return False

    def check_connection(self) -> bool:
        return self.is_running(self.base_url)

    # ---- Videos ----

    def upload_video(self, path: Path, whisper_model: str = "base", language: str = "en"):
        """Upload a video file with optional transcription params."""
        with path.open("rb") as f:
            resp = self.session.post(
                f"{self.base_url}/api/videos/upload",
                files={"video": (path.name, f)},
                data={"whisper_model": whisper_model, "language": language},
                timeout=self.timeout,
            )
        return resp.json()

    def list_videos(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/videos", timeout=self.timeout)
        return resp.json()

    def delete_video(self, name: str) -> dict:
        resp = self.session.delete(f"{self.base_url}/api/videos/{name}", timeout=self.timeout)
        return resp.json()

    def delete_all_source(self) -> dict:
        resp = self.session.delete(f"{self.base_url}/api/videos/source/all", timeout=self.timeout)
        return resp.json()

    def run_dedup(self, video: str, threshold: int) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/videos/{video}/dedup",
            json={"threshold": threshold},
            timeout=self.timeout,
        )
        return resp.json()

    def run_dedup_multi(self, video: str, thresholds: list[int]) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/videos/{video}/dedup-multi",
            json={"thresholds": thresholds},
            timeout=max(60, len(thresholds) * 10 + 60),
        )
        return resp.json()

    def detect_scenes(self, video: str, detector_type: str = "content",
                      threshold: float = 30.0, min_scene_len: int = 15) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/videos/{video}/scenes",
            json={
                "detector_type": detector_type,
                "threshold": threshold,
                "min_scene_len": min_scene_len,
            },
            timeout=300,
        )
        return resp.json()

    def scene_aware_dedup(self, video: str, threshold: int = 10,
                           scene_threshold: float = 30.0, min_scene_len: int = 15) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/videos/{video}/scene-aware-dedup",
            json={
                "threshold": threshold,
                "scene_threshold": scene_threshold,
                "min_scene_len": min_scene_len,
            },
            timeout=300,
        )
        return resp.json()

    def get_frame_meta(self, video: str) -> dict:
        resp = self.session.get(f"{self.base_url}/api/videos/{video}/frames", timeout=self.timeout)
        return resp.json()

    def get_transcript(self, video: str) -> dict:
        resp = self.session.get(f"{self.base_url}/api/videos/{video}/transcript", timeout=self.timeout)
        return resp.json()

    def get_frames_index(self, video: str) -> dict:
        resp = self.session.get(f"{self.base_url}/api/videos/{video}/frames_index", timeout=self.timeout)
        return resp.json()

    # ---- Jobs ----

    def list_jobs(self) -> list:
        resp = self.session.get(f"{self.base_url}/api/jobs", timeout=self.timeout)
        return resp.json()

    def list_jobs_running(self) -> list:
        resp = self.session.get(f"{self.base_url}/api/jobs/running", timeout=self.timeout)
        return resp.json()

    def list_jobs_queued(self) -> list:
        resp = self.session.get(f"{self.base_url}/api/jobs/queued", timeout=self.timeout)
        return resp.json()

    def get_job(self, job_id: str) -> dict:
        resp = self.session.get(f"{self.base_url}/api/jobs/{job_id}", timeout=self.timeout)
        return resp.json()

    def get_job_frames(self, job_id: str, limit: int = 50, offset: int = 0) -> list:
        resp = self.session.get(
            f"{self.base_url}/api/jobs/{job_id}/frames",
            params={"limit": limit, "offset": offset},
            timeout=self.timeout,
        )
        return resp.json()

    def get_results(self, job_id: str) -> dict:
        resp = self.session.get(f"{self.base_url}/api/jobs/{job_id}/results", timeout=self.timeout)
        return resp.json()

    def cancel_job(self, job_id: str) -> dict:
        resp = self.session.delete(f"{self.base_url}/api/jobs/{job_id}", timeout=self.timeout)
        return resp.json()

    def update_job_priority(self, job_id: str, priority: int) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/jobs/{job_id}/priority",
            json={"priority": priority},
            timeout=self.timeout,
        )
        return resp.json()

    def status_poll(self, job_id: str, interval: float = 2.0) -> dict:
        """Poll a job until it reaches a terminal state. Returns final status dict."""
        completed = {"completed", "failed", "cancelled", "error"}
        while True:
            try:
                data = self.get_job(job_id)
            except RequestException:
                raise ConnectionError(f"Cannot reach server at {self.base_url}")
            status = data.get("status")
            if status in completed:
                return data
            time.sleep(interval)

    # ---- Providers ----

    def list_providers(self) -> list:
        resp = self.session.get(f"{self.base_url}/api/providers", timeout=self.timeout)
        return resp.json()

    def discover_providers(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/providers/discover", timeout=60)
        return resp.json()

    def get_litellm_status(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/providers/litellm/models", timeout=self.timeout)
        return resp.json()



    def get_openrouter_models(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/providers/openrouter/models", timeout=self.timeout)
        return resp.json()

    def estimate_cost(self, model: str, frames: int) -> dict:
        resp = self.session.get(
            f"{self.base_url}/api/providers/openrouter/cost",
            params={"model": model, "frames": frames},
            timeout=self.timeout,
        )
        return resp.json()

    def get_balance(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/providers/openrouter/balance", timeout=self.timeout)
        return resp.json()

    # ---- System ----

    def get_vram_status(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/vram", timeout=self.timeout)
        return resp.json()

    def get_gpu_list(self) -> list:
        resp = self.session.get(f"{self.base_url}/api/gpus", timeout=self.timeout)
        return resp.json()

    def get_debug_status(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/debug", timeout=self.timeout)
        return resp.json()

    def toggle_debug(self, enable: bool) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/debug",
            json={"enable": enable},
            timeout=self.timeout,
        )
        return resp.json()

    # ---- LLM Chat ----

    def submit_chat(self, provider_type: str, model: str, prompt: str,
                    content: str = "", temperature: float = 0.1,
                    api_key: str = "", ollama_url: str = "http://localhost:11434") -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/llm/chat",
            json={
                "provider_type": provider_type,
                "model": model,
                "prompt": prompt,
                "content": content,
                "temperature": temperature,
                "api_key": api_key,
                "ollama_url": ollama_url,
            },
            timeout=self.timeout,
        )
        return resp.json()

    def get_chat_status(self, job_id: str) -> dict:
        resp = self.session.get(f"{self.base_url}/api/llm/chat/{job_id}", timeout=self.timeout)
        return resp.json()

    def cancel_chat(self, job_id: str) -> dict:
        resp = self.session.delete(f"{self.base_url}/api/llm/chat/{job_id}", timeout=self.timeout)
        return resp.json()

    def get_queue_stats(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/llm/queue/stats", timeout=self.timeout)
        return resp.json()

    # ---- Results ----

    def list_results(self) -> list:
        resp = self.session.get(f"{self.base_url}/api/results", timeout=self.timeout)
        return resp.json()

    # ---- Knowledge ----

    def get_kb_status(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/knowledge/status", timeout=self.timeout)
        return resp.json()

    def save_kb_config(self, **kwargs) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/knowledge/config",
            json=kwargs,
            timeout=self.timeout,
        )
        return resp.json()

    def test_kb_connection(self, url: str = "", api_key: str = "") -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/knowledge/test",
            json={"url": url, "api_key": api_key},
            timeout=self.timeout,
        )
        return resp.json()

    def sync_job_to_kb(self, job_id: str) -> dict:
        resp = self.session.post(f"{self.base_url}/api/knowledge/sync/{job_id}", timeout=self.timeout)
        return resp.json()

    def sync_all_to_kb(self) -> dict:
        resp = self.session.post(f"{self.base_url}/api/knowledge/sync-all", timeout=self.timeout)
        return resp.json()

    def list_knowledge_bases(self) -> dict:
        resp = self.session.get(f"{self.base_url}/api/knowledge/bases", timeout=self.timeout)
        return resp.json()

    def send_to_kb(self, job_id: str, kb_id: str = "", kb_name: str = "") -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/knowledge/send/{job_id}",
            json={"kb_id": kb_id, "kb_name": kb_name},
            timeout=self.timeout,
        )
        return resp.json()


def api_error(message: str, code: int = 1) -> dict:
    """Standardized CLI error response dict."""
    return {"error": {"code": code, "message": message}}
