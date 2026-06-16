"""TaskQueueManager Protocol — the contract every task queue adapter must satisfy.

Defines the async task queue interface consumed by infrastructure managers
that need asynchronous job processing with retry, scheduling, and DLQ support.

Security: Payloads MUST be JSON-serializable. Never queue credentials or tokens
    in plain text — encrypt sensitive payloads before enqueuing.
Observability: Enqueue/dequeue/ack/nack events emit counters under cenf.taskqueue.*.
@ai-directive: Ack/nack MUST be idempotent — calling ack on an already-acked job
    is a no-op. DLQ jobs require manual inspection and reprocessing.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from core_infrastructure.taskqueue.models import Job, JobRef


@runtime_checkable
class TaskQueueManager(Protocol):
    """Async task queue contract with retry, scheduling, and DLQ support.

    All infrastructure managers that need asynchronous job processing consume
    this interface. Concrete adapters provide in-memory list (dev/testing)
    or SAQ/Redis backend (production).

    Rules:
        - enqueue() returns a JobRef handle immediately — processing is async.
        - dequeue() returns the oldest PENDING job or None if queue is empty.
        - ack() marks a job COMPLETED. Idempotent — safe to call multiple times.
        - nack() with requeue=True resets to PENDING and increments attempts.
          When attempts >= max_retries, the job transitions to DEAD and moves to DLQ.
        - nack() with requeue=False marks the job FAILED immediately.
        - schedule() sets execute_at for deferred execution. dequeue() skips
          jobs whose execute_at is in the future.
        - get_job() returns None for unknown IDs — never raises.
        - get_dlq_jobs() returns DEAD jobs for the specified queue.
    """

    async def enqueue(
        self,
        queue_name: str,
        payload: dict[str, Any],
        max_retries: int | None = None,
    ) -> JobRef:
        """Place a job onto a queue for immediate processing.

        Args:
            queue_name: Target queue name. Created implicitly if not exists.
            payload: JSON-serializable dict with job data.
            max_retries: Optional override for max retry attempts.

        Returns:
            JobRef: A handle to the enqueued job with id, queue, and status.

        Raises:
            ValidationError: If payload is not JSON-serializable.
        """
        ...

    async def dequeue(self, queue_name: str) -> Job | None:
        """Retrieve and lock the next available job from a queue.

        Returns the oldest PENDING job whose execute_at is in the past
        (or None). The job transitions to RUNNING status.

        Args:
            queue_name: Queue to dequeue from.

        Returns:
            Job | None: The next job, or None if queue is empty.
        """
        ...

    async def ack(self, job_id: str) -> None:
        """Acknowledge successful job completion.

        Transitions the job to COMPLETED status. Idempotent.

        Args:
            job_id: The job identifier from JobRef.id.
        """
        ...

    async def nack(self, job_id: str, requeue: bool = True) -> None:
        """Signal job failure — optionally requeue for retry.

        If requeue=True: increments attempts, resets to PENDING.
            If attempts >= max_retries, transitions to DEAD and moves to DLQ.
        If requeue=False: transitions to FAILED immediately.

        Args:
            job_id: The job identifier.
            requeue: Whether to requeue the job for retry.

        Raises:
            Does NOT raise for unknown job IDs — no-op.
        """
        ...

    async def schedule(
        self,
        queue_name: str,
        payload: dict[str, Any],
        execute_at: datetime,
        max_retries: int | None = None,
    ) -> JobRef:
        """Schedule a job for deferred execution.

        Args:
            queue_name: Target queue name.
            payload: JSON-serializable dict with job data.
            execute_at: UTC datetime when the job becomes eligible for dequeue.
            max_retries: Optional override for max retry attempts.

        Returns:
            JobRef: A handle to the scheduled job.

        Raises:
            ValidationError: If payload is not JSON-serializable.
        """
        ...

    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by its identifier.

        Args:
            job_id: The job identifier.

        Returns:
            Job | None: The full Job object, or None if not found.
        """
        ...

    async def get_dlq_jobs(self, queue_name: str) -> list[Job]:
        """Retrieve all DEAD jobs in the DLQ for a given queue.

        Args:
            queue_name: The original queue name (DLQ suffix is added internally).

        Returns:
            list[Job]: DEAD jobs currently in the DLQ.
        """
        ...
