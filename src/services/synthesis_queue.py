#!/usr/bin/env python3
"""
Synthesis Queue Manager for two-step video analysis.
Handles concurrent frame synthesis requests to secondary LLM instances.
"""

import logging
import threading
import time
import queue
import uuid
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class SynthesisJobStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SynthesisJob:
    """A frame synthesis job for Phase 2 analysis"""
    
    job_id: str
    frame_number: int
    original_frame: int
    timestamp: float
    original_ts: float
    corrected_ts: float
    vision_analysis: str
    transcript_context: str
    phase2_provider_type: str  # "ollama" or "openrouter"
    phase2_model: str
    phase2_temperature: float = 0.0
    phase2_api_key: str = ""
    phase2_ollama_url: str = "http://localhost:11434"
    
    # Progress tracking
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: SynthesisJobStatus = SynthesisJobStatus.PENDING
    queue_position: int = 0
    
    # Results
    combined_analysis: Optional[str] = None
    error: Optional[str] = None
    tokens: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "frame_number": self.frame_number,
            "original_frame": self.original_frame,
            "timestamp": self.timestamp,
            "original_ts": self.original_ts,
            "corrected_ts": self.corrected_ts,
            "vision_analysis": self.vision_analysis,
            "transcript_context": self.transcript_context,
            "phase2_provider_type": self.phase2_provider_type,
            "phase2_model": self.phase2_model,
            "phase2_temperature": self.phase2_temperature,
            "status": self.status.value,
            "queue_position": self.queue_position,
            "combined_analysis": self.combined_analysis,
            "error": self.error,
            "tokens": self.tokens,
        }


class SynthesisQueueManager:
    """Manages concurrent synthesis jobs for two-step analysis"""
    
    def __init__(self, max_concurrent: int = 3, rate_limit_per_minute: int = 60):
        self.max_concurrent = max_concurrent
        self.max_jobs_per_minute = rate_limit_per_minute
        
        # Job storage
        self.jobs: Dict[str, SynthesisJob] = {}
        self.queue: List[str] = []  # job_ids in queue order
        self.running: Dict[str, SynthesisJob] = {}
        
        # Rate limiting
        self.rate_limit_window: List[float] = []  # timestamps of started jobs
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Callbacks for progress updates
        self.callbacks: List[Callable[[str, SynthesisJob], None]] = []
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        logger.info(f"SynthesisQueueManager initialized (max_concurrent={max_concurrent})")
    
    def _worker_loop(self):
        """Background thread that processes the synthesis queue"""
        while True:
            try:
                self._process_queue()
                time.sleep(0.5)  # Check queue twice per second
            except Exception as e:
                logger.error(f"Error in synthesis worker loop: {e}")
    
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
        return len(self.rate_limit_window) < self.max_jobs_per_minute
    
    def _update_queue_positions(self):
        """Update queue positions for all queued jobs"""
        with self.lock:
            for position, job_id in enumerate(self.queue):
                if job_id in self.jobs:
                    self.jobs[job_id].queue_position = position + 1
    
    def _notify_callbacks(self, event: str, job: SynthesisJob):
        """Notify all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(event, job)
            except Exception as e:
                logger.error(f"Error in synthesis callback: {e}")
    
    def _process_queue(self):
        """Process synthesis queue and start jobs if within limits"""
        with self.lock:
            if not self.queue:
                return
            
            # Check rate limit
            if not self._check_rate_limit():
                logger.debug("Synthesis rate limit reached, waiting...")
                return
            
            # Check concurrent job limit
            if len(self.running) >= self.max_concurrent:
                return
            
            # Start next job in queue
            job_id = self.queue[0]
            job = self.jobs[job_id]
            
            # Start the job
            job.status = SynthesisJobStatus.RUNNING
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
            
            logger.info(f"Synthesis job {job.job_id} started for frame {job.frame_number}")
            self._notify_callbacks("started", job)
    
    def _process_job(self, job: SynthesisJob):
        """Process a synthesis job by sending to secondary LLM"""
        try:
            import requests
            
            # Build synthesis prompt
            synthesis_prompt = self._build_synthesis_prompt(job)
            
            if job.phase2_provider_type == "ollama":
                resp = requests.post(
                    f"{job.phase2_ollama_url.rstrip('/')}/api/chat",
                    json={
                        "model": job.phase2_model,
                        "messages": [{"role": "user", "content": synthesis_prompt}],
                        "stream": False,
                        "think": False,
                        "options": {
                            "temperature": job.phase2_temperature,
                            "num_predict": 4096,
                        },
                    },
                    timeout=300,
                )
                resp.raise_for_status()
                result = resp.json().get("message", {}).get("content", "")
                tokens = resp.json().get("usage", {})
                
            else:  # openrouter
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {job.phase2_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": job.phase2_model,
                        "messages": [{"role": "user", "content": synthesis_prompt}],
                        "temperature": job.phase2_temperature,
                        "max_tokens": 4096,
                    },
                    timeout=300,
                )
                resp.raise_for_status()
                data = resp.json()
                result = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {})
            
            job.combined_analysis = result
            job.tokens = tokens
            job.status = SynthesisJobStatus.COMPLETED
            
        except Exception as e:
            job.error = str(e)
            job.status = SynthesisJobStatus.FAILED
            logger.error(f"Synthesis job {job.job_id} failed: {e}")
        
        finally:
            job.completed_at = time.time()
            with self.lock:
                self.running.pop(job.job_id, None)
            
            logger.info(f"Synthesis job {job.job_id} completed with status {job.status.value}")
            self._notify_callbacks("completed", job)
    
    def _build_synthesis_prompt(self, job: SynthesisJob) -> str:
        """Build synthesis prompt from vision analysis and transcript context"""
        # TODO: Load from prompts/frame_analysis/synthesis.txt
        # For now, use a simple template
        return f"""Combine the visual analysis with transcript context to create an enhanced description.

