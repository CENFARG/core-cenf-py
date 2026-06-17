---
Spec_ID: SPEC_M10
Title: TaskQueueManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [task-queue, saq, dlq, scheduling]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M10: TaskQueueManager

## Purpose

Provide async task queue with SAQ (MIT license), DLQ support, exponential backoff, and scheduled job execution. Restores contextvars snapshot per job.

**Does NOT**: Serialize live descriptors, block the event-loop during job processing.

## Python Protocol

```python
from __future__ import annotations
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from core_infrastructure.taskqueue.models import Job, JobRef

@runtime_checkable
class TaskQueueManager(Protocol):
    """@ai-directive: Ack/nack MUST be idempotent. DLQ jobs require manual inspection."""

    async def enqueue(self, queue_name: str, payload: dict[str, Any], max_retries: int | None = None) -> JobRef:
        """Place a job onto a queue for immediate processing."""
        ...

    async def dequeue(self, queue_name: str) -> Job | None:
        """Retrieve and lock the next available job. Returns None if empty."""
        ...

    async def ack(self, job_id: str) -> None:
        """Acknowledge successful job completion. Idempotent."""
        ...

    async def nack(self, job_id: str, requeue: bool = True) -> None:
        """Signal job failure. Requeue or move to DLQ based on attempts."""
        ...

    async def schedule(self, queue_name: str, payload: dict[str, Any], execute_at: datetime, max_retries: int | None = None) -> JobRef:
        """Schedule a job for deferred execution."""
        ...

    async def get_job(self, job_id: str) -> Job | None:
        """Retrieve a job by ID. Returns None for unknown IDs."""
        ...

    async def get_dlq_jobs(self, queue_name: str) -> list[Job]:
        """Retrieve all DEAD jobs in the DLQ for a given queue."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class TaskQueueSettings(BaseModel):
    redis_url: str = Field(min_length=1, default="redis://localhost:6379")
    queue_name: str = Field(min_length=1, max_length=64, default="default")
    worker_concurrency: int = Field(default=10, ge=1, le=100)
    max_retries_default: int = Field(default=3, ge=1, le=10)
    backoff_base_seconds: float = Field(default=2.0, ge=0.5)
    backoff_max_seconds: float = Field(default=300.0, ge=10.0)
    dlq_enabled: bool = Field(default=True)
    job_timeout_seconds: int = Field(default=300, ge=10, le=3600)

class Job(BaseModel):
    id: str
    queue: str
    payload: dict[str, Any]
    status: Literal["pending", "running", "completed", "failed", "dead"]
    attempts: int = Field(default=0)
    max_retries: int = Field(default=3)
    execute_at: datetime | None = Field(default=None)
    created_at: datetime
    updated_at: datetime

class JobRef(BaseModel):
    id: str
    queue: str
    status: str
```

## Gherkin Scenarios

### Scenario: Enqueue and dequeue

- WHEN `enqueue("default", {"action": "process"})` is called
- THEN it returns a `JobRef` with a unique id
- AND `dequeue("default")` returns the `Job` with status "running"

### Scenario: Ack marks job completed

- GIVEN a job with status "running"
- WHEN `ack(job_id)` is called
- THEN the job status becomes "completed"
- AND calling `ack(job_id)` again is a no-op (idempotent)

### Scenario: Nack with requeue moves to DLQ after max retries

- GIVEN a job with attempts=2 and max_retries=3
- WHEN `nack(job_id, requeue=True)` is called
- THEN attempts becomes 3, which equals max_retries
- AND the job transitions to "dead" and moves to DLQ

### Scenario: Scheduled job skips until execute_at

- GIVEN a job scheduled with execute_at = 1 hour from now
- WHEN `dequeue("default")` is called immediately
- THEN it returns None (job not yet eligible)

### Scenario: Non-serializable payload raises ValidationError

- WHEN `enqueue("default", {"data": object()})` is called (object not JSON-serializable)
- THEN it raises `ValidationError`

### Scenario: Contextvars restored per job

- GIVEN a job was enqueued with correlation_id="abc"
- WHEN the job is dequeued and processed
- THEN correlation_id contextvar is restored to "abc"

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Non-serializable payload | VALIDATION | Re-raise immediately |
| Redis connection lost | TRANSIENT | Retry with backoff |
| Worker misconfiguration | PERMANENT | Fail bootstrap |
| Job not found | VALIDATION | Return None (not error) |

## RED Metrics

- `cenf.taskqueue.enqueue_total` (counter)
- `cenf.taskqueue.dequeue_total` (counter)
- `cenf.taskqueue.errors_total` (counter)
- `cenf.taskqueue.process_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryTaskQueueAdapter` — dict-based with async scheduling simulation.
- **Integration**: `SAQAdapter` with Redis testcontainer.
- **E2E**: Scheduled job timing, DLQ reprocessing.

## Do's and Don'ts

**Do**:
- Use SAQ (MIT license) as the queue backend
- Implement Dead-Letter Queue for failed jobs
- Restore contextvars snapshot per job execution
- Use exponential backoff for retries

**Don't**:
- Serialize live descriptors (file handles, connections)
- Block the event-loop during job processing
- Lose job context across queue boundaries
