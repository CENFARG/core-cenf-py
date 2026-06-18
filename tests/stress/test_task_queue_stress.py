"""Stress tests for MemoryTaskQueueAdapter — concurrent enqueue/dequeue/ack/nack.

Tests cover:
- 500 jobs enqueued rapidly (no lost jobs)
- Concurrent dequeue and ack under load
- DLQ behavior when jobs exhaust max_retries
- No job corruption under concurrent access

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio

import pytest

from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import MemoryTaskQueueAdapter
from core_infrastructure.taskqueue.models import JobStatus, QueueConfig

pytestmark = pytest.mark.stress

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adapter() -> MemoryTaskQueueAdapter:
    """Create a MemoryTaskQueueAdapter with default QueueConfig."""
    return MemoryTaskQueueAdapter(QueueConfig(default_max_retries=3))


# ---------------------------------------------------------------------------
# Stress: rapid enqueue
# ---------------------------------------------------------------------------


class TestRapidEnqueue:
    """Verify 500 jobs enqueued rapidly with no data loss."""

    @pytest.mark.asyncio
    async def test_500_jobs_enqueued_no_lost_jobs(self, adapter: MemoryTaskQueueAdapter) -> None:
        """Enqueue 500 jobs concurrently — all 500 exist in the queue."""
        async def enqueue_one(index: int) -> str:
            ref = await adapter.enqueue("batch-q", {"task": f"job-{index}"})
            return ref.id

        job_ids = await asyncio.gather(*[enqueue_one(i) for i in range(500)])

        assert len(job_ids) == 500
        # Verify every job is retrievable
        for jid in job_ids:
            job = await adapter.get_job(jid)
            assert job is not None, f"Job {jid} not found"
            assert job.status == JobStatus.PENDING
            assert job.queue == "batch-q"

    @pytest.mark.asyncio
    async def test_enqueue_large_payloads_under_load(self, adapter: MemoryTaskQueueAdapter) -> None:
        """Enqueue jobs with large payloads concurrently."""
        large_payload = {"data": "x" * 1000, "index": 0}

        async def enqueue_large(index: int) -> str:
            payload: dict[str, str] = {**large_payload, "index": str(index)}
            ref = await adapter.enqueue("large-q", payload)
            return ref.id

        job_ids = await asyncio.gather(*[enqueue_large(i) for i in range(100)])
        assert len(job_ids) == 100


# ---------------------------------------------------------------------------
# Stress: concurrent dequeue and ack
# ---------------------------------------------------------------------------


class TestConcurrentDequeueAck:
    """Verify dequeuing and acking under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_dequeue_and_ack_preserves_jobs(self, adapter: MemoryTaskQueueAdapter) -> None:
        """Concurrent dequeuers process all enqueued jobs exactly once."""
        queue_name = "dequeue-stress"
        total_jobs = 200

        # Pre-populate
        for i in range(total_jobs):
            await adapter.enqueue(queue_name, {"task": i})

        completed_count = 0

        async def worker() -> None:
            nonlocal completed_count
            while True:
                job = await adapter.dequeue(queue_name)
                if job is None:
                    return
                # Process and ack
                await adapter.ack(job.id)
                completed_count += 1
                # Yield to allow other workers
                await asyncio.sleep(0)

        workers = [worker() for _ in range(10)]
        await asyncio.gather(*workers)

        assert completed_count == total_jobs, f"Processed {completed_count}, expected {total_jobs}"


# ---------------------------------------------------------------------------
# Stress: DLQ exhaustion
# ---------------------------------------------------------------------------


class TestDLQExhaustion:
    """Verify DLQ behavior when jobs repeatedly fail."""

    @pytest.mark.asyncio
    async def test_jobs_move_to_dlq_after_max_retries_exhaustion(self, adapter: MemoryTaskQueueAdapter) -> None:
        """Nack a job 3 times (max_retries=3) — it moves to DLQ (DEAD)."""
        queue_name = "dlq-stress"
        job_count = 50

        for i in range(job_count):
            await adapter.enqueue(queue_name, {"task": i}, max_retries=3)

        dead_count = 0
        for _ in range(job_count):
            job = await adapter.dequeue(queue_name)
            assert job is not None
            # Nack with requeue 3 times — after 3rd, moves to DLQ
            for _ in range(3):
                await adapter.nack(job.id, requeue=True)
            # After max_retries exhausted, check it is DEAD
            refreshed = await adapter.get_job(job.id)
            if refreshed is not None and refreshed.status == JobStatus.DEAD:
                dead_count += 1

        assert dead_count == job_count, f"Expected {job_count} DEAD jobs, got {dead_count}"

    @pytest.mark.asyncio
    async def test_dlq_contains_all_dead_jobs(self, adapter: MemoryTaskQueueAdapter) -> None:
        """get_dlq_jobs() returns all DEAD jobs after exhaustion."""
        queue_name = "dlq-list-stress"
        total = 20

        for i in range(total):
            await adapter.enqueue(queue_name, {"task": i}, max_retries=1)

        for _ in range(total):
            job = await adapter.dequeue(queue_name)
            assert job is not None
            await adapter.nack(job.id, requeue=True)  # First nack → should be dead (max_retries=1)

        dlq_jobs = await adapter.get_dlq_jobs(queue_name)
        assert len(dlq_jobs) == total, f"DLQ has {len(dlq_jobs)} jobs, expected {total}"
        for j in dlq_jobs:
            assert j.status == JobStatus.DEAD
