"""
Unit tests for VRAM Manager
"""

import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vram_manager import VRAMManager, JobStatus, GPUInfo


class TestVRAMManagerInitialization:
    """Tests for VRAM manager initialization"""

    @pytest.fixture
    def mock_pynvml(self):
        """Mock pynvml module"""
        with patch.dict("sys.modules", {"pynvml": MagicMock()}):
            import pynvml

            pynvml.nvmlInit.return_value = None
            pynvml.nvmlDeviceGetCount.return_value = 2

            mock_handle = MagicMock()
            memory_info = MagicMock()
            memory_info.total = 10 * (1024**3)
            memory_info.used = 2 * (1024**3)
            memory_info.free = 8 * (1024**3)
            pynvml.nvmlDeviceGetMemoryInfo.return_value = memory_info
            pynvml.nvmlDeviceGetName.return_value = b"Test GPU"
            pynvml.nvmlDeviceGetHandleByIndex.return_value = mock_handle

            yield pynvml

    def test_init_with_nvml(self, mock_pynvml):
        """Test initialization with NVML available"""
        import vram_manager as vm_module
        from vram_manager import VRAMManager, GPUInfo

        manager = VRAMManager.__new__(VRAMManager)
        manager.jobs = {}
        manager.queue = []
        manager.running = {}
        manager.running_per_gpu = {}
        manager.lock = MagicMock()
        manager.callbacks = []
        manager.gpus = []

        # Patch the pynvml reference inside vram_manager module
        with (
            patch.object(vm_module, "pynvml", mock_pynvml),
            patch.object(vm_module, "HAS_NVML", True),
        ):
            manager._init_nvml()

        assert len(manager.gpus) == 2
        assert manager.gpus[0].name == "Test GPU"
        assert manager.gpus[0].total_vram == 10 * (1024**3)

    def test_init_without_nvml(self):
        """Test initialization without NVML"""
        manager = VRAMManager.__new__(VRAMManager)
        manager.jobs = {}
        manager.queue = []
        manager.running = {}
        manager.running_per_gpu = {}
        manager.lock = MagicMock()
        manager.callbacks = []
        manager.gpus = []

        with patch("vram_manager.HAS_NVML", False):
            manager._init_nvml()

        assert manager.gpus == []


