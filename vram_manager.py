import logging
import threading
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path

try:
    import pynvml

    HAS_NVML = True
except ImportError:
    HAS_NVML = False

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GPUInfo:
    """Information about a single GPU"""

    index: int
    name: str
    total_vram: int
    used_vram: int
    free_vram: int


@dataclass
class Job:
    job_id: str
    provider_type: str  # "ollama" or "openrouter"
    provider_name: str
    model_id: str
    vram_required: int  # bytes, 0 for cloud providers
    priority: int = 0  # Higher = runs sooner
    status: JobStatus = JobStatus.PENDING
    queue_position: int = 0
    gpu_assigned: Optional[int] = None  # Which GPU this job runs on
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    video_path: str = ""
    params: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "provider_type": self.provider_type,
            "provider_name": self.provider_name,
            "model_id": self.model_id,
            "vram_required": self.vram_required,
            "vram_gb": round(self.vram_required / (1024**3), 2)
            if self.vram_required > 0
            else 0,
            "priority": self.priority,
            "status": self.status.value,
            "queue_position": self.queue_position,
            "gpu_assigned": self.gpu_assigned,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "video_path": self.video_path,
        }


class VRAMManager:
    """Manages GPU VRAM allocation with smart queueing across multiple GPUs"""

    VRAM_BUFFER = 1.2  # 20% buffer for safety
    CHECK_INTERVAL = 5  # seconds
    MAX_JOBS_PER_GPU = 2  # Maximum concurrent jobs per GPU
    CONTEXT_VRAM_OVERHEAD = 1 * (1024**3)  # 1GB for KV cache/context when model already loaded

    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.queue: List[str] = []  # Ordered list of job_ids
        self.running: Dict[str, Job] = {}  # job_id -> Job
        self.running_per_gpu: Dict[int, List[str]] = {}  # gpu_id -> list of job_ids
        self.lock = threading.RLock()
        self.callbacks: List[Callable] = []
        self.gpus: List[GPUInfo] = []  # List of all GPUs
        self._ollama_running_models_provider: Optional[Callable[[], set]] = None
        self._init_nvml()
        self._start_monitor()

    def _init_nvml(self):
        """Initialize NVIDIA Management Library and detect all GPUs"""
        global HAS_NVML
        if HAS_NVML:
            try:
                pynvml.nvmlInit()
                device_count = pynvml.nvmlDeviceGetCount()
                logger.info(f"NVML initialized. Found {device_count} GPU(s)")

                # Get info for all GPUs
                for i in range(device_count):
                    handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    name = pynvml.nvmlDeviceGetName(handle)

                    gpu = GPUInfo(
                        index=i,
                        name=name if isinstance(name, str) else name.decode("utf-8"),
                        total_vram=info.total,
                        used_vram=info.used,
                        free_vram=info.free,
                    )
                    self.gpus.append(gpu)
                    logger.info(
                        f"  GPU {i}: {gpu.name}, "
                        f"VRAM: {gpu.total_vram / (1024**3):.2f} GB"
                    )
            except Exception as e:
                logger.warning(f"Failed to initialize NVML: {e}")
                HAS_NVML = False

    def set_ollama_running_models_provider(self, provider: Callable[[], set]):
        """Set a callable that returns a set of currently loaded Ollama model names"""
        self._ollama_running_models_provider = provider

    def _get_loaded_ollama_models(self) -> set:
        """Get set of model names currently loaded in Ollama via /api/ps"""
        if not self._ollama_running_models_provider:
            return set()
        try:
            return self._ollama_running_models_provider()
        except Exception as e:
            logger.error(f"Error getting loaded Ollama models: {e}")
            return set()

    def _get_effective_vram_required(self, job: Job) -> int:
        """Get effective VRAM required, accounting for already-loaded models.

        If the model is already loaded in Ollama, only a small context
        overhead is needed instead of the full model size.
        """
        if job.provider_type != "ollama" or job.vram_required == 0:
            return job.vram_required

        loaded_models = self._get_loaded_ollama_models()
        if job.model_id in loaded_models:
            logger.info(
                f"Model {job.model_id} already loaded in Ollama, "
                f"reducing VRAM requirement from {job.vram_required / (1024**3):.2f}GB "
                f"to {self.CONTEXT_VRAM_OVERHEAD / (1024**3):.2f}GB"
            )
            return self.CONTEXT_VRAM_OVERHEAD

        return job.vram_required

    def _get_gpu_status(self) -> List[GPUInfo]:
        """Get current status of all GPUs"""
        if not HAS_NVML:
            return []

        gpus = []
        try:
            for i in range(len(self.gpus)):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                name = pynvml.nvmlDeviceGetName(handle)

                gpu = GPUInfo(
                    index=i,
                    name=name if isinstance(name, str) else name.decode("utf-8"),
                    total_vram=info.total,
                    used_vram=info.used,
                    free_vram=info.free,
                )
                gpus.append(gpu)
        except Exception as e:
            logger.error(f"Error getting GPU status: {e}")

        return gpus

    def _find_best_gpu(
        self, vram_required: int, vram_allocated: Dict[int, int] = None, job: Job = None
    ) -> Optional[int]:
        """Find the best GPU with enough VRAM available"""
        if vram_required == 0:
            return 0  # Cloud provider, any GPU is fine

        if not HAS_NVML or not self.gpus:
            return 0  # No GPU info available, start on GPU 0

        effective_vram = vram_required
        if job is not None:
            effective_vram = self._get_effective_vram_required(job)

        # Get loaded Ollama models to avoid double-counting with nvidia-smi
        loaded_ollama_models = self._get_loaded_ollama_models()

        # Get current VRAM usage for all GPUs
        gpus = self._get_gpu_status()

        # Calculate VRAM used by running jobs per GPU.
        # Skip jobs whose models are already loaded in Ollama — nvidia-smi
        # already accounts for their VRAM, so subtracting again would double-count.
        vram_used_by_gpu = {}
        for running_job in self.running.values():
            if running_job.gpu_assigned is not None:
                if (
                    running_job.provider_type == "ollama"
                    and running_job.model_id in loaded_ollama_models
                ):
                    continue
                vram_used_by_gpu[running_job.gpu_assigned] = (
                    vram_used_by_gpu.get(running_job.gpu_assigned, 0)
                    + running_job.vram_required
                )

        # Find GPU with most free VRAM that can fit the job
        best_gpu = None
        best_free = 0
        required_with_buffer = int(effective_vram * self.VRAM_BUFFER)

        for gpu in gpus:
            # Calculate actual free VRAM considering running jobs
            actual_free = gpu.free_vram

            # Subtract VRAM used by running jobs (only those not yet reflected in nvidia-smi)
            actual_free -= vram_used_by_gpu.get(gpu.index, 0)

            # Subtract VRAM allocated to jobs in current batch if provided
            if vram_allocated:
                actual_free -= vram_allocated.get(gpu.index, 0)

            # Check per-GPU job limit
            current_jobs_on_gpu = len(self.running_per_gpu.get(gpu.index, []))
            if current_jobs_on_gpu >= self.MAX_JOBS_PER_GPU:
                logger.debug(
                    f"GPU {gpu.index}: at job limit ({current_jobs_on_gpu}/{self.MAX_JOBS_PER_GPU})"
                )
                continue

            logger.debug(
                f"GPU {gpu.index}: {gpu.name}, "
                f"Free: {actual_free / (1024**3):.2f}GB, "
                f"Required: {required_with_buffer / (1024**3):.2f}GB, "
                f"Jobs: {current_jobs_on_gpu}/{self.MAX_JOBS_PER_GPU}"
            )

            if actual_free >= required_with_buffer:
                if actual_free > best_free:
                    best_free = actual_free
                    best_gpu = gpu.index

        return best_gpu

    def _get_available_vram(self) -> int:
        """Get total available VRAM across all GPUs"""
        if not HAS_NVML:
            return 24 * (1024**3)  # Fallback: assume 24GB

        gpus = self._get_gpu_status()
        return sum(gpu.free_vram for gpu in gpus)

    def _can_fit(self, vram_required: int, job: Job = None) -> bool:
        """Check if job can fit in available VRAM on any GPU"""
        if vram_required == 0:
            return True  # Cloud provider

        return self._find_best_gpu(vram_required, job=job) is not None

    def submit_job(
        self,
        job_id: str,
        provider_type: str,
        provider_name: str,
        model_id: str,
        vram_required: int,
        video_path: str,
        params: Dict,
        priority: int = 0,
    ) -> Job:
        """Submit a new job to the queue"""
        with self.lock:
            job = Job(
                job_id=job_id,
                provider_type=provider_type,
                provider_name=provider_name,
                model_id=model_id,
                vram_required=vram_required,
                priority=priority,
                video_path=video_path,
                params=params,
            )

            self.jobs[job_id] = job

            # Check if we can start immediately
            effective_vram = self._get_effective_vram_required(job)
            if effective_vram == 0 or self._can_fit(effective_vram, job=job):
                gpu_id = self._find_best_gpu(effective_vram, job=job) if effective_vram > 0 else 0
                self._start_job(job, gpu_id)
            else:
                self._add_to_queue(job)

            return job

    def _add_to_queue(self, job: Job):
        """Add job to priority queue"""
        job.status = JobStatus.QUEUED

        # Insert by priority (higher first), then by creation time
        insert_pos = len(self.queue)
        for i, queued_id in enumerate(self.queue):
            queued_job = self.jobs[queued_id]
            if job.priority > queued_job.priority:
                insert_pos = i
                break
            elif (
                job.priority == queued_job.priority
                and job.created_at < queued_job.created_at
            ):
                insert_pos = i
                break

        self.queue.insert(insert_pos, job.job_id)
        job.queue_position = insert_pos + 1

        # Update positions for all queued jobs
        for i, job_id in enumerate(self.queue):
            self.jobs[job_id].queue_position = i + 1

        logger.info(f"Job {job.job_id} queued at position {job.queue_position}")
        self._notify_callbacks("queued", job)

    def _start_job(self, job: Job, gpu_id: Optional[int] = None):
        """Start a job immediately"""
        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        job.queue_position = 0
        job.gpu_assigned = gpu_id
        self.running[job.job_id] = job

        # Track job per GPU
        if gpu_id is not None:
            if gpu_id not in self.running_per_gpu:
                self.running_per_gpu[gpu_id] = []
            self.running_per_gpu[gpu_id].append(job.job_id)

        # Remove from queue if present
        if job.job_id in self.queue:
            self.queue.remove(job.job_id)
            self._update_queue_positions()

        gpu_info = f" on GPU {gpu_id}" if gpu_id is not None else ""
        vram_info = (
            f" (VRAM: {job.vram_required / (1024**3):.2f}GB)"
            if job.vram_required > 0
            else ""
        )
        logger.info(f"Job {job.job_id} started{gpu_info}{vram_info}")
        self._notify_callbacks("started", job)

    def _process_queue(self):
        """Check queue and start jobs if VRAM available on any GPU"""
        with self.lock:
            if not self.queue:
                return

            # Get loaded Ollama models to avoid double-counting
            loaded_ollama_models = self._get_loaded_ollama_models()

            # Get current GPU status
            gpus = self._get_gpu_status() if HAS_NVML and self.gpus else []

            # Track VRAM already allocated to running jobs per GPU.
            # Skip jobs whose models are already loaded — nvidia-smi accounts for them.
            vram_allocated = {}
            for job in self.running.values():
                if job.gpu_assigned is not None:
                    if (
                        job.provider_type == "ollama"
                        and job.model_id in loaded_ollama_models
                    ):
                        continue
                    vram_allocated[job.gpu_assigned] = (
                        vram_allocated.get(job.gpu_assigned, 0) + job.vram_required
                    )

            # Initialize available VRAM per GPU (accounting for running jobs)
            gpu_vram_available = {}
            for gpu in gpus:
                gpu_vram_available[gpu.index] = gpu.free_vram - vram_allocated.get(
                    gpu.index, 0
                )

            # Try to start as many jobs as possible
            to_start = []
            remaining_queue = []

            for job_id in self.queue:
                job = self.jobs[job_id]

                if job.vram_required == 0:
                    # Cloud provider - can run on any "GPU" (no actual GPU needed)
                    # Use GPU 0 as default for tracking
                    to_start.append((job, 0))
                else:
                    # Use effective VRAM (reduced if model already loaded)
                    effective_vram = self._get_effective_vram_required(job)
                    required_with_buffer = int(effective_vram * self.VRAM_BUFFER)

                    # Find best GPU for this job considering VRAM already allocated in this batch
                    best_gpu = None
                    best_free = -1

                    for gpu_index, available_vram in gpu_vram_available.items():
                        # Check per-GPU job limit
                        current_jobs_on_gpu = len(
                            self.running_per_gpu.get(gpu_index, [])
                        )
                        if current_jobs_on_gpu >= self.MAX_JOBS_PER_GPU:
                            continue

                        if available_vram >= required_with_buffer:
                            if available_vram > best_free:
                                best_free = available_vram
                                best_gpu = gpu_index

                    if best_gpu is not None:
                        # Found a GPU with enough VRAM
                        to_start.append((job, best_gpu))
                        # Update available VRAM on this GPU for subsequent jobs in batch
                        gpu_vram_available[best_gpu] -= effective_vram
                    else:
                        # Not enough VRAM, keep in queue
                        remaining_queue.append(job_id)

            # Start all jobs that can fit
            for job, gpu_id in to_start:
                self._start_job(job, gpu_id)

            # Update queue with remaining jobs
            if remaining_queue != self.queue:
                self.queue = remaining_queue
                self._update_queue_positions()

    def _update_queue_positions(self):
        """Update queue position numbers after changes"""
        for i, job_id in enumerate(self.queue):
            self.jobs[job_id].queue_position = i + 1

    def complete_job(self, job_id: str, success: bool = True):
        """Mark job as completed or failed"""
        with self.lock:
            if job_id not in self.jobs:
                logger.warning(f"Complete called for unknown job: {job_id}")
                return

            job = self.jobs[job_id]
            job.completed_at = time.time()
            job.status = JobStatus.COMPLETED if success else JobStatus.FAILED

            if job_id in self.running:
                # Remove from per-GPU tracking
                if (
                    job.gpu_assigned is not None
                    and job.gpu_assigned in self.running_per_gpu
                ):
                    if job_id in self.running_per_gpu[job.gpu_assigned]:
                        self.running_per_gpu[job.gpu_assigned].remove(job_id)
                        # Clean up empty GPU list
                        if not self.running_per_gpu[job.gpu_assigned]:
                            del self.running_per_gpu[job.gpu_assigned]

                del self.running[job_id]

            logger.info(f"Job {job_id} {'completed' if success else 'failed'}")
            self._notify_callbacks("completed" if success else "failed", job)

            # Trigger queue processing
            self._process_queue()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or queued job"""
        with self.lock:
            if job_id not in self.jobs:
                return False

            job = self.jobs[job_id]

            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                return False

            job.status = JobStatus.CANCELLED
            job.completed_at = time.time()

            if job_id in self.queue:
                self.queue.remove(job_id)
                self._update_queue_positions()

            if job_id in self.running:
                # Remove from per-GPU tracking
                if (
                    job.gpu_assigned is not None
                    and job.gpu_assigned in self.running_per_gpu
                ):
                    if job_id in self.running_per_gpu[job.gpu_assigned]:
                        self.running_per_gpu[job.gpu_assigned].remove(job_id)
                        # Clean up empty GPU list
                        if not self.running_per_gpu[job.gpu_assigned]:
                            del self.running_per_gpu[job.gpu_assigned]

                del self.running[job_id]

            logger.info(f"Job {job_id} cancelled")
            self._notify_callbacks("cancelled", job)
            return True

    def update_priority(self, job_id: str, new_priority: int):
        """Update job priority and re-sort queue"""
        with self.lock:
            if job_id not in self.jobs:
                return False

            job = self.jobs[job_id]
            if job.status != JobStatus.QUEUED:
                return False

            job.priority = new_priority

            # Re-sort queue
            self.queue.remove(job_id)
            self._add_to_queue(job)
            return True

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def get_all_jobs(self) -> List[Job]:
        return list(self.jobs.values())

    def get_running_jobs(self) -> List[Job]:
        return list(self.running.values())

    def get_queued_jobs(self) -> List[Job]:
        return [self.jobs[jid] for jid in self.queue]

    def get_status(self) -> Dict:
        """Get current VRAM status for all GPUs"""
        gpus = self._get_gpu_status()

        if not gpus and not HAS_NVML:
            # Fallback
            return {
                "gpus": [],
                "total_vram": 24 * (1024**3),
                "available_vram": 24 * (1024**3),
                "used_vram": 0,
                "total_gb": 24,
                "available_gb": 24,
                "used_gb": 0,
                "running_count": len(self.running),
                "queued_count": len(self.queue),
                "nvml_available": False,
            }

        total_vram = sum(gpu.total_vram for gpu in gpus)
        available_vram = sum(gpu.free_vram for gpu in gpus)
        used_vram = sum(gpu.used_vram for gpu in gpus)

        return {
            "gpus": [
                {
                    "index": gpu.index,
                    "name": gpu.name,
                    "total_vram": gpu.total_vram,
                    "available_vram": gpu.free_vram,
                    "used_vram": gpu.used_vram,
                    "total_gb": round(gpu.total_vram / (1024**3), 2),
                    "available_gb": round(gpu.free_vram / (1024**3), 2),
                    "used_gb": round(gpu.used_vram / (1024**3), 2),
                }
                for gpu in gpus
            ],
            "total_vram": total_vram,
            "available_vram": available_vram,
            "used_vram": used_vram,
            "total_gb": round(total_vram / (1024**3), 2),
            "available_gb": round(available_vram / (1024**3), 2),
            "used_gb": round(used_vram / (1024**3), 2),
            "running_count": len(self.running),
            "queued_count": len(self.queue),
            "nvml_available": HAS_NVML,
        }

    def register_callback(self, callback: Callable):
        """Register callback for job status changes"""
        self.callbacks.append(callback)

    def _notify_callbacks(self, event: str, job: Job):
        """Notify all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(event, job)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _start_monitor(self):
        """Start background thread to process queue"""

        def monitor():
            while True:
                self._process_queue()
                time.sleep(self.CHECK_INTERVAL)

        threading.Thread(target=monitor, daemon=True).start()
        logger.info("VRAM manager monitor started")


# Global instance
vram_manager = VRAMManager()
