"""Unit tests for TaskQueueManager Protocol and Pydantic models.

Tests cover:
- TaskQueueManager Protocol contract (enqueue, dequeue, ack, nack, schedule, get_job, get_dlq_jobs)
- Protocol is runtime-checkable
- JobStatus enum values
- Job Pydantic model validation
- JobRef Pydantic model validation
- QueueConfig Pydantic model validation and defaults

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus, QueueConfig
from core_infrastructure.taskqueue.ports import TaskQueueManager


class TestTaskQueueManagerProtocol:
    """Verify TaskQueueManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """TaskQueueManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(TaskQueueManager, "_is_runtime_protocol") or hasattr(
            TaskQueueManager, "__protocol_attrs__"
        )

    def test_has_enqueue_method(self) -> None:
        """Protocol requires async enqueue(queue_name, payload, options)."""
        assert hasattr(TaskQueueManager, "enqueue")

    def test_has_dequeue_method(self) -> None:
        """Protocol requires async dequeue(queue_name)."""
        assert hasattr(TaskQueueManager, "dequeue")

    def test_has_ack_method(self) -> None:
        """Protocol requires async ack(job_id)."""
        assert hasattr(TaskQueueManager, "ack")

    def test_has_nack_method(self) -> None:
        """Protocol requires async nack(job_id, requeue)."""
        assert hasattr(TaskQueueManager, "nack")

    def test_has_schedule_method(self) -> None:
        """Protocol requires async schedule(queue_name, payload, execute_at, options)."""
        assert hasattr(TaskQueueManager, "schedule")

    def test_has_get_job_method(self) -> None:
        """Protocol requires async get_job(job_id) -> Job | None."""
        assert hasattr(TaskQueueManager, "get_job")

    def test_has_get_dlq_jobs_method(self) -> None:
        """Protocol requires async get_dlq_jobs(queue_name) -> list[Job]."""
        assert hasattr(TaskQueueManager, "get_dlq_jobs")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all TaskQueueManager methods satisfies the protocol."""

        class ValidTaskQueue:
            async def enqueue(self, queue_name, payload, options=None): ...
            async def dequeue(self, queue_name): ...
            async def ack(self, job_id) -> None: ...
            async def nack(self, job_id, requeue) -> None: ...
            async def schedule(self, queue_name, payload, execute_at, options=None): ...
            async def get_job(self, job_id): ...
            async def get_dlq_jobs(self, queue_name): ...

        assert isinstance(ValidTaskQueue(), TaskQueueManager)

    def test_class_missing_enqueue_fails_protocol(self) -> None:
        """A class without enqueue() does NOT satisfy TaskQueueManager."""

        class Incomplete:
            async def dequeue(self, queue_name): ...

        assert not isinstance(Incomplete(), TaskQueueManager)


class TestJobStatusEnum:
    """Verify JobStatus enum values."""

    def test_pending_status(self) -> None:
        """JobStatus.PENDING is available."""
        assert JobStatus.PENDING.value == "PENDING"

    def test_running_status(self) -> None:
        """JobStatus.RUNNING is available."""
        assert JobStatus.RUNNING.value == "RUNNING"

    def test_completed_status(self) -> None:
        """JobStatus.COMPLETED is available."""
        assert JobStatus.COMPLETED.value == "COMPLETED"

    def test_failed_status(self) -> None:
        """JobStatus.FAILED is available."""
        assert JobStatus.FAILED.value == "FAILED"

    def test_dead_status(self) -> None:
        """JobStatus.DEAD is available."""
        assert JobStatus.DEAD.value == "DEAD"

    def test_all_statuses_are_strings(self) -> None:
        """All JobStatus values are strings."""
        for status in JobStatus:
            assert isinstance(status.value, str)