class TestFindBestGPU:
    """Tests for GPU selection algorithm"""

    def test_find_best_gpu_enough_vram(self, setup_vram_manager):
        """Test finding GPU with enough VRAM"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=2 * (1024**3),
            free_vram=8 * (1024**3),
        )

        manager.gpus = [mock_gpu0]
        with (
            patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]),
            patch("vram_manager.HAS_NVML", True),
        ):
            result = manager._find_best_gpu(5 * (1024**3))
            assert result == 0

    def test_find_best_gpu_insufficient_vram(self, setup_vram_manager):
        """Test finding GPU with insufficient VRAM"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=8 * (1024**3),
            free_vram=2 * (1024**3),
        )

        manager.gpus = [mock_gpu0]
        with (
            patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]),
            patch("vram_manager.HAS_NVML", True),
        ):
            result = manager._find_best_gpu(5 * (1024**3))
            assert result is None

    def test_find_best_gpu_prefers_larger_free(self, setup_vram_manager):
        """Test that manager prefers GPU with more free VRAM"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=2 * (1024**3),
            free_vram=8 * (1024**3),
        )
        mock_gpu1 = GPUInfo(
            index=1,
            name="RTX 3090",
            total_vram=24 * (1024**3),
            used_vram=4 * (1024**3),
            free_vram=20 * (1024**3),
        )

        manager.gpus = [mock_gpu0, mock_gpu1]
        with (
            patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0, mock_gpu1]),
            patch("vram_manager.HAS_NVML", True),
        ):
            result = manager._find_best_gpu(5 * (1024**3))
            assert result == 1  # GPU 1 has more free VRAM

    def test_find_best_gpu_job_limit(self, setup_vram_manager):
        """Test that MAX_JOBS_PER_GPU limit is respected"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=2 * (1024**3),
            free_vram=8 * (1024**3),
        )

        # Simulate GPU at job limit
        manager.running_per_gpu[0] = ["job1", "job2"]
        manager.gpus = [mock_gpu0]

        with (
            patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]),
            patch("vram_manager.HAS_NVML", True),
        ):
            result = manager._find_best_gpu(5 * (1024**3))
            assert result is None  # GPU at limit

    def test_find_best_gpu_cloud_provider(self, setup_vram_manager):
        """Test that cloud providers (vram_required=0) get GPU 0"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=9 * (1024**3),
            free_vram=1 * (1024**3),
        )

        with patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]):
            result = manager._find_best_gpu(0)
            assert result == 0

    def test_find_best_gpu_with_allocated_vram(self, setup_vram_manager):
        """Test GPU selection considering batch allocation"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=2 * (1024**3),
            free_vram=8 * (1024**3),
        )

        manager.gpus = [mock_gpu0]
        with (
            patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]),
            patch("vram_manager.HAS_NVML", True),
        ):
            # Allocate 4GB in batch
            result = manager._find_best_gpu(
                3 * (1024**3), vram_allocated={0: 4 * (1024**3)}
            )
            # 3GB fits: 8GB free - 4GB allocated = 4GB available >= 3GB * 1.2 buffer = 3.6GB
            assert result == 0

    def test_find_best_gpu_insufficient_vram(self, setup_vram_manager):
        """Test finding GPU with insufficient VRAM"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=8 * (1024**3),
            free_vram=2 * (1024**3),
        )

        with patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]):
            result = manager._find_best_gpu(5 * (1024**3))
            assert result is None

    def test_find_best_gpu_prefers_larger_free(self, setup_vram_manager):
        """Test that manager prefers GPU with more free VRAM"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=2 * (1024**3),
            free_vram=8 * (1024**3),
        )
        mock_gpu1 = GPUInfo(
            index=1,
            name="RTX 3090",
            total_vram=24 * (1024**3),
            used_vram=4 * (1024**3),
            free_vram=20 * (1024**3),
        )

        with patch.object(
            manager, "_get_gpu_status", return_value=[mock_gpu0, mock_gpu1]
        ):
            result = manager._find_best_gpu(5 * (1024**3))
            assert result == 1  # GPU 1 has more free VRAM

    def test_find_best_gpu_job_limit(self, setup_vram_manager):
        """Test that MAX_JOBS_PER_GPU limit is respected"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=2 * (1024**3),
            free_vram=8 * (1024**3),
        )

        # Simulate GPU at job limit
        manager.running_per_gpu[0] = ["job1", "job2"]

        with patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]):
            result = manager._find_best_gpu(5 * (1024**3))
            assert result is None  # GPU at limit

    def test_find_best_gpu_cloud_provider(self, setup_vram_manager):
        """Test that cloud providers (vram_required=0) get GPU 0"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=9 * (1024**3),
            free_vram=1 * (1024**3),
        )

        with patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]):
            result = manager._find_best_gpu(0)
            assert result == 0

    def test_find_best_gpu_with_allocated_vram(self, setup_vram_manager):
        """Test GPU selection considering batch allocation"""
        manager = setup_vram_manager

        mock_gpu0 = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=2 * (1024**3),
            free_vram=8 * (1024**3),
        )

        with patch.object(manager, "_get_gpu_status", return_value=[mock_gpu0]):
            # Allocate 4GB in batch
            result = manager._find_best_gpu(
                3 * (1024**3), vram_allocated={0: 4 * (1024**3)}
            )
            # 3GB fits: 8GB free - 4GB allocated = 4GB available >= 3GB * 1.2 buffer = 3.6GB
            assert result == 0


