---
sidebar_position: 10
---

# TaskQueueManager (M10)

Async task queue with job lifecycle management, retry with exponential backoff, scheduled (deferred) execution, and dead-letter queue (DLQ) support.

## Protocol

`TaskQueueManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.taskqueue.ports`.

### `async enqueue(queue_name: str, payload: dict[str, Any], max_retries: int | None = None) → JobRef`

Place a job onto a queue for immediate processing.

```python
async def enqueue(
    self,
    queue_name: str,
    payload: dict[str, Any],
    max_retries: int | None = None,
) -> JobRef: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `queue_name` | `str` | Target queue name. Created implicitly if not exists |
| `payload` | `dict[str, Any]` | JSON-serializable dict with job data |
| `max_retries` | `int \| None` | Optional override for `QueueConfig.default_max_retries` |

**Returns:** `JobRef` — a handle with `id`, `queue`, and `status`.

**Raises:** `ValidationError` if payload is not JSON-serializable.

---

### `async dequeue(queue_name: str) → Job | None`

Retrieve and lock the next available job from a queue.

```python
async def dequeue(self, queue_name: str) -> Job | None: ...
```

Returns the oldest PENDING job whose `execute_at` is in the past (or `None`). The job transitions to RUNNING status.

---

### `async ack(job_id: str) → None`

Acknowledge successful job completion.

```python
async def ack(self, job_id: str) -> None: ...
```

Transitions the job to COMPLETED status. Idempotent — safe to call multiple times.

---

### `async nack(job_id: str, requeue: bool = True) → None`

Signal job failure — optionally requeue for retry.

```python
async def nack(self, job_id: str, requeue: bool = True) -> None: ...
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `job_id` | `str` | *(required)* | Job identifier |
| `requeue` | `bool` | `True` | Whether to requeue for retry |

**Behavior:**
- `requeue=True`: increments `attempts`, resets to PENDING. If `attempts >= max_retries`, transitions to DEAD and moves to DLQ.
- `requeue=False`: transitions to FAILED immediately.

Does NOT raise for unknown job IDs — no-op.

---

### `async schedule(queue_name: str, payload: dict[str, Any], execute_at: datetime, max_retries: int | None = None) → JobRef`

Schedule a job for deferred execution.

```python
async def schedule(
    self,
    queue_name: str,
    payload: dict[str, Any],
    execute_at: datetime,
    max_retries: int | None = None,
) -> JobRef: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `queue_name` | `str` | Target queue name |
| `payload` | `dict[str, Any]` | JSON-serializable dict with job data |
| `execute_at` | `datetime` | UTC datetime when the job becomes eligible for dequeue |
| `max_retries` | `int \| None` | Optional override for retry attempts |

**Raises:** `ValidationError` if payload is not JSON-serializable.

---

### `async get_job(job_id: str) → Job | None`

Retrieve a job by its identifier.

```python
async def get_job(self, job_id: str) -> Job | None: ...
```

**Returns:** The full `Job` object, or `None` if not found. **Never raises.**

---

### `async get_dlq_jobs(queue_name: str) → list[Job]`

Retrieve all DEAD jobs in the DLQ for a given queue.

```python
async def get_dlq_jobs(self, queue_name: str) -> list[Job]: ...
```

The DLQ suffix (from `QueueConfig.dlq_suffix`, default `_dlq`) is appended internally.

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing `QueueConfig`.

## Job Lifecycle

```
PENDING ──dequeue()──→ RUNNING ──ack()──→ COMPLETED
   ↑                      │
   │              ┌───────┤
   │              │       └──nack(requeue=False)──→ FAILED
   │              │                                      │
   │              └──nack(requeue=True)                  │
   │                   (attempts < max_retries)          │
   │                   (increments attempts)             │
   │                   (resets to PENDING)               │
   │                                                    │
   └────────────────────────────────────────────────────┘
                                                         │
                            nack(requeue=True)           │
                            (attempts >= max_retries)    │
                            ────────────────────────→ DEAD → DLQ
```

## Dead-Letter Queue (DLQ)

When a job exhausts `max_retries`:
1. Status transitions to `DEAD`
2. Job is moved to the DLQ (queue name + `_dlq` suffix, e.g., `email_dlq`)
3. DLQ jobs require **manual inspection** and reprocessing
4. Use `get_dlq_jobs()` to retrieve DEAD jobs

## Models

### `JobStatus`

```python
class JobStatus(StrEnum):
    PENDING = "PENDING"       # Waiting to be dequeued
    RUNNING = "RUNNING"       # Currently being processed
    COMPLETED = "COMPLETED"   # Successfully acknowledged
    FAILED = "FAILED"         # Failed without requeue
    DEAD = "DEAD"             # Exhausted max_retries, in DLQ
