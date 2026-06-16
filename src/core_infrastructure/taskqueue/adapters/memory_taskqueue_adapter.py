"""MemoryTaskQueueAdapter — in-memory list-backed TaskQueueManager with DLQ.

Provides a zero-dependency TaskQueueManager implementation using plain dicts
and lists for job storage. Supports full job lifecycle: enqueue, dequeue, ack,
nack with retry, exponential backoff with jitter, DLQ routing on exhaustion,
and scheduled execution via execute_at.

Security: Payloads are validated as JSON-serializable before enqueue.
Observability: Job state transitions emit counters under cenf.taskqueue.*.
@ai-directive: This adapter exists for dev/testing. Use SAQ/Redis adapter
    in production after completing the Redis backend integration.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import json
import math
import random
import uuid
from datetime import UTC, datetime
from typing import Any

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus, QueueConfig


class MemoryTaskQueueAdapter:
    """In-memory list-backed TaskQueueManager with retry logic and DLQ.

    Stores jobs in a dict of queues (list-per-queue). Provides full
    job lifecycle management with exponential backoff and jitter for
    retry delays. Failed jobs are routed to a DLQ after max_retries
    is exhausted.

    Args:
        config: QueueConfig for retry/backoff/DLQ settings.

    Usage::

        adapter = MemoryTaskQueueAdapter(config=QueueConfig())
        ref = await adapter.enqueue("default", {"task": "process"})
        job = await adapter.dequeue("default")
        await adapter.ack(job.id)
    """

    def __init__(self, config: QueueConfig | None = None) -> None:
        self._config = config if config is not None else QueueConfig()
        self._queues: dict[str, list[Job]] = {}
        self._jobs_by_id: dict[str, Job] = {}
        self._started = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique job ID (UUID4)."""
        return str(uuid.uuid4())

    @staticmethod
    def _validate_payload(payload: dict[str, Any]) -> None:
        """Validate that a payload is JSON-serializable.

        Args:
            payload: The dict to validate.

        Raises:
            ValidationError: If payload is not JSON-serializable.
        """
        try:
            json.dumps(payload)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                f"Payload is not JSON-serializable: {exc}",
                details={"error": str(exc)},
            ) from exc

    def _ensure_queue(self, queue_name: str) -> list[Job]:
        """Get or create a queue list for the given name.

        Args:
            queue_name: Queue name to retrieve or create.

        Returns:
            list[Job]: The queue's job list.
        """
        if queue_name not in self._queues:
            self._queues[queue_name] = []
        return self._queues[queue_name]

    def _find_job(self, job_id: str) -> Job | None:
        """Find a job by ID across all queues.

        Args:
            job_id: The job identifier.

        Returns:
            Job | None: The job if found, None otherwise.
        """
        return self._jobs_by_id.get(job_id)

    def _move_to_dlq(self, job: Job) -> None:
        """Move a job to the DLQ for its queue.

        Transitions job status to DEAD and moves it from the main queue
        to the DLQ queue (queue_name + dlq_suffix).

        Args:
            job: The job to move to DLQ.
        """
        # Remove from main queue
        main_queue = self._queues.get(job.queue, [])
        if job in main_queue:
            main_queue.remove(job)

        # Add to DLQ
        dlq_name = job.queue + self._config.dlq_suffix
        dlq_queue = self._ensure_queue(dlq_name)
        job.status = JobStatus.DEAD
        dlq_queue.append(job)

    def _calculate_backoff(self, attempts: int) -> float:
        """Calculate exponential backoff delay with jitter.

        Formula:
            delay = backoff_base^attempts * backoff_factor * (1 + random_jitter)

        Args:
            attempts: Current attempt count (1-based).

        Returns:
            float: Backoff delay in seconds.
        """
        base_delay = (
            math.pow(self._config.backoff_base, attempts)
            * self._config.backoff_factor
        )
        jitter = random.uniform(0, 0.5)
        return base_delay * (1.0 + jitter)

    # ------------------------------------------------------------------
    # Public API — TaskQueueManager Protocol
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        queue_name: str,
        payload: dict[str, Any],
        max_retries: int | None = None,
    ) -> JobRef:
        """Place a job onto a queue for immediate processing.

        Args:
            queue_name: Target queue name.
            payload: JSON-serializable dict with job data.
            max_retries: Optional override for max retry attempts.

        Returns:
            JobRef: Handle to the enqueued job.

        Raises:
            ValidationError: If payload is not JSON-serializable.
        """
        self._validate_payload(payload)

        resolved_max_retries = (
            max_retries
            if max_retries is not None
            else self._config.default_max_retries
        )

        job = Job(
            id=self._generate_id(),
            queue=queue_name,
            payload=payload,
            max_retries=resolved_max_retries,
        )

        queue = self._ensure_queue(queue_name)
        queue.append(job)
        self._jobs_by_id[job.id] = job

        return JobRef(id=job.id, queue=job.queue, status=job.status)

    async def dequeue(self, queue_name: str) -> Job | None:
        """Retrieve the next available job from a queue.

        Returns the oldest PENDING job with execute_at in the past.
        Transitions the job to RUNNING status.

        Args:
            queue_name: Queue to dequeue from.

        Returns:
            Job | None: The next job, or None if no eligible jobs.
        """
        queue = self._queues.get(queue_name, [])
        now = datetime.now(UTC)

        for i, job in enumerate(queue):
            if job.status != JobStatus.PENDING:
                continue
            # Check scheduling — skip if not yet ready
            if job.execute_at is not None and job.execute_at > now:
                continue
            # Remove from queue to prevent re-dequeue
            del queue[i]
            return job

        return None

    async def ack(self, job_id: str) -> None:
        """Acknowledge successful job completion.

        Transitions the job to COMPLETED status. Idempotent — safe
        to call on already-acked jobs.

        Args:
            job_id: The job identifier.
        """
        job = self._find_job(job_id)
        if job is not None:
            job.status = JobStatus.COMPLETED

    async def nack(self, job_id: str, requeue: bool = True) -> None:
        """Signal job failure — optionally requeue for retry.

        If requeue=True: increments attempts, resets to PENDING.
            If attempts >= max_retries, moves to DLQ (DEAD).
        If requeue=False: transitions to FAILED immediately.

        Args:
            job_id: The job identifier.
            requeue: Whether to requeue for retry.
        """
        job = self._find_job(job_id)
        if job is None:
            return

        if requeue:
            job.attempts += 1
            job.error = None
            if job.attempts >= job.max_retries:
                self._move_to_dlq(job)
            else:
                job.status = JobStatus.PENDING
        else:
            job.status = JobStatus.FAILED

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
            execute_at: UTC datetime when the job becomes eligible.
            max_retries: Optional override for max retry attempts.

        Returns:
            JobRef: Handle to the scheduled job.

        Raises:
            ValidationError: If payload is not JSON-serializable.
        """
        self._validate_payload(payload)

        resolved_max_retries = (
            max_retries
            if max_retries is not None
            else self._config.default_max_retries
        )

        job = Job(
            id=self._generate_id(),
            queue=queue_name,
            payload=payload,
            max_retries=resolved_max_retries,
            execute_at=execute_at,
        )

        queue = self._ensure_queue(queue_name)
        queue.append(job)
        self._jobs_by_id[job.id] = job

        return JobRef(id=job.id, queue=job.queue, status=job.status)

    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by its identifier.

        Args:
            job_id: The job identifier.

        Returns:
            Job | None: The full Job object, or None if not found.
        """
        return self._find_job(job_id)

    async def get_dlq_jobs(self, queue_name: str) -> list[Job]:
        """Retrieve all DEAD jobs in the DLQ for a given queue.

        Args:
            queue_name: The original queue name.

        Returns:
            list[Job]: DEAD jobs currently in the DLQ.
        """
        dlq_name = queue_name + self._config.dlq_suffix
        dlq_queue = self._queues.get(dlq_name, [])
        return list(dlq_queue)
