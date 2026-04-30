"""
Unit tests for Chat Queue Manager
"""

import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import sys
import time
import threading
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from chat_queue import ChatQueueManager, ChatJobStatus


def _make_manager():
    """Helper: create a ChatQueueManager instance without starting the worker thread."""
    manager = ChatQueueManager.__new__(ChatQueueManager)
    manager.jobs = {}
    manager.queue = []
    manager.running = {}
    manager.lock = threading.RLock()
    manager.callbacks = []
    manager.rate_limit_window = []
    manager.worker_thread = None
    return manager


class TestChatQueueInitialization:
    """Tests for Chat Queue Manager initialization"""

    def test_init_sets_defaults(self):
        """Test that manager initializes with correct defaults"""
        manager = _make_manager()
        manager._start_worker()

        # Worker thread should be started and be a daemon
        assert manager.worker_thread is not None
        assert manager.worker_thread.daemon is True
        assert manager.worker_thread.is_alive()


class TestRateLimiting:
    """Tests for rate limiting functionality"""

    def test_check_rate_limit_under_limit(self):
        """Test rate limit check when under limit"""
        manager = _make_manager()

        # 5 recent jobs — well under the 30/min limit
        manager.rate_limit_window = [
            time.time() - 50,
            time.time() - 40,
            time.time() - 30,
            time.time() - 20,
            time.time() - 10,
        ]

        assert manager._check_rate_limit() is True

    def test_check_rate_limit_over_limit(self):
        """Test rate limit check when over limit"""
        manager = _make_manager()

        # 31 recent jobs — over the 30/min limit
        now = time.time()
        manager.rate_limit_window = [now - i for i in range(31)]

        assert manager._check_rate_limit() is False


class TestProcessQueue:
    """Tests for background queue processing"""

    def test_process_queue_max_concurrent(self):
        """Test that queue respects MAX_CONCURRENT_JOBS limit"""
        manager = _make_manager()
        # Simulate 5 running jobs (at the limit)
        manager.running = {f"job{i}": MagicMock() for i in range(5)}
        manager.queue = ["job6", "job7"]
        manager.jobs = {
            jid: MagicMock() for jid in list(manager.running) + manager.queue
        }

        # _process_queue should exit early without starting anything new
        before_running = len(manager.running)
        manager._process_queue()
        assert len(manager.running) == before_running

    def test_process_queue_starts_next(self):
        """Test that next job in queue starts when slot available"""
        manager = _make_manager()

        job_id = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        # Queue should contain the job
        assert job_id in manager.queue


class TestSubmitJob:
    """Tests for job submission"""

    def test_submit_job_generates_id(self):
        """Test that job submission generates unique job ID"""
        manager = _make_manager()

        job_id = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        assert job_id.startswith("chat_")
        assert len(job_id) == 13  # "chat_" (5) + 8 hex chars

    def test_submit_job_adds_to_queue(self):
        """Test that newly submitted job is added to queue"""
        manager = _make_manager()

        job_id = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        assert job_id in manager.queue
        assert manager.jobs[job_id].status == ChatJobStatus.PENDING

    def test_submit_job_higher_priority_first(self):
        """Test that higher priority jobs are queued first"""
        manager = _make_manager()

        # Submit low priority first
        job_low = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
            priority=1,
        )

        # Submit high priority second
        job_high = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
            priority=10,
        )

        # High priority should be first
        assert manager.queue[0].startswith("chat_")
        assert manager.queue.index(job_high) < manager.queue.index(job_low)

    def test_submit_job_missing_required_fields(self):
        """Test that submission fails with missing required fields"""
        manager = _make_manager()

        # Missing model
        with pytest.raises(ValueError):
            manager.submit_job(
            provider_type="litellm",
                model_id="",
                prompt="Test",
                content="Content",
                api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
            )


class TestGetJobStatus:
    """Tests for job status retrieval"""

    def test_get_job_status_exists(self):
        """Test getting status of existing job"""
        manager = _make_manager()

        job_id = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        status = manager.get_job_status(job_id)
        assert status is not None
        assert status["job_id"] == job_id
        assert "status" in status

    def test_get_job_status_not_found(self):
        """Test getting status of non-existent job"""
        manager = _make_manager()

        status = manager.get_job_status("nonexistent_job_id")
        assert status is None

    def test_job_status_fields(self):
        """Test that job status includes all required fields"""
        manager = _make_manager()

        job_id = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        status = manager.get_job_status(job_id)
        assert "job_id" in status
        assert "provider_type" in status
        assert "model_id" in status
        assert "status" in status
        assert "queue_position" in status
        assert "created_at" in status


class TestCancelJob:
    """Tests for job cancellation"""

    def test_cancel_queued_job(self):
        """Test cancelling a queued job"""
        manager = _make_manager()

        job_id = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        result = manager.cancel_job(job_id)

        assert result is True
        assert manager.jobs[job_id].status == ChatJobStatus.CANCELLED

    def test_cancel_running_job_fails(self):
        """Test that cancelling a running job returns False"""
        manager = _make_manager()

        job_id = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        # Simulate job is running
        manager.jobs[job_id].status = ChatJobStatus.RUNNING

        # Cancel should fail for running jobs
        result = manager.cancel_job(job_id)
        assert result is False

    def test_cancel_completed_job_fails(self):
        """Test that cancelling completed job returns False"""
        manager = _make_manager()

        job_id = manager.submit_job(
            provider_type="litellm",
            model_id="test-model",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        # Simulate job is completed
        manager.jobs[job_id].status = ChatJobStatus.COMPLETED

        result = manager.cancel_job(job_id)
        assert result is False


class TestQueueStats:
    """Tests for queue statistics"""

    def test_queue_stats_structure(self):
        """Test that queue stats returns correct structure"""
        manager = _make_manager()

        # Add some jobs
        job1 = manager.submit_job(
            provider_type="litellm",
            model_id="test",
            prompt="Test",
            content="Content",
            api_key="",
            litellm_url="http://172.16.17.3:4000/v1",
        )

        manager.jobs[job1].status = ChatJobStatus.RUNNING

        stats = manager.get_queue_stats()

        assert "total_jobs" in stats
        assert "queued" in stats
        assert "running" in stats
        assert "recent_completed" in stats
        assert "rate_limit_window" in stats


class TestWorkerLoop:
    """Tests for background worker loop"""

    def test_worker_loop_starts(self):
        """Test that worker loop thread starts"""
        manager = _make_manager()

        manager._start_worker()

        # Worker thread should be a daemon and alive
        assert manager.worker_thread is not None
        assert manager.worker_thread.daemon is True
        assert manager.worker_thread.is_alive()


class TestCleanRateLimitWindow:
    """Tests for rate limit window cleaning"""

    def test_clean_rate_limit_window_removes_old(self):
        """Test that old timestamps are removed from window"""
        manager = _make_manager()
        manager.rate_limit_window = [
            time.time() - 120,  # Old (2 min ago)
            time.time() - 90,  # Old (1.5 min ago)
            time.time() - 30,  # Recent (30 sec ago)
            time.time() - 10,  # Recent (10 sec ago)
        ]

        manager._clean_rate_limit_window()

        # Only recent timestamps should remain
        assert len(manager.rate_limit_window) == 2
        assert all(t > time.time() - 60 for t in manager.rate_limit_window)