```

---

### `Job`

**File:** `core_infrastructure.taskqueue.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` (1–64) | *(required)* | Unique job identifier (UUID4) |
| `queue` | `str` (1–128) | *(required)* | Queue name |
| `payload` | `dict[str, Any]` | `{}` | JSON-serializable job payload |
| `status` | `JobStatus` | `PENDING` | Current lifecycle status |
| `attempts` | `int` (≥0) | `0` | Number of processing attempts |
| `max_retries` | `int` (≥0) | `3` | Maximum retry attempts before DLQ |
| `created_at` | `datetime` | `now(UTC)` | UTC timestamp when created |
| `execute_at` | `datetime \| None` | `None` | Scheduled execution time (None = immediate) |
| `error` | `str \| None` | `None` | Last error message if failed |

---

### `JobRef`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` (1–64) | *(required)* | Job identifier |
| `queue` | `str` (1–128) | *(required)* | Queue name |
| `status` | `JobStatus` | `PENDING` | Current status |

Lightweight handle returned by `enqueue()`/`schedule()` — callers receive this without the full payload.

---

### `QueueConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_max_retries` | `int` (≥0) | `3` | Default max retry attempts |
| `backoff_base` | `float` (>0) | `2.0` | Base for exponential backoff |
| `backoff_factor` | `float` (>0) | `1.0` | Multiplier for backoff calculation |
| `dlq_suffix` | `str` (1–32) | `"_dlq"` | Suffix appended to queue name for DLQ |

**Exponential backoff formula:**
```
delay = backoff_base^attempts * backoff_factor * (1 + random_jitter)
```

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `MemoryTaskQueueAdapter` | Python list + dict | Dev/testing — in-process, no persistence |
| `SaqAdapter` | SAQ (Redis-backed) | Production — persistent queues with Redis |

## Usage Example

```python
from core_infrastructure.taskqueue.adapters.memory_task_queue_adapter import MemoryTaskQueueAdapter

# Bootstrap
tq = MemoryTaskQueueAdapter(config_manager=config, logger_manager=logger)

# Enqueue a job for immediate processing
ref = await tq.enqueue(
    queue_name="email",
    payload={"to": "user@example.com", "template": "welcome", "data": {"name": "Alice"}},
    max_retries=3,
)
# → JobRef(id="uuid-...", queue="email", status=PENDING)

# Schedule a job for deferred execution
from datetime import datetime, timedelta, UTC

ref2 = await tq.schedule(
    queue_name="reports",
    payload={"report_type": "monthly", "org_id": "org-42"},
    execute_at=datetime.now(UTC) + timedelta(hours=1),
)

# Worker: dequeue and process
job = await tq.dequeue("email")
if job is not None:
    try:
        # Process the job
        send_email(job.payload["to"], job.payload["template"], **job.payload["data"])
        await tq.ack(job.id)  # → COMPLETED
    except TransientError as e:
        # Retryable — requeue for retry
        await tq.nack(job.id, requeue=True)
        # If attempts < max_retries → PENDING (retry)
        # If attempts >= max_retries → DEAD (moved to DLQ)
    except Exception as e:
        # Non-retryable — fail immediately
        await tq.nack(job.id, requeue=False)  # → FAILED

# Inspect a job
full_job = await tq.get_job(ref.id)
if full_job:
    print(f"Status: {full_job.status}, Attempts: {full_job.attempts}")

# Inspect dead-letter queue
dead_jobs = await tq.get_dlq_jobs("email")
for dead in dead_jobs:
    logger.error("DLQ job", job_id=dead.id, error=dead.error, attempts=dead.attempts)
```

### Worker Loop Pattern

```python
import asyncio

async def worker(tq: TaskQueueManager, queue_name: str):
    """Continuously process jobs from the queue."""
    while True:
        job = await tq.dequeue(queue_name)
        if job is None:
            await asyncio.sleep(1)  # No jobs available
            continue

        try:
            await process_job(job.payload)
            await tq.ack(job.id)
            logger.info("Job completed", job_id=job.id)
        except TransientError:
            await tq.nack(job.id, requeue=True)
            logger.warn("Job retried", job_id=job.id, attempts=job.attempts + 1)
        except Exception:
            await tq.nack(job.id, requeue=False)
            logger.error("Job failed", job_id=job.id)
```

## @ai-directive

- **Payloads MUST be JSON-serializable.** Never queue credentials or tokens in plain text — encrypt sensitive payloads before enqueuing.
- `ack()` and `nack()` MUST be idempotent — calling `ack` on an already-acked job is a no-op.
- DLQ jobs require manual inspection and reprocessing. `JobStatus.DEAD` is terminal.
- Exponential backoff uses `backoff_base^attempts * backoff_factor * (1 + jitter)`.

## Related

- [ErrorHandlingManager](error-handling-manager.md) — TRANSIENT classification drives retry decisions
- [LoggerManager](logger-manager.md) — every state transition logged at DEBUG level
- [ObservabilityManager](observability-manager.md) — enqueue/dequeue/ack/nack counters under `cenf.taskqueue.*`
- [CacheManager](cache-manager.md) — can be used to deduplicate job payloads
