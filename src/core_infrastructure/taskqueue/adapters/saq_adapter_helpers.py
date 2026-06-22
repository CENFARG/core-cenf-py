"""SaQAdapter helpers — job conversion, payload validation, queue utilities.

Extracted from ``saq_adapter.py`` to comply with the 250-line CENF rule.
Contains SAQ ↔ CENF job conversion, JSON payload validation, SAQ status
mapping, queue name extraction, and queue instance management.

What: Extracted helpers for SaQAdapter to reduce main module size.
Why: 250-line CENF rule compliance — pure refactoring, no behavior change.
Where: src/core_infrastructure/taskqueue/adapters/saq_adapter_helpers.py

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import saq

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.taskqueue.models import Job, JobStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENERIC_JOB_FUNCTION = "process_job"
DLQ_KEY_PREFIX = "cenf:taskqueue:dlq:"


def validate_payload(payload: dict[str, Any]) -> None:
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


def saq_status_to_job_status(saq_status: saq.Status) -> JobStatus:
    """Map SAQ Status to CENF JobStatus.

    Args:
        saq_status: The SAQ job status.

    Returns:
        JobStatus: The corresponding CENF job status.
    """
    mapping = {
        saq.Status.NEW: JobStatus.PENDING,
        saq.Status.QUEUED: JobStatus.PENDING,
        saq.Status.ACTIVE: JobStatus.PENDING,
        saq.Status.COMPLETE: JobStatus.COMPLETED,
        saq.Status.FAILED: JobStatus.FAILED,
        saq.Status.ABORTING: JobStatus.FAILED,
        saq.Status.ABORTED: JobStatus.FAILED,
    }
    return mapping.get(saq_status, JobStatus.PENDING)


def saq_job_queue_name(saq_job: saq.Job) -> str:
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


def saq_job_to_cenf_job(saq_job: saq.Job) -> Job:
    """Convert a SAQ Job to a CENF Job.

    Extracts the payload from SAQ job kwargs, falling back to
    the full kwargs dict if no ``payload`` key exists.

    Args:
        saq_job: The SAQ job to convert.

    Returns:
        Job: A CENF Job model instance.
    """
    payload: dict[str, Any] = (
        saq_job.kwargs.get("payload", saq_job.kwargs) if saq_job.kwargs else {}
    )

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
        queue=saq_job_queue_name(saq_job),
        payload=payload,
        status=saq_status_to_job_status(saq_job.status),
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


def get_or_create_queue(
    queues: dict[str, saq.Queue], redis_url: str, queue_name: str
) -> saq.Queue:
    """Get or create a SAQ Queue instance for the given queue name.

    Args:
        queues: The queue_name → saq.Queue cache dict.
        redis_url: The Redis connection URL.
        queue_name: The CENF queue name.

    Returns:
        saq.Queue: The SAQ queue instance for this queue name.
    """
    if queue_name not in queues:
        queues[queue_name] = saq.Queue.from_url(
            redis_url,
            name=queue_name,
        )
    return queues[queue_name]


async def find_job_in_queues(
    job_id: str,
    *,
    queues: dict[str, saq.Queue],
    job_queue_map: dict[str, str],
) -> tuple[saq.Queue | None, saq.Job | None]:
    """Find a SAQ job across all known queues.

    First checks the job-to-queue map (O(1)), then falls back to
    scanning all known queues (O(n)).

    Args:
        job_id: The SAQ job key.
        queues: The queue_name → saq.Queue cache dict.
        job_queue_map: The job_key → queue_name mapping.

    Returns:
        tuple: (queue, saq_job) or (None, None) if not found.
    """
    # Fast path: job-to-queue map
    queue_name = job_queue_map.get(job_id)
    if queue_name and queue_name in queues:
        queue = queues[queue_name]
        saq_job = await queue.job(job_id)
        if saq_job is not None:
            return queue, saq_job

    # Slow path: scan all queues
    for q_name, queue in queues.items():
        saq_job = await queue.job(job_id)
        if saq_job is not None:
            job_queue_map[job_id] = q_name
            return queue, saq_job

    return None, None


async def get_dlq_jobs_from_registry(
    queue_name: str,
    *,
    queues: dict[str, saq.Queue],
    dlq: dict[str, set[str]],
) -> list[Job]:
    """Retrieve all DEAD jobs in the DLQ for a given queue.

    Queries the internal DLQ registry and fetches each job from SAQ.

    Args:
        queue_name: The original queue name.
        queues: The queue_name → saq.Queue cache dict.
        dlq: The DLQ registry (dlq_key → set of job keys). Mutated to remove stale entries.

    Returns:
        list[Job]: DEAD jobs currently in the DLQ.
    """
    dlq_key = DLQ_KEY_PREFIX + queue_name
    dead_keys = dlq.get(dlq_key, set())
    queue = queues.get(queue_name)

    if queue is None or not dead_keys:
        return []

    jobs: list[Job] = []
    remaining: set[str] = set()

    for job_key in dead_keys:
        saq_job = await queue.job(job_key)
        if saq_job is not None:
            cenf_job = saq_job_to_cenf_job(saq_job)
            cenf_job.status = JobStatus.DEAD
            jobs.append(cenf_job)
            remaining.add(job_key)

    dlq[dlq_key] = remaining
    return jobs
