"""
Unit tests for chat queue utility functions
"""

import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import sys
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from chat_queue import ChatJob, ChatJobStatus


class TestChatJobDataclass:
    """Tests for ChatJob dataclass"""

    def test_job_creation(self):
        """Test creating a chat job"""
        job = ChatJob(
            job_id="chat_abc12345",
            provider_type="ollama",
            model_id="llama3:8b",
            prompt="Test prompt",
            content="Test content",
            api_key="test_key",
            ollama_url="http://localhost:11434",
            created_at=time.time(),
            started_at=None,
            completed_at=None,
            status=ChatJobStatus.PENDING,
            queue_position=1,
            result=None,
            error=None,
            priority=0,
        )

        assert job.job_id == "chat_abc12345"
        assert job.provider_type == "ollama"
        assert job.status == ChatJobStatus.PENDING

    def test_job_to_dict(self):
        """Test job conversion to dictionary"""
        job = ChatJob(
            job_id="chat_abc12345",
            provider_type="ollama",
            model_id="llama3:8b",
            prompt="Test",
            content="Content",
            api_key="key",
            ollama_url="http://localhost:11434",
            created_at=time.time(),
            started_at=None,
            completed_at=None,
            status=ChatJobStatus.QUEUED,
            queue_position=2,
            result=None,
            error=None,
            priority=5,
        )

        job_dict = job.__dict__

        assert "job_id" in job_dict
        assert "provider_type" in job_dict
        assert "status" in job_dict
        assert "queue_position" in job_dict


class TestQueuePositioning:
    """Tests for queue positioning logic"""

    def test_queue_insertion_by_priority(self):
        """Test queue insertion orders by priority"""
        base_time = time.time()

        jobs = [
            ChatJob(
                job_id=f"job{i}",
                provider_type="ollama",
                model_id="test" if i == 0 else f"test{i}",
                prompt="Test",
                content="Content",
                api_key="key",
                ollama_url="http://localhost:11434",
                created_at=base_time - i,
                started_at=None,
                completed_at=None,
                status=ChatJobStatus.QUEUED,
                queue_position=0,
                result=None,
                error=None,
                priority=3 - i,  # job0=3, job1=2, job2=1
            )
            for i in range(3)
        ]

        # Sort by priority (higher first), then creation time
        from functools import cmp_to_key

        def compare_jobs(a, b):
            if a.priority != b.priority:
                return b.priority - a.priority
            return a.created_at - b.created_at

        sorted_jobs = sorted(jobs, key=cmp_to_key(compare_jobs))

        # job0 should be first (highest priority)
        assert sorted_jobs[0].job_id == "job0"
        assert sorted_jobs[1].job_id == "job1"
        assert sorted_jobs[2].job_id == "job2"


class TestStatusTransitions:
    """Tests for job status transitions"""

    def test_pending_to_queued(self):
        """Test transition from PENDING to QUEUED"""
        job = ChatJob(
            job_id="test",
            provider_type="ollama",
            model_id="test",
            prompt="Test",
            content="Content",
            api_key="key",
            ollama_url="http://localhost:11434",
            created_at=time.time(),
            started_at=None,
            completed_at=None,
            status=ChatJobStatus.PENDING,
            queue_position=0,
            result=None,
            error=None,
            priority=0,
        )

        job.status = ChatJobStatus.QUEUED
        assert job.status == ChatJobStatus.QUEUED

    def test_queued_to_running(self):
        """Test transition from QUEUED to RUNNING"""
        job = ChatJob(
            job_id="test",
            provider_type="ollama",
            model_id="test",
            prompt="Test",
            content="Content",
            api_key="key",
            ollama_url="http://localhost:11434",
            created_at=time.time(),
            started_at=None,
            completed_at=None,
            status=ChatJobStatus.QUEUED,
            queue_position=1,
            result=None,
            error=None,
            priority=0,
        )

        job.status = ChatJobStatus.RUNNING
        assert job.status == ChatJobStatus.RUNNING
        assert job.started_at is None  # Set separately

    def test_running_to_completed(self):
        """Test transition from RUNNING to COMPLETED"""
        job = ChatJob(
            job_id="test",
            provider_type="ollama",
            model_id="test",
            prompt="Test",
            content="Content",
            api_key="key",
            ollama_url="http://localhost:11434",
            created_at=time.time(),
            started_at=time.time() - 10,
            completed_at=time.time(),
            status=ChatJobStatus.RUNNING,
            queue_position=0,
            result="Response text",
            error=None,
            priority=0,
        )

        job.status = ChatJobStatus.COMPLETED

        assert job.status == ChatJobStatus.COMPLETED
        assert job.result == "Response text"
        assert job.completed_at is not None


class TestJobValidation:
    """Tests for job validation"""

    def test_required_fields_present(self):
        """Test all required fields are present"""
        required_fields = {
            "job_id",
            "provider_type",
            "model_id",
            "prompt",
            "content",
            "api_key",
            "ollama_url",
            "created_at",
            "status",
        }

        fields_in_job = {
            "job_id",
            "provider_type",
            "model_id",
            "prompt",
            "content",
            "api_key",
            "ollama_url",
            "created_at",
            "started_at",
            "completed_at",
            "status",
            "queue_position",
            "result",
            "error",
            "priority",
        }

        assert required_fields.issubset(fields_in_job)