class TestJobQueue:
    """Tests for job queue management"""

    def test_submit_job_immediate_start(self, setup_vram_manager):
        """Test that job starting immediately doesn't go to queue"""
        manager = setup_vram_manager

        job = manager.submit_job(
            job_id="job1",
            provider_type="openrouter",  # Cloud, always starts
            provider_name="OpenRouter",
            model_id="test-model",
            vram_required=0,
            video_path="/test.mp4",
            params={},
            priority=0,
        )

        assert job.status == JobStatus.RUNNING
        assert "job1" not in manager.queue
        assert "job1" in manager.running

    def test_submit_job_queued(self, setup_vram_manager):
        """Test that high VRAM job goes to queue"""
        manager = setup_vram_manager

        mock_gpu = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=8 * (1024**3),
            free_vram=2 * (1024**3),
        )
        manager.gpus = [mock_gpu]

        with (
            patch.object(manager, "_get_gpu_status", return_value=[mock_gpu]),
            patch("vram_manager.HAS_NVML", True),
        ):
            job = manager.submit_job(
                job_id="job1",
                provider_type="ollama",
                provider_name="Ollama",
                model_id="test-model",
                vram_required=100 * (1024**3),  # Very high, won't fit
                video_path="/test.mp4",
                params={},
                priority=0,
            )

        assert job.status == JobStatus.QUEUED
        assert "job1" in manager.queue
        assert job.queue_position == 1

    def test_priority_queue_ordering(self, setup_vram_manager):
        """Test that higher priority jobs are queued first"""
        manager = setup_vram_manager

        # Submit low priority first
        job_low = manager.submit_job(
            job_id="job_low",
            provider_type="ollama",
            provider_name="Ollama",
            model_id="test",
            vram_required=100 * (1024**3),
            video_path="/test.mp4",
            params={},
            priority=1,
        )

        # Submit high priority second
        job_high = manager.submit_job(
            job_id="job_high",
            provider_type="ollama",
            provider_name="Ollama",
            model_id="test",
            vram_required=100 * (1024**3),
            video_path="/test.mp4",
            params={},
            priority=10,
        )

        # High priority should be first in queue
        assert manager.queue[0] == "job_high"
        assert manager.queue[1] == "job_low"

    def test_queue_position_updates(self, setup_vram_manager):
        """Test queue position numbers update correctly"""
        manager = setup_vram_manager

        # Queue multiple jobs
        manager.submit_job(
            job_id="job1",
            provider_type="ollama",
            provider_name="Ollama",
            model_id="test",
            vram_required=100 * (1024**3),
            video_path="/test.mp4",
            params={},
            priority=1,
        )
        manager.submit_job(
            job_id="job2",
            provider_type="ollama",
            provider_name="Ollama",
            model_id="test",
            vram_required=100 * (1024**3),
            video_path="/test.mp4",
            params={},
            priority=2,
        )
        manager.submit_job(
            job_id="job3",
            provider_type="ollama",
            provider_name="Ollama",
            model_id="test",
            vram_required=100 * (1024**3),
            video_path="/test.mp4",
            params={},
            priority=3,
        )

        # After submission, job3 has the highest priority so it should be first
        assert "job3" in manager.queue
        assert manager.jobs["job3"].queue_position == 1
        assert manager.jobs["job1"].queue_position == 3


class TestVRAMManagerStartProcessQueue:
    """Tests for background queue processing"""

    def test_process_queue_starts_jobs(self, setup_vram_manager):
        """Test that _process_queue starts jobs when VRAM available"""
        manager = setup_vram_manager

        # Manually add a job to queue
        job = MagicMock()
        job.job_id = "queued_job"
        job.vram_required = 0  # Cloud provider
        job.status = JobStatus.QUEUED
        manager.queue = ["queued_job"]
        manager.jobs = {"queued_job": job}

        with patch.object(manager, "_start_job") as mock_start:
            manager._process_queue()
            mock_start.assert_called_once()


class TestCompleteJob:
    """Tests for job completion"""

    def test_complete_job_removes_from_running(self, setup_vram_manager):
        """Test that completed job is removed from running dict"""
        manager = setup_vram_manager

        # Add job to running AND jobs dict
        job = MagicMock()
        job.job_id = "running_job"
        job.gpu_assigned = 0
        manager.jobs["running_job"] = job
        manager.running["running_job"] = job
        manager.running_per_gpu[0] = ["running_job"]

        manager.complete_job("running_job", success=True)

        assert "running_job" not in manager.running

    def test_complete_job_triggers_queue_processing(self, setup_vram_manager):
        """Test that completing a job triggers queue processing"""
        manager = setup_vram_manager

        # Queue and running jobs
        queued_job = MagicMock()
        queued_job.job_id = "queued_job"
        queued_job.vram_required = 0
        manager.queue = ["queued_job"]
        manager.jobs = {"queued_job": queued_job}

        running_job = MagicMock()
        running_job.job_id = "running_job"
        running_job.gpu_assigned = 0
        manager.jobs["running_job"] = running_job
        manager.running["running_job"] = running_job
        manager.running_per_gpu[0] = ["running_job"]

        with patch.object(manager, "_process_queue") as mock_process:
            manager.complete_job("running_job", success=True)
            mock_process.assert_called_once()