VISION ANALYSIS:
{job.vision_analysis}

TRANSCRIPT CONTEXT:
{job.transcript_context}

TIMESTAMP: {job.corrected_ts:.2f} seconds (original: {job.original_ts:.2f}s)

Create a comprehensive analysis that:
1. Integrates what's visually present with what's being said
2. Highlights relationships between visual and audio information
3. Identifies any contradictions or confirmations
4. Provides additional context from the transcript

ENHANCED ANALYSIS:"""
    
    def enqueue_job(self, job_data: Dict) -> str:
        """Enqueue a new synthesis job"""
        with self.lock:
            job_id = str(uuid.uuid4())[:8]
            
            job = SynthesisJob(
                job_id=job_id,
                frame_number=job_data["frame_number"],
                original_frame=job_data.get("original_frame", job_data["frame_number"]),
                timestamp=job_data["timestamp"],
                original_ts=job_data.get("original_ts", job_data["timestamp"]),
                corrected_ts=job_data.get("corrected_ts", job_data["timestamp"]),
                vision_analysis=job_data["vision_analysis"],
                transcript_context=job_data["transcript_context"],
                phase2_provider_type=job_data["phase2_provider_type"],
                phase2_model=job_data["phase2_model"],
                phase2_temperature=job_data.get("phase2_temperature", 0.0),
                phase2_api_key=job_data.get("phase2_api_key", ""),
                phase2_ollama_url=job_data.get("phase2_ollama_url", "http://localhost:11434"),
            )
            
            self.jobs[job_id] = job
            self.queue.append(job_id)
            self._update_queue_positions()
            
            job.status = SynthesisJobStatus.QUEUED
            logger.info(f"Synthesis job {job_id} queued for frame {job.frame_number} (position {job.queue_position})")
            self._notify_callbacks("queued", job)
            
            return job_id
    
    def get_job(self, job_id: str) -> Optional[SynthesisJob]:
        """Get a synthesis job by ID"""
        with self.lock:
            return self.jobs.get(job_id)
    
    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get job status as dictionary"""
        job = self.get_job(job_id)
        if job:
            return job.to_dict()
        return None
    
    def get_queue_stats(self) -> Dict:
        """Get queue statistics"""
        with self.lock:
            return {
                "total_jobs": len(self.jobs),
                "queued": len(self.queue),
                "running": len(self.running),
                "completed": len([j for j in self.jobs.values() if j.status == SynthesisJobStatus.COMPLETED]),
                "failed": len([j for j in self.jobs.values() if j.status == SynthesisJobStatus.FAILED]),
                "max_concurrent": self.max_concurrent,
            }
    
    def get_progress(self) -> float:
        """Get overall progress (0-100)"""
        with self.lock:
            if not self.jobs:
                return 100.0
            
            completed = len([j for j in self.jobs.values() if j.status in [
                SynthesisJobStatus.COMPLETED, SynthesisJobStatus.FAILED, SynthesisJobStatus.CANCELLED
            ]])
            
            return (completed / len(self.jobs)) * 100
    
    def is_complete(self) -> bool:
        """Check if all jobs are complete"""
        with self.lock:
            if not self.jobs:
                return True
            
            for job in self.jobs.values():
                if job.status not in [
                    SynthesisJobStatus.COMPLETED, 
                    SynthesisJobStatus.FAILED, 
                    SynthesisJobStatus.CANCELLED
                ]:
                    return False
            return True
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a synthesis job"""
        with self.lock:
            if job_id not in self.jobs:
                return False
            
            job = self.jobs[job_id]
            if job.status in [SynthesisJobStatus.PENDING, SynthesisJobStatus.QUEUED]:
                job.status = SynthesisJobStatus.CANCELLED
                if job_id in self.queue:
                    self.queue.remove(job_id)
                    self._update_queue_positions()
                logger.info(f"Synthesis job {job_id} cancelled")
                self._notify_callbacks("cancelled", job)
                return True
            else:
                logger.warning(f"Cannot cancel synthesis job {job_id} in status {job.status.value}")
                return False
    
    def register_callback(self, callback: Callable[[str, SynthesisJob], None]):
        """Register a callback for job events"""
        with self.lock:
            self.callbacks.append(callback)
    
    def clear_completed(self):
        """Clear completed jobs from memory"""
        with self.lock:
            to_remove = []
            for job_id, job in self.jobs.items():
                if job.status in [SynthesisJobStatus.COMPLETED, SynthesisJobStatus.FAILED, SynthesisJobStatus.CANCELLED]:
                    to_remove.append(job_id)
            
            for job_id in to_remove:
                self.jobs.pop(job_id, None)
            
            logger.info(f"Cleared {len(to_remove)} completed synthesis jobs")


# Global synthesis queue instance
synthesis_queue = SynthesisQueueManager(max_concurrent=3)