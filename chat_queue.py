#!/usr/bin/env python3
"""
Chat Queue Manager for LLM chat requests.
Handles rate limiting, queueing, and concurrent request management.
"""

import logging
import threading
import time
import queue
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ChatJobStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ChatJob:
    """A chat request job"""

    job_id: str
    provider_type: str  # "ollama" or "openrouter"
    model_id: str
    prompt: str
    content: str
    temperature: float = 0.0
    api_key: str = ""
    ollama_url: str = "http://localhost:11434"
    created_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: ChatJobStatus = ChatJobStatus.PENDING
    queue_position: int = 0
    result: Optional[str] = None
    error: Optional[str] = None
    priority: int = 0  # Higher = runs sooner

    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "provider_type": self.provider_type,
            "model_id": self.model_id,
            "status": self.status.value,
            "queue_position": self.queue_position,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "priority": self.priority,
        }


class ChatQueueManager:
    """
    Manages LLM chat requests with rate limiting and queueing.
    Separate from video analysis queue since chat requests are lightweight.
    """

    MAX_CONCURRENT_JOBS = 5  # Maximum concurrent chat requests
    MAX_JOBS_PER_MINUTE = 30  # Rate limit per minute
    CHECK_INTERVAL = 1  # seconds

    def __init__(self):
        self.jobs: Dict[str, ChatJob] = {}
        self.queue: List[str] = []  # Ordered list of job_ids
        self.running: Dict[str, ChatJob] = {}  # job_id -> ChatJob
        self.lock = threading.RLock()
        self.callbacks: List[Callable] = []
        self.rate_limit_window: List[float] = []  # Timestamps of recent jobs
        self.worker_thread = None
        self._start_worker()

    def _start_worker(self):
        """Start background worker thread to process queue"""
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Chat queue manager worker started")

    def _worker_loop(self):
        """Background worker that processes the chat queue"""
        while True:
            try:
                self._process_queue()
            except Exception as e:
                logger.error(f"Error in chat queue worker: {e}")
            time.sleep(self.CHECK_INTERVAL)

    def _clean_rate_limit_window(self):
        """Remove timestamps older than 1 minute from rate limit window"""
        now = time.time()
        one_minute_ago = now - 60
        self.rate_limit_window = [
            ts for ts in self.rate_limit_window if ts > one_minute_ago
        ]

    def _check_rate_limit(self) -> bool:
        """Check if we're under rate limit"""
        self._clean_rate_limit_window()
        return len(self.rate_limit_window) < self.MAX_JOBS_PER_MINUTE

    def _process_queue(self):
        """Process chat queue and start jobs if within limits"""
        with self.lock:
            if not self.queue:
                return

            # Check rate limit
            if not self._check_rate_limit():
                logger.debug("Rate limit reached, waiting...")
                return

            # Check concurrent job limit
            if len(self.running) >= self.MAX_CONCURRENT_JOBS:
                return

            # Start next job in queue
            job_id = self.queue[0]
            job = self.jobs[job_id]

            # Start the job
            job.status = ChatJobStatus.RUNNING
            job.started_at = time.time()
            job.queue_position = 0
            self.running[job.job_id] = job

            # Remove from queue
            self.queue.pop(0)
            self._update_queue_positions()

            # Add to rate limit window
            self.rate_limit_window.append(time.time())

            # Start processing in background thread
            threading.Thread(target=self._process_job, args=(job,), daemon=True).start()

            logger.info(f"Chat job {job.job_id} started")
            self._notify_callbacks("started", job)

    def _process_job(self, job: ChatJob):
        """Process a chat job"""
        try:
            import requests

            full_prompt = (
                f"{job.prompt}\n\n{job.content}".strip() if job.content else job.prompt
            )

            if job.provider_type == "ollama":
                resp = requests.post(
                    f"{job.ollama_url.rstrip('/')}/api/chat",
                    json={
                        "model": job.model_id,
                        "messages": [{"role": "user", "content": full_prompt}],
                        "stream": False,
                        "think": False,
                        "options": {
                            "temperature": job.temperature,
                            "num_predict": 4096,
                        },
                    },
                    timeout=300,
                )
                resp.raise_for_status()
                result = resp.json().get("message", {}).get("content", "")

            else:  # openrouter
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {job.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": job.model_id,
                        "messages": [{"role": "user", "content": full_prompt}],
                        "temperature": job.temperature,
                    },
                    timeout=300,
                )
                resp.raise_for_status()
                result = resp.json()["choices"][0]["message"]["content"]

            job.result = result
            job.status = ChatJobStatus.COMPLETED

        except Exception as e:
            job.error = str(e)
            job.status = ChatJobStatus.FAILED
            logger.error(f"Chat job {job.job_id} failed: {e}")

        finally:
            job.completed_at = time.time()
            with self.lock:
                if job.job_id in self.running:
                    del self.running[job.job_id]

            logger.info(
                f"Chat job {job.job_id} {'completed' if job.result else 'failed'}"
            )
            self._notify_callbacks("completed" if job.result else "failed", job)

    def _update_queue_positions(self):
        """Update queue position numbers after changes"""
        for i, job_id in enumerate(self.queue):
            self.jobs[job_id].queue_position = i + 1

    def submit_job(
        self,
        provider_type: str,
        model_id: str,
        prompt: str,
        content: str = "",
        temperature: float = 0.0,
        api_key: str = "",
        ollama_url: str = "http://localhost:11434",
        priority: int = 0,
    ) -> str:
        """Submit a chat job and return job_id"""
        if not model_id:
            raise ValueError("model_id is required")

        import uuid

        job_id = f"chat_{uuid.uuid4().hex[:8]}"

        with self.lock:
            job = ChatJob(
                job_id=job_id,
                provider_type=provider_type,
                model_id=model_id,
                prompt=prompt,
                content=content,
                temperature=temperature,
                api_key=api_key,
                ollama_url=ollama_url,
                created_at=time.time(),
                priority=priority,
            )

            self.jobs[job_id] = job

            # Insert by priority (higher first); equal-priority jobs maintain FIFO order
            insert_pos = len(self.queue)
            for i, queued_id in enumerate(self.queue):
                queued_job = self.jobs[queued_id]
                if priority > queued_job.priority:
                    insert_pos = i
                    break

            self.queue.insert(insert_pos, job_id)
            job.queue_position = insert_pos + 1

            # Update positions for all queued jobs
            for i, qid in enumerate(self.queue):
                self.jobs[qid].queue_position = i + 1

            logger.info(
                f"Chat job {job_id} submitted, queue position {job.queue_position}"
            )
            self._notify_callbacks("submitted", job)

        return job_id

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get job status by ID"""
        with self.lock:
            if job_id not in self.jobs:
                return None
            return self.jobs[job_id].to_dict()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or queued chat job"""
        with self.lock:
            if job_id not in self.jobs:
                return False

            job = self.jobs[job_id]

            if job.status in [
                ChatJobStatus.COMPLETED,
                ChatJobStatus.FAILED,
                ChatJobStatus.RUNNING,
            ]:
                return False

            job.status = ChatJobStatus.CANCELLED
            job.completed_at = time.time()
            job.error = "Cancelled by user"

            if job_id in self.queue:
                self.queue.remove(job_id)
                self._update_queue_positions()

            logger.info(f"Chat job {job_id} cancelled")
            self._notify_callbacks("cancelled", job)
            return True

    def get_queue_stats(self) -> Dict:
        """Get queue statistics"""
        with self.lock:
            return {
                "total_jobs": len(self.jobs),
                "queued": len(self.queue),
                "running": len(self.running),
                "recent_completed": len(
                    [
                        j
                        for j in self.jobs.values()
                        if j.status == ChatJobStatus.COMPLETED
                        and j.completed_at
                        and time.time() - j.completed_at < 300
                    ]
                ),  # Last 5 minutes
                "rate_limit_window": len(self.rate_limit_window),
                "max_concurrent": self.MAX_CONCURRENT_JOBS,
                "max_per_minute": self.MAX_JOBS_PER_MINUTE,
            }

    def register_callback(self, callback: Callable):
        """Register a callback for job events"""
        with self.lock:
            self.callbacks.append(callback)

    def _notify_callbacks(self, event: str, job: ChatJob):
        """Notify all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(event, job)
            except Exception as e:
                logger.error(f"Error in chat queue callback: {e}")


# Global instance
chat_queue_manager = ChatQueueManager()