class TestCancelJob:
    """Tests for job cancellation"""

    def test_cancel_queued_job(self, setup_vram_manager):
        """Test cancelling a queued job"""
        manager = setup_vram_manager

        job = MagicMock()
        job.job_id = "queued_job"
        job.status = JobStatus.QUEUED
        manager.queue = ["queued_job"]
        manager.jobs = {"queued_job": job}

        result = manager.cancel_job("queued_job")

        assert result is True
        assert job.status == JobStatus.CANCELLED
        assert "queued_job" not in manager.queue

    def test_cancel_running_job(self, setup_vram_manager):
        """Test cancelling a running job"""
        manager = setup_vram_manager

        job = MagicMock()
        job.job_id = "running_job"
        job.status = JobStatus.RUNNING
        job.gpu_assigned = 0
        manager.running["running_job"] = job
        manager.jobs = {"running_job": job}

        result = manager.cancel_job("running_job")

        assert result is True
        assert job.status == JobStatus.CANCELLED
        assert "running_job" not in manager.running

    def test_cancel_completed_job_fails(self, setup_vram_manager):
        """Test that cancelling completed job returns False"""
        manager = setup_vram_manager

        job = MagicMock()
        job.job_id = "completed_job"
        job.status = JobStatus.COMPLETED
        manager.jobs = {"completed_job": job}

        result = manager.cancel_job("completed_job")

        assert result is False

    def test_cancel_nonexistent_job_fails(self, setup_vram_manager):
        """Test that cancelling non-existent job returns False"""
        manager = setup_vram_manager

        result = manager.cancel_job("nonexistent_job")
        assert result is False


class TestVRAMManagerStatus:
    """Tests for status reporting"""

    def test_get_status(self, setup_vram_manager):
        """Test get_status returns correct structure"""
        manager = setup_vram_manager

        with patch.object(manager, "_get_gpu_status", return_value=[]):
            status = manager.get_status()

            assert "gpus" in status
            assert "total_vram" in status
            assert "available_vram" in status
            assert "running_count" in status
            assert "queued_count" in status
            assert "nvml_available" in status

    def test_get_running_jobs(self, setup_vram_manager):
        """Test get_running_jobs returns running jobs"""
        manager = setup_vram_manager

        job1 = MagicMock()
        job1.job_id = "job1"
        job1.gpu_assigned = 0

        job2 = MagicMock()
        job2.job_id = "job2"
        job2.gpu_assigned = 1

        manager.running = {"job1": job1, "job2": job2}

        running = manager.get_running_jobs()
        assert len(running) == 2
        assert job1 in running
        assert job2 in running

    def test_get_queued_jobs(self, setup_vram_manager):
        """Test get_queued_jobs returns queued jobs"""
        manager = setup_vram_manager

        job1 = MagicMock()
        job1.job_id = "job1"

        job2 = MagicMock()
        job2.job_id = "job2"

        manager.queue = ["job1", "job2"]
        manager.jobs = {"job1": job1, "job2": job2}

        queued = manager.get_queued_jobs()
        assert len(queued) == 2
        assert job1 in queued
        assert job2 in queued


