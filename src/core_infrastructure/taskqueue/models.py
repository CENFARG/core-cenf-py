"""CENF TaskQueueManager models — Job, JobRef, JobStatus, QueueConfig.

Defines the Pydantic models for the task queue domain: Job lifecycle states,
QueueConfig for retry/backoff policies, and JobRef as a lightweight job handle.

Security: Job.payload is validated as JSON-serializable. No credentials or PII
    should be placed in payload without encryption.
Observability: Every job state transition is logged at DEBUG level via LoggerManager.
@ai-directive: JobStatus.DEAD is terminal — jobs in DLQ require manual intervention.
    Exponential backoff uses backoff_base^attempts * backoff_factor * (1 + jitter).

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    """Job lifecycle states for task queue processing.

    Transitions:
        PENDING → RUNNING → COMPLETED (ack)
        PENDING → RUNNING → PENDING (nack + requeue, increment attempts)
        PENDING → RUNNING → FAILED (nack, no requeue)
        FAILED → DEAD (exhausted max_retries, moved to DLQ)
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD = "DEAD"


class Job(BaseModel):
    """A task queue job with full lifecycle tracking.

    Represents a single unit of work in the task queue. Tracks status,
    retry attempts, and scheduling metadata. When max_retries is exhausted,
    the job transitions to DEAD and moves to the DLQ.

    Attributes:
        id: Unique job identifier (UUID4).
        queue: Name of the queue this job belongs to.
        payload: JSON-serializable dict with job data.
        status: Current lifecycle status.
        attempts: Number of processing attempts so far.
        max_retries: Maximum retry attempts before DLQ.
        created_at: UTC timestamp when the job was created.
        execute_at: Optional scheduled execution time (UTC).
        error: Last error message if the job failed.
    """

    id: str = Field(..., min_length=1, max_length=64, description="Unique job identifier.")
    queue: str = Field(..., min_length=1, max_length=128, description="Queue name.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON-serializable job payload.",
    )
    status: JobStatus = Field(default=JobStatus.PENDING, description="Current lifecycle status.")
    attempts: int = Field(default=0, ge=0, description="Number of processing attempts.")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts before DLQ.")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the job was created.",
    )
    execute_at: datetime | None = Field(
        default=None,
        description="Scheduled execution time (UTC). None = immediate.",
    )
    error: str | None = Field(
        default=None,
        description="Last error message if the job failed.",
    )


class JobRef(BaseModel):
    """Lightweight reference to a job — returned by enqueue/schedule.

    Callers receive a JobRef as a handle to track the job without
    exposing the full payload. Use get_job() to retrieve the full Job.

    Attributes:
        id: Job identifier.
        queue: Queue name.
        status: Current job status.
    """

    id: str = Field(..., min_length=1, max_length=64, description="Job identifier.")
    queue: str = Field(..., min_length=1, max_length=128, description="Queue name.")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Current status.")


class QueueConfig(BaseModel):
    """Configuration for task queue retry and backoff behavior.

    Controls how the task queue handles retries and DLQ routing.
    Exponential backoff formula:
        delay = backoff_base^attempts * backoff_factor * (1 + random_jitter)

    Attributes:
        default_max_retries: Default max retry attempts before DLQ routing.
        backoff_base: Base for exponential backoff calculation.
        backoff_factor: Multiplier for backoff calculation.
        dlq_suffix: Suffix appended to queue name for DLQ.
    """

    default_max_retries: int = Field(default=3, ge=0, description="Default max retry attempts.")
    backoff_base: float = Field(default=2.0, gt=0, description="Base for exponential backoff.")
    backoff_factor: float = Field(default=1.0, gt=0, description="Multiplier for backoff calculation.")
    dlq_suffix: str = Field(default="_dlq", min_length=1, max_length=32, description="Suffix for DLQ queue name.")
