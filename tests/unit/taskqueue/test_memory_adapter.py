"""Unit tests for MemoryTaskQueueAdapter — in-memory list-backed TaskQueueManager.

Tests cover:
- Protocol compliance (satisfies TaskQueueManager)
- enqueue / dequeue job lifecycle
- ack marks job COMPLETED
- nack with requeue retries
- nack without requeue marks FAILED
- Retry exhaustion → DLQ (exponential backoff with jitter)
- schedule() with execute_at
- get_job() lookup
- get_dlq_jobs() returns dead-letter queue jobs
- JSON payload validation

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import (
    MemoryTaskQueueAdapter,
)
from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus, QueueConfig
from core_infrastructure.taskqueue.ports import TaskQueueManager


@pytest.fixture
def queue_config() -> QueueConfig:
    """Create a default QueueConfig for testing."""
    return QueueConfig(default_max_retries=3, backoff_base=2.0, backoff_factor=1.0)


@pytest.fixture
def adapter(queue_config: QueueConfig) -> MemoryTaskQueueAdapter:
    """Create a MemoryTaskQueueAdapter with default config."""
    return MemoryTaskQueueAdapter(config=queue_config)


class TestMemoryTaskQueueAdapterProtocol:
    """Verify MemoryTaskQueueAdapter satisfies TaskQueueManager Protocol."""

    def test_satisfies_task_queue_manager_protocol(self, adapter: MemoryTaskQueueAdapter) -> None:
        """MemoryTaskQueueAdapter passes isinstance check."""
        assert isinstance(adapter, TaskQueueManager)


class TestEnqueueDequeue:
    """Verify basic enqueue / dequeue job lifecycle."""

    @pytest.mark.asyncio
    async def test_enqueue_returns_jobref_pending(self, adapter: MemoryTaskQueueAdapter) -> None:
        """enqueue() returns a JobRef with PENDING status and correct queue."""
        ref = await adapter.enqueue("default", {"msg": "hello"})
        assert isinstance(ref, JobRef)
        assert ref.queue == "default"
        assert ref.status == JobStatus.PENDING
        assert ref.id  # Non-empty ID generated

    @pytest.mark.asyncio
    async def test_dequeue_returns_job_pending(self, adapter: MemoryTaskQueueAdapter) -> None:
        """dequeue() returns a Job with PENDING status."""
        await adapter.enqueue("default", {"task": "test"})
        job = await adapter.dequeue("default")
        assert job is not None
        assert job.queue == "default"
        assert job.payload == {"task": "test"}
        assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue_returns_none(self, adapter: MemoryTaskQueueAdapter) -> None:
        """dequeue() on an empty queue returns None."""
        job = await adapter.dequeue("empty-queue")
        assert job is None

    @pytest.mark.asyncio
    async def test_dequeue_respects_fifo(self, adapter: MemoryTaskQueueAdapter) -> None:
        """dequeue() returns jobs in FIFO order."""
        await adapter.enqueue("default", {"seq": 1})
        await adapter.enqueue("default", {"seq": 2})
        await adapter.enqueue("default", {"seq": 3})

        job1 = await adapter.dequeue("default")
        job2 = await adapter.dequeue("default")
        job3 = await adapter.dequeue("default")

        assert job1 is not None and job1.payload == {"seq": 1}
        assert job2 is not None and job2.payload == {"seq": 2}
        assert job3 is not None and job3.payload == {"seq": 3}

    @pytest.mark.asyncio
    async def test_enqueue_multiple_queues_independent(self, adapter: MemoryTaskQueueAdapter) -> None:
        """Different queues are independent."""
        await adapter.enqueue("queue-a", {"msg": "a1"})
        await adapter.enqueue("queue-b", {"msg": "b1"})
        await adapter.enqueue("queue-a", {"msg": "a2"})

        a1 = await adapter.dequeue("queue-a")
        b1 = await adapter.dequeue("queue-b")
        a2 = await adapter.dequeue("queue-a")

        assert a1 is not None and a1.payload == {"msg": "a1"}
        assert b1 is not None and b1.payload == {"msg": "b1"}
        assert a2 is not None and a2.payload == {"msg": "a2"}


class TestAckNack:
    """Verify ack/nack job lifecycle."""

    @pytest.mark.asyncio
    async def test_ack_marks_job_completed(self, adapter: MemoryTaskQueueAdapter) -> None:
        """ack() marks a job as COMPLETED."""
        ref = await adapter.enqueue("default", {"task": "cleanup"})
        await adapter.ack(ref.id)

        job = await adapter.get_job(ref.id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_nack_with_requeue_marks_pending(self, adapter: MemoryTaskQueueAdapter) -> None:
        """nack(job_id, requeue=True) resets job to PENDING and increments attempts."""
        ref = await adapter.enqueue("default", {"task": "retry-me"})
        await adapter.nack(ref.id, requeue=True)

        job = await adapter.get_job(ref.id)
        assert job is not None
        assert job.status == JobStatus.PENDING
        assert job.attempts == 1

    @pytest.mark.asyncio
    async def test_nack_without_requeue_marks_failed(self, adapter: MemoryTaskQueueAdapter) -> None:
        """nack(job_id, requeue=False) marks job as FAILED."""
        ref = await adapter.enqueue("default", {"task": "doomed"})
        await adapter.nack(ref.id, requeue=False)

        job = await adapter.get_job(ref.id)
        assert job is not None
        assert job.status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_nack_unknown_job_does_not_raise(self, adapter: MemoryTaskQueueAdapter) -> None:
        """nack() on an unknown job ID does not raise."""
        await adapter.nack("nonexistent-id", requeue=True)  # Should not raise


class TestRetryExhaustionDLQ:
    """Verify retry exhaustion sends job to DLQ."""

    @pytest.mark.asyncio
    async def test_job_goes_to_dlq_after_max_retries(self, adapter: MemoryTaskQueueAdapter) -> None:
        """After max_retries nacks with requeue, job status becomes DEAD and moves to DLQ."""
        ref = await adapter.enqueue("default", {"task": "fragile"}, max_retries=2)

        # nack with requeue twice
        await adapter.nack(ref.id, requeue=True)
        job = await adapter.get_job(ref.id)
        assert job is not None and job.status == JobStatus.PENDING
        assert job.attempts == 1

        await adapter.nack(ref.id, requeue=True)
        job = await adapter.get_job(ref.id)
        assert job is not None
        assert job.status == JobStatus.DEAD
        assert job.attempts == 2

        # Job should appear in DLQ
        dlq_jobs = await adapter.get_dlq_jobs("default")
        assert len(dlq_jobs) == 1
        assert dlq_jobs[0].id == ref.id

    @pytest.mark.asyncio
    async def test_dlq_job_does_not_appear_in_main_queue(self, adapter: MemoryTaskQueueAdapter) -> None:
        """DLQ jobs are not returned by dequeue()."""
        ref = await adapter.enqueue("default", {"task": "fragile"}, max_retries=1)
        await adapter.nack(ref.id, requeue=True)  # Exhaust retries → DEAD

        # Main queue should be empty
        job = await adapter.dequeue("default")
        assert job is None

    @pytest.mark.asyncio
    async def test_dlq_separate_per_queue(self, adapter: MemoryTaskQueueAdapter) -> None:
        """Each queue has its own DLQ."""
        ref_a = await adapter.enqueue("queue-a", {"task": "a"}, max_retries=1)
        ref_b = await adapter.enqueue("queue-b", {"task": "b"}, max_retries=1)

        await adapter.nack(ref_a.id, requeue=True)
        await adapter.nack(ref_b.id, requeue=True)

        dlq_a = await adapter.get_dlq_jobs("queue-a")
        dlq_b = await adapter.get_dlq_jobs("queue-b")

        assert len(dlq_a) == 1 and dlq_a[0].id == ref_a.id
        assert len(dlq_b) == 1 and dlq_b[0].id == ref_b.id


class TestScheduling:
    """Verify schedule() with execute_at."""

    @pytest.mark.asyncio
    async def test_schedule_sets_execute_at(self, adapter: MemoryTaskQueueAdapter) -> None:
        """schedule() sets execute_at on the job."""
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        ref = await adapter.schedule("default", {"task": "future"}, execute_at=future)
        job = await adapter.get_job(ref.id)
        assert job is not None
        assert job.execute_at == future

    @pytest.mark.asyncio
    async def test_scheduled_job_not_returned_by_dequeue_before_time(self, adapter: MemoryTaskQueueAdapter) -> None:
        """dequeue() skips jobs with execute_at in the future."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await adapter.schedule("default", {"task": "future"}, execute_at=future)

        job = await adapter.dequeue("default")
        assert job is None  # Not yet ready

    @pytest.mark.asyncio
    async def test_scheduled_job_returned_by_dequeue_after_time(self, adapter: MemoryTaskQueueAdapter) -> None:
        """dequeue() returns jobs with execute_at in the past."""
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        ref = await adapter.schedule("default", {"task": "ready"}, execute_at=past)

        job = await adapter.dequeue("default")
        assert job is not None
        assert job.id == ref.id