class TestOllamaAlreadyLoaded:
    """Tests for ollama ps integration - already-loaded model detection"""

    def test_effective_vram_full_when_model_not_loaded(self, setup_vram_manager):
        """When model is not loaded, effective VRAM equals full requirement"""
        manager = setup_vram_manager
        manager.set_ollama_running_models_provider(lambda: set())

        job = MagicMock()
        job.provider_type = "ollama"
        job.model_id = "llava:7b"
        job.vram_required = 8 * (1024**3)

        effective = manager._get_effective_vram_required(job)
        assert effective == 8 * (1024**3)

    def test_effective_vram_reduced_when_model_already_loaded(self, setup_vram_manager):
        """When model is already loaded, effective VRAM is just context overhead"""
        manager = setup_vram_manager
        manager.set_ollama_running_models_provider(lambda: {"llava:7b", "gemma3:4b"})

        job = MagicMock()
        job.provider_type = "ollama"
        job.model_id = "llava:7b"
        job.vram_required = 8 * (1024**3)

        effective = manager._get_effective_vram_required(job)
        assert effective == manager.CONTEXT_VRAM_OVERHEAD

    def test_effective_vram_cloud_provider_unchanged(self, setup_vram_manager):
        """Cloud providers (vram=0) are not affected by ollama ps check"""
        manager = setup_vram_manager
        manager.set_ollama_running_models_provider(lambda: {"some-model"})

        job = MagicMock()
        job.provider_type = "openrouter"
        job.model_id = "some-model"
        job.vram_required = 0

        effective = manager._get_effective_vram_required(job)
        assert effective == 0

    def test_effective_vram_without_provider(self, setup_vram_manager):
        """Without ollama provider, full VRAM is required"""
        manager = setup_vram_manager

        job = MagicMock()
        job.provider_type = "ollama"
        job.model_id = "llava:7b"
        job.vram_required = 8 * (1024**3)

        effective = manager._get_effective_vram_required(job)
        assert effective == 8 * (1024**3)

    def test_submit_job_starts_immediately_when_model_loaded(self, setup_vram_manager):
        """A second job with an already-loaded model should start, not queue"""
        manager = setup_vram_manager

        mock_gpu = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=8 * (1024**3),
            free_vram=2 * (1024**3),
        )

        manager.set_ollama_running_models_provider(lambda: {"llava:7b"})

        with patch.object(manager, "_get_gpu_status", return_value=[mock_gpu]):
            job = manager.submit_job(
                job_id="job1",
                provider_type="ollama",
                provider_name="Ollama-Local",
                model_id="llava:7b",
                vram_required=8 * (1024**3),
                video_path="/test.mp4",
                params={},
                priority=0,
            )

        assert job.status == JobStatus.RUNNING
        assert "job1" not in manager.queue

    def test_submit_job_queues_when_model_not_loaded_and_vram_tight(
        self, setup_vram_manager
    ):
        """When model is NOT loaded and VRAM is tight, job should queue"""
        manager = setup_vram_manager

        mock_gpu = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=10 * (1024**3),
            used_vram=8 * (1024**3),
            free_vram=2 * (1024**3),
        )

        manager.set_ollama_running_models_provider(lambda: set())

        with patch.object(manager, "_get_gpu_status", return_value=[mock_gpu]):
            job = manager.submit_job(
                job_id="job1",
                provider_type="ollama",
                provider_name="Ollama-Local",
                model_id="llava:7b",
                vram_required=8 * (1024**3),
                video_path="/test.mp4",
                params={},
                priority=0,
            )

        assert job.status == JobStatus.QUEUED
        assert "job1" in manager.queue

    def test_no_double_counting_running_job_vram(self, setup_vram_manager):
        """Running job with already-loaded model should not double-count VRAM"""
        manager = setup_vram_manager

        mock_gpu = GPUInfo(
            index=0,
            name="RTX 3080",
            total_vram=24 * (1024**3),
            used_vram=10 * (1024**3),
            free_vram=14 * (1024**3),
        )

        manager.set_ollama_running_models_provider(lambda: {"llava:7b"})

        running_job = MagicMock()
        running_job.job_id = "running_job"
        running_job.provider_type = "ollama"
        running_job.model_id = "llava:7b"
        running_job.vram_required = 10 * (1024**3)
        running_job.gpu_assigned = 0
        manager.running["running_job"] = running_job
        manager.running_per_gpu[0] = ["running_job"]

        new_job = MagicMock()
        new_job.provider_type = "ollama"
        new_job.model_id = "llava:7b"
        new_job.vram_required = 10 * (1024**3)

        with patch.object(manager, "_get_gpu_status", return_value=[mock_gpu]):
            gpu = manager._find_best_gpu(10 * (1024**3), job=new_job)
            assert gpu is not None, "Should find a GPU since model is already loaded and no double-counting"

    def test_provider_callback_exception_returns_empty(self, setup_vram_manager):
        """If the provider callback raises, treat as no models loaded"""
        manager = setup_vram_manager
        manager.set_ollama_running_models_provider(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        job = MagicMock()
        job.provider_type = "ollama"
        job.model_id = "llava:7b"
        job.vram_required = 8 * (1024**3)

        effective = manager._get_effective_vram_required(job)
        assert effective == 8 * (1024**3)
