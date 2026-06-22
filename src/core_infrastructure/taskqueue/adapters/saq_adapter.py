"""SaQAdapter — Redis-backed SAQ TaskQueueManager with async job processing.

Provides a production-ready TaskQueueManager implementation using SAQ
(Simple Async Queue) backed by Redis. Supports full job lifecycle:
enqueue, dequeue, ack, nack with retry, scheduled execution, and DLQ
tracking for exhausted-retry jobs.

Security: Payloads are validated as JSON-serializable before enqueue.
    Redis connection URL is masked in log output.
Observability: Job state transitions log at DEBUG level via LoggerManager.
@ai-directive: SAQ handles its own Redis connection pool and retry logic.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import saq

from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager
from core_infrastructure.taskqueue.adapters.saq_adapter_helpers import (
    DLQ_KEY_PREFIX,
    GENERIC_JOB_FUNCTION,
    find_job_in_queues,
    get_dlq_jobs_from_registry,
    get_or_create_queue,
    saq_job_to_cenf_job,
    validate_payload,
)
from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus


class SaQAdapter:
    """Redis-backed SAQ TaskQueueManager adapter.

    Multi-queue support: SAQ Queue instances are created and cached per
    queue name. Each queue uses the same Redis connection URL.

    Usage::
        adapter = SaQAdapter(config, secrets, logger, error_handler)
        ref = await adapter.enqueue("default", {"task": "process"})
    """

    def __init__(
        self, config: ConfigManager, secrets: SecretManager,
        logger: LoggerManager, error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._logger = logger
        self._error_handler = error_handler
        self._redis_url = config.get_string("taskqueue.redis_url", default_value="redis://localhost:6379/0")
        self._timeout = int(config.get_number("taskqueue.saq.timeout", default_value=30))
        self._queues: dict[str, saq.Queue] = {}
        self._dlq: dict[str, set[str]] = {}
        self._job_queue_map: dict[str, str] = {}
        self._started = False

        try:
            get_or_create_queue(self._queues, self._redis_url, "default")
            self._logger.debug("SaQAdapter: connected to Redis",
                               redis_url=self._logger.mask(self._redis_url, visible_chars=0))
        except Exception as exc:
            self._logger.warn("SaQAdapter: Redis unavailable",
                              redis_url=self._logger.mask(self._redis_url, visible_chars=0),
                              error=str(exc))

    # ── Backward-compatible wrappers ────────────────────────────────────
    _validate_payload = staticmethod(validate_payload)
    _saq_job_to_cenf_job = staticmethod(saq_job_to_cenf_job)

    @staticmethod
    def _saq_status_to_job_status(saq_status: saq.Status) -> JobStatus:
        from core_infrastructure.taskqueue.adapters.saq_adapter_helpers import saq_status_to_job_status
        return saq_status_to_job_status(saq_status)

    @staticmethod
    def _saq_job_queue_name(saq_job: saq.Job) -> str:
        from core_infrastructure.taskqueue.adapters.saq_adapter_helpers import saq_job_queue_name
        return saq_job_queue_name(saq_job)

    def _get_or_create_queue(self, queue_name: str) -> saq.Queue:
        return get_or_create_queue(self._queues, self._redis_url, queue_name)

    def _track_job_queue(self, job_key: str, queue_name: str) -> None:
        self._job_queue_map[job_key] = queue_name

    def _register_dlq(self, queue_name: str, job_key: str) -> None:
        dlq_key = DLQ_KEY_PREFIX + queue_name
        if dlq_key not in self._dlq:
            self._dlq[dlq_key] = set()
        self._dlq[dlq_key].add(job_key)

    # ── Public API ──────────────────────────────────────────────────────

    async def enqueue(self, queue_name: str, payload: dict[str, Any],
                      max_retries: int | None = None) -> JobRef:
        """Place a job onto a queue for immediate processing."""
        validate_payload(payload)
        queue = self._get_or_create_queue(queue_name)
        retries = max_retries if max_retries is not None else 3
        saq_job: saq.Job | None = await queue.enqueue(
            GENERIC_JOB_FUNCTION, payload=payload, queue_name=queue_name,
            retries=retries, timeout=self._timeout,
        )
        if saq_job is None:
            raise RuntimeError(f"Failed to enqueue job on queue '{queue_name}'")
        self._track_job_queue(saq_job.key, queue_name)
        return JobRef(id=saq_job.key, queue=queue_name, status=JobStatus.PENDING)

    async def dequeue(self, queue_name: str) -> Job | None:
        """Retrieve the next available job from a queue."""
        queue = self._get_or_create_queue(queue_name)
        saq_job = await queue.dequeue()
        if saq_job is None:
            return None
        self._track_job_queue(saq_job.key, queue_name)
        return saq_job_to_cenf_job(saq_job)

    async def ack(self, job_id: str) -> None:
        """Acknowledge successful job completion."""
        queue, saq_job = await find_job_in_queues(
            job_id, queues=self._queues, job_queue_map=self._job_queue_map,
        )
        if queue is not None and saq_job is not None:
            await queue.finish(saq_job, saq.Status.COMPLETE)

    async def nack(self, job_id: str, requeue: bool = True) -> None:
        """Signal job failure — optionally requeue for retry."""
        queue, saq_job = await find_job_in_queues(
            job_id, queues=self._queues, job_queue_map=self._job_queue_map,
        )
        if queue is None or saq_job is None:
            return
        queue_name = self._job_queue_map.get(job_id, "unknown")
        if requeue:
            await queue.retry(saq_job, error="Job failed — requeueing for retry")
            if saq_job.status in (saq.Status.ABORTED, saq.Status.FAILED):
                self._register_dlq(queue_name, job_id)
        else:
            await queue.abort(saq_job, error="Job failed — no requeue")
            self._register_dlq(queue_name, job_id)

    async def schedule(self, queue_name: str, payload: dict[str, Any],
                       execute_at: datetime, max_retries: int | None = None) -> JobRef:
        """Schedule a job for deferred execution."""
        validate_payload(payload)
        queue = self._get_or_create_queue(queue_name)
        retries = max_retries if max_retries is not None else 3
        scheduled_epoch = int(execute_at.timestamp())
        saq_job: saq.Job | None = await queue.enqueue(
            GENERIC_JOB_FUNCTION, payload=payload, queue_name=queue_name,
            retries=retries, timeout=self._timeout, scheduled=scheduled_epoch,
        )
        if saq_job is None:
            raise RuntimeError(f"Failed to schedule job on queue '{queue_name}'")
        self._track_job_queue(saq_job.key, queue_name)
        return JobRef(id=saq_job.key, queue=queue_name, status=JobStatus.PENDING)

    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by its identifier."""
        _queue, saq_job = await find_job_in_queues(
            job_id, queues=self._queues, job_queue_map=self._job_queue_map,
        )
        if saq_job is None:
            return None
        return saq_job_to_cenf_job(saq_job)

    async def get_dlq_jobs(self, queue_name: str) -> list[Job]:
        """Retrieve all DEAD jobs in the DLQ for a given queue (delegates to helpers)."""
        return await get_dlq_jobs_from_registry(
            queue_name, queues=self._queues, dlq=self._dlq,
        )