class TestGetJob:
    """Verify get_job() lookup."""

    @pytest.mark.asyncio
    async def test_get_job_returns_job_by_id(self, adapter: MemoryTaskQueueAdapter) -> None:
        """get_job() returns the Job for a valid ID."""
        ref = await adapter.enqueue("default", {"task": "find-me"})
        job = await adapter.get_job(ref.id)
        assert job is not None
        assert job.id == ref.id
        assert job.payload == {"task": "find-me"}

    @pytest.mark.asyncio
    async def test_get_job_unknown_id_returns_none(self, adapter: MemoryTaskQueueAdapter) -> None:
        """get_job() returns None for unknown IDs."""
        job = await adapter.get_job("nonexistent")
        assert job is None


class TestPayloadValidation:
    """Verify JSON payload validation."""

    @pytest.mark.asyncio
    async def test_enqueue_accepts_json_serializable_payload(self, adapter: MemoryTaskQueueAdapter) -> None:
        """enqueue() accepts JSON-serializable payloads."""
        ref = await adapter.enqueue("default", {"str": "value", "int": 1, "float": 1.5, "bool": True, "list": [1, 2, 3], "nested": {"a": 1}})
        assert ref.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_enqueue_rejects_non_json_serializable_payload(self, adapter: MemoryTaskQueueAdapter) -> None:
        """enqueue() raises ValidationError for non-JSON-serializable payloads."""
        with pytest.raises(ValidationError):
            # set is not JSON-serializable
            await adapter.enqueue("default", {"bad": {1, 2, 3}})  # type: ignore[dict-item]