class TestJobModel:
    """Verify Job Pydantic model validation."""

    def test_job_creation_with_required_fields(self) -> None:
        """Job creates with id, queue, payload, status."""
        now = datetime.now(UTC)
        job = Job(
            id="job-001",
            queue="default",
            payload={"task": "send_email", "to": "user@example.com"},
            status=JobStatus.PENDING,
            created_at=now,
        )
        assert job.id == "job-001"
        assert job.queue == "default"
        assert job.payload == {"task": "send_email", "to": "user@example.com"}
        assert job.status == JobStatus.PENDING
        assert job.attempts == 0
        assert job.max_retries == 3
        assert job.execute_at is None
        assert job.error is None

    def test_job_creation_with_all_fields(self) -> None:
        """Job accepts all optional fields."""
        now = datetime.now(UTC)
        future = datetime.now(UTC)
        job = Job(
            id="job-002",
            queue="email",
            payload={"task": "send"},
            status=JobStatus.RUNNING,
            attempts=2,
            max_retries=5,
            created_at=now,
            execute_at=future,
            error="Connection timeout",
        )
        assert job.attempts == 2
        assert job.max_retries == 5
        assert job.execute_at == future
        assert job.error == "Connection timeout"

    def test_job_id_is_required(self) -> None:
        """Job.id must not be empty."""
        with pytest.raises(PydanticValidationError):
            Job(
                id="",
                queue="default",
                payload={},
                status=JobStatus.PENDING,
            )

    def test_job_queue_min_length(self) -> None:
        """Job.queue must be at least 1 character."""
        with pytest.raises(PydanticValidationError):
            Job(
                id="job-003",
                queue="",
                payload={},
                status=JobStatus.PENDING,
            )

    def test_job_attempts_non_negative(self) -> None:
        """Job.attempts must be >= 0."""
        with pytest.raises(PydanticValidationError):
            Job(
                id="job-004",
                queue="default",
                payload={},
                status=JobStatus.PENDING,
                attempts=-1,
            )

    def test_job_max_retries_non_negative(self) -> None:
        """Job.max_retries must be >= 0."""
        with pytest.raises(PydanticValidationError):
            Job(
                id="job-005",
                queue="default",
                payload={},
                status=JobStatus.PENDING,
                max_retries=-1,
            )


class TestJobRefModel:
    """Verify JobRef Pydantic model validation."""

    def test_jobref_creation(self) -> None:
        """JobRef creates with id, queue, status."""
        ref = JobRef(id="job-001", queue="default", status=JobStatus.PENDING)
        assert ref.id == "job-001"
        assert ref.queue == "default"
        assert ref.status == JobStatus.PENDING

    def test_jobref_id_required(self) -> None:
        """JobRef.id must not be empty."""
        with pytest.raises(PydanticValidationError):
            JobRef(id="", queue="default", status=JobStatus.PENDING)


class TestQueueConfigModel:
    """Verify QueueConfig Pydantic model validation and defaults."""

    def test_default_config(self) -> None:
        """QueueConfig creates with sensible defaults."""
        config = QueueConfig()
        assert config.default_max_retries == 3
        assert config.backoff_base == 2.0
        assert config.backoff_factor == 1.0
        assert config.dlq_suffix == "_dlq"

    def test_custom_config(self) -> None:
        """QueueConfig accepts custom values."""
        config = QueueConfig(
            default_max_retries=5,
            backoff_base=3.0,
            backoff_factor=2.0,
            dlq_suffix="_dead",
        )
        assert config.default_max_retries == 5
        assert config.backoff_base == 3.0
        assert config.backoff_factor == 2.0
        assert config.dlq_suffix == "_dead"

    def test_negative_max_retries_fails(self) -> None:
        """default_max_retries must be >= 0."""
        with pytest.raises(PydanticValidationError):
            QueueConfig(default_max_retries=-1)

    def test_negative_backoff_base_fails(self) -> None:
        """backoff_base must be > 0."""
        with pytest.raises(PydanticValidationError):
            QueueConfig(backoff_base=0.0)

    def test_negative_backoff_factor_fails(self) -> None:
        """backoff_factor must be > 0."""
        with pytest.raises(PydanticValidationError):
            QueueConfig(backoff_factor=0.0)

    def test_empty_dlq_suffix_fails(self) -> None:
        """dlq_suffix must not be empty."""
        with pytest.raises(PydanticValidationError):
            QueueConfig(dlq_suffix="")
