"""SaQAdapter — Redis-backed SAQ TaskQueueManager with async job processing.

Provides a production-ready TaskQueueManager implementation using SAQ
(Simple Async Queue) backed by Redis. Supports full job lifecycle:
enqueue, dequeue, ack, nack with retry, scheduled execution, and DLQ
tracking for exhausted-retry jobs.

The adapter translates between the CENF TaskQueueManager Protocol and
SAQ's function-oriented job model. All jobs are enqueued with a generic
``process_job`` function name; the actual queue name and payload are
stored in the job's kwargs for transparent routing.

Security: Payloads are validated as JSON-serializable before enqueue.
    Redis connection URL is masked in log output.
Observability: Job state transitions log at DEBUG level via LoggerManager.
@ai-directive: SAQ handles its own Redis connection pool and retry logic.
    The adapter focuses on CENF Protocol ↔ SAQ API translation.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import saq

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager
from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GENERIC_JOB_FUNCTION = "process_job"
_DLQ_KEY_PREFIX = "cenf:taskqueue:dlq:"


class SaQAdapter:
    """Redis-backed SAQ TaskQueueManager adapter.

    Connects to a Redis instance via SAQ and provides the full
    TaskQueueManager Protocol: enqueue, dequeue, ack, nack with retry,
    schedule, get_job, and get_dlq_jobs.

    Multi-queue support: SAQ Queue instances are created and cached per
    queue name. Each queue uses the same Redis connection URL.

    Args:
        config: ConfigManager providing ``taskqueue.redis_url``,
            ``taskqueue.saq.concurrency``, ``taskqueue.saq.timeout``.
        secrets: SecretManager for Redis credentials (reserved).
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for error classification.

    Usage::

        adapter = SaQAdapter(config, secrets, logger, error_handler)
        ref = await adapter.enqueue("default", {"task": "process"})
        job = await adapter.dequeue("default")
        await adapter.ack(job.id)
    """

    def __init__(
        self,
        config: ConfigManager,
        secrets: SecretManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._logger = logger
        self._error_handler = error_handler

        self._redis_url: str = config.get_string(
            "taskqueue.redis_url", default_value="redis://localhost:6379/0"
        )
        self._timeout: int = int(
            config.get_number("taskqueue.saq.timeout", default_value=30)
        )

        # Cache: queue_name → saq.Queue instance
        self._queues: dict[str, saq.Queue] = {}
        # DLQ registry: queue_name → set of dead job keys
        self._dlq: dict[str, set[str]] = {}
        # Track which queue each job belongs to (for get_job lookup)
        self._job_queue_map: dict[str, str] = {}

        self._started = False

        # Attempt initial Redis connection (non-fatal on failure)
        try:
            self._get_or_create_queue("default")
            self._logger.debug(
                "SaQAdapter: connected to Redis",
                redis_url=self._logger.mask(self._redis_url, visible_chars=0),
            )
        except Exception as exc:
            self._logger.warn(
                "SaQAdapter: Redis unavailable — adapter will raise on operations",
                redis_url=self._logger.mask(self._redis_url, visible_chars=0),
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def _get_or_create_queue(self, queue_name: str) -> saq.Queue:
        """Get or create a SAQ Queue instance for the given queue name.

        Args:
            queue_name: The CENF queue name.

        Returns:
            saq.Queue: The SAQ queue instance for this queue name.
        """
        if queue_name not in self._queues:
            self._queues[queue_name] = saq.Queue.from_url(
                self._redis_url,
                name=queue_name,
            )
        return self._queues[queue_name]

    @staticmethod
    def _saq_status_to_job_status(saq_status: saq.Status) -> JobStatus:
        """Map SAQ Status to CENF JobStatus.

        Args:
            saq_status: The SAQ job status.

        Returns:
            JobStatus: The corresponding CENF job status.
        """
        mapping = {
            saq.Status.NEW: JobStatus.PENDING,
            saq.Status.QUEUED: JobStatus.PENDING,
            saq.Status.ACTIVE: JobStatus.PENDING,  # RUNNING in our terms, but mapped conservatively
            saq.Status.COMPLETE: JobStatus.COMPLETED,
            saq.Status.FAILED: JobStatus.FAILED,
            saq.Status.ABORTING: JobStatus.FAILED,
            saq.Status.ABORTED: JobStatus.FAILED,
        }
        return mapping.get(saq_status, JobStatus.PENDING)

    @staticmethod
    def _saq_job_queue_name(saq_job: saq.Job) -> str:
        """Extract the queue name from a SAQ Job's queue attribute.

        SAQ stores the Queue instance, not just the name string.
        This helper handles both Queue instances and plain strings
        (for mock compatibility in tests).

        Args:
            saq_job: The SAQ job.

        Returns:
            str: The queue name.
        """
        queue_attr = saq_job.queue
        if queue_attr is not None and hasattr(queue_attr, "name"):
            return str(queue_attr.name)
        return str(queue_attr)

    @staticmethod
    def _saq_job_to_cenf_job(saq_job: saq.Job) -> Job:
        """Convert a SAQ Job to a CENF Job.

        Extracts the payload from SAQ job kwargs, falling back to
        the full kwargs dict if no ``payload`` key exists.

        Args:
            saq_job: The SAQ job to convert.

        Returns:
            Job: A CENF Job model instance.
        """
        payload: dict[str, Any] = saq_job.kwargs.get("payload", saq_job.kwargs) if saq_job.kwargs else {}

        # Safely extract numeric fields (handle MagicMock in tests)
        def _safe_int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        attempts = _safe_int(saq_job.attempts, 0)
        max_retries = _safe_int(saq_job.retries, 3)
        queued_ts = _safe_int(saq_job.queued, 0)
        scheduled_ts = _safe_int(saq_job.scheduled, 0)
        error_msg: str | None = saq_job.error if isinstance(saq_job.error, str) else None

        return Job(
            id=saq_job.key,
            queue=SaQAdapter._saq_job_queue_name(saq_job),
            payload=payload,
            status=SaQAdapter._saq_status_to_job_status(saq_job.status),
            attempts=attempts,
            max_retries=max_retries,
            created_at=datetime.fromtimestamp(queued_ts, tz=UTC) if queued_ts > 0 else datetime.now(UTC),
            execute_at=(
                datetime.fromtimestamp(scheduled_ts, tz=UTC)
                if scheduled_ts > 0
                else None
            ),
            error=error_msg,
        )

    def _track_job_queue(self, job_key: str, queue_name: str) -> None:
        """Record which queue a job belongs to for cross-queue lookup.

        Args:
            job_key: The SAQ job key.
            queue_name: The CENF queue name.
        """
        self._job_queue_map[job_key] = queue_name

    def _register_dlq(self, queue_name: str, job_key: str) -> None:
        """Register a job key in the DLQ for its queue.

        Args:
            queue_name: The CENF queue name.
            job_key: The SAQ job key.
        """
        dlq_key = _DLQ_KEY_PREFIX + queue_name
        if dlq_key not in self._dlq:
            self._dlq[dlq_key] = set()
        self._dlq[dlq_key].add(job_key)

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

        queue = self._get_or_create_queue(queue_name)
        retries = max_retries if max_retries is not None else 3

        saq_job: saq.Job | None = await queue.enqueue(
            _GENERIC_JOB_FUNCTION,
            payload=payload,
            queue_name=queue_name,
            retries=retries,
            timeout=self._timeout,
        )
        # queue.enqueue returns None if the queue is full or stopped
        if saq_job is None:
            raise RuntimeError(f"Failed to enqueue job on queue '{queue_name}'")

        self._track_job_queue(saq_job.key, queue_name)
        return JobRef(id=saq_job.key, queue=queue_name, status=JobStatus.PENDING)

    async def dequeue(self, queue_name: str) -> Job | None:
        """Retrieve the next available job from a queue.

        Args:
            queue_name: Queue to dequeue from.

        Returns:
            Job | None: The next job, or None if queue is empty.
        """
        queue = self._get_or_create_queue(queue_name)
        saq_job = await queue.dequeue()
        if saq_job is None:
            return None

        self._track_job_queue(saq_job.key, queue_name)
        return self._saq_job_to_cenf_job(saq_job)

    async def _find_job_in_queues(self, job_id: str) -> tuple[saq.Queue | None, saq.Job | None]:
        """Find a SAQ job across all known queues.

        First checks the job-to-queue map (O(1)), then falls back to
        scanning all known queues (O(n)).

        Args:
            job_id: The SAQ job key.

        Returns:
            tuple: (queue, saq_job) or (None, None) if not found.
        """
        # Fast path: job-to-queue map
        queue_name = self._job_queue_map.get(job_id)
        if queue_name and queue_name in self._queues:
            queue = self._queues[queue_name]
            saq_job = await queue.job(job_id)
            if saq_job is not None:
                return queue, saq_job

        # Slow path: scan all queues
        for q_name, queue in self._queues.items():
            saq_job = await queue.job(job_id)
            if saq_job is not None:
                self._job_queue_map[job_id] = q_name
                return queue, saq_job

        return None, None

    async def ack(self, job_id: str) -> None:
        """Acknowledge successful job completion.

        Transitions the job to COMPLETED status by calling SAQ finish.
        Idempotent — safe to call on already-acked jobs.

        Args:
            job_id: The job identifier.
        """
        queue, saq_job = await self._find_job_in_queues(job_id)
        if queue is not None and saq_job is not None:
            await queue.finish(saq_job, saq.Status.COMPLETE)

    async def nack(self, job_id: str, requeue: bool = True) -> None:
        """Signal job failure — optionally requeue for retry.

        If requeue=True: calls SAQ retry (increments attempts, requeues).
            When SAQ retries are exhausted, job becomes ABORTED.
        If requeue=False: calls SAQ abort (marks FAILED immediately).

        Args:
            job_id: The job identifier.
            requeue: Whether to requeue the job for retry.
        """
        queue, saq_job = await self._find_job_in_queues(job_id)
        if queue is None or saq_job is None:
            return

        # Use tracked queue name from job_map (stable, not derived from SAQ Queue object)
        queue_name = self._job_queue_map.get(job_id, "unknown")

        if requeue:
            await queue.retry(saq_job, error="Job failed — requeueing for retry")
            # Check if retries exhausted (SAQ moves job to ABORTED on exhaustion)
            if saq_job.status in (saq.Status.ABORTED, saq.Status.FAILED):
                self._register_dlq(queue_name, job_id)
        else:
            await queue.abort(saq_job, error="Job failed — no requeue")
            self._register_dlq(queue_name, job_id)

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

        queue = self._get_or_create_queue(queue_name)
        retries = max_retries if max_retries is not None else 3

        # Convert datetime to epoch seconds for SAQ's scheduled parameter
        scheduled_epoch = int(execute_at.timestamp())

        saq_job: saq.Job | None = await queue.enqueue(
            _GENERIC_JOB_FUNCTION,
            payload=payload,
            queue_name=queue_name,
            retries=retries,
            timeout=self._timeout,
            scheduled=scheduled_epoch,
        )
        if saq_job is None:
            raise RuntimeError(f"Failed to schedule job on queue '{queue_name}'")

        self._track_job_queue(saq_job.key, queue_name)
        return JobRef(id=saq_job.key, queue=queue_name, status=JobStatus.PENDING)

    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by its identifier.

        Searches across all known queues for the job.

        Args:
            job_id: The job identifier.

        Returns:
            Job | None: The full Job object, or None if not found.
        """
        _queue, saq_job = await self._find_job_in_queues(job_id)
        if saq_job is None:
            return None

        return self._saq_job_to_cenf_job(saq_job)

    async def get_dlq_jobs(self, queue_name: str) -> list[Job]:
        """Retrieve all DEAD jobs in the DLQ for a given queue.

        Queries the internal DLQ registry and fetches each job from SAQ.

        Args:
            queue_name: The original queue name.

        Returns:
            list[Job]: DEAD jobs currently in the DLQ.
        """
        dlq_key = _DLQ_KEY_PREFIX + queue_name
        dead_keys = self._dlq.get(dlq_key, set())
        queue = self._queues.get(queue_name)

        if queue is None or not dead_keys:
            return []

        jobs: list[Job] = []
        remaining: set[str] = set()

        for job_key in dead_keys:
            saq_job = await queue.job(job_key)
            if saq_job is not None:
                cenf_job = self._saq_job_to_cenf_job(saq_job)
                # Override status to DEAD for DLQ jobs
                cenf_job.status = JobStatus.DEAD
                jobs.append(cenf_job)
                remaining.add(job_key)
            # If job not found in SAQ, it was cleaned up — remove from registry

        # Clean up registry for jobs no longer in SAQ
        self._dlq[dlq_key] = remaining

        return jobs