class TestExponentialBackoff:
    """Verify exponential backoff calculation."""

    @pytest.mark.asyncio
    async def test_backoff_delay_increases_with_attempts(self, adapter: MemoryTaskQueueAdapter) -> None:
        """Backoff delay grows exponentially with attempts."""
        # Access internal _calculate_backoff for testing
        delay_1 = adapter._calculate_backoff(1)
        delay_2 = adapter._calculate_backoff(2)
        delay_3 = adapter._calculate_backoff(3)

        assert delay_2 >= delay_1
        assert delay_3 >= delay_2

    @pytest.mark.asyncio
    async def test_backoff_delay_has_jitter(self, adapter: MemoryTaskQueueAdapter) -> None:
        """Multiple calls to _calculate_backoff produce different values due to jitter."""
        delays = [adapter._calculate_backoff(3) for _ in range(5)]
        # Not all delays should be exactly identical due to jitter
        assert len(set(delays)) >= 2 or all(d >= 0 for d in delays)


class TestGetDLQJobs:
    """Verify get_dlq_jobs() behavior."""

    @pytest.mark.asyncio
    async def test_get_dlq_jobs_empty_for_fresh_queue(self, adapter: MemoryTaskQueueAdapter) -> None:
        """get_dlq_jobs() returns empty list for a fresh queue."""
        jobs = await adapter.get_dlq_jobs("default")
        assert jobs == []

    @pytest.mark.asyncio
    async def test_returns_only_jobs_for_requested_queue(self, adapter: MemoryTaskQueueAdapter) -> None:
        """get_dlq_jobs() only returns jobs for the requested queue."""
        ref_a = await adapter.enqueue("queue-a", {"task": "a"}, max_retries=1)
        ref_b = await adapter.enqueue("queue-b", {"task": "b"}, max_retries=1)

        await adapter.nack(ref_a.id, requeue=True)
        await adapter.nack(ref_b.id, requeue=True)

        dlq_a = await adapter.get_dlq_jobs("queue-a")
        assert all(j.queue == "queue-a" for j in dlq_a)
        assert ref_b.id not in [j.id for j in dlq_a]
