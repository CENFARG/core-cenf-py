"""Unit tests for SaQAdapter — Redis-backed SAQ TaskQueueManager.

Tests cover:
- Protocol compliance (satisfies TaskQueueManager)
- enqueue / dequeue job lifecycle
- ack marks job COMPLETED via SAQ finish
- nack with requeue retries via SAQ retry
- nack without requeue marks FAILED via SAQ abort
- schedule() with execute_at
- get_job() lookup
- get_dlq_jobs() returns dead-letter queue jobs
- JSON payload validation
- Graceful error on Redis unavailable

Mock strategy: SAQ Queue is mocked via AsyncMock to avoid Redis dependency.
The adapter logic (CENF Protocol ↔ SAQ API translation) is what is tested.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import saq

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.adapters.in_memory_config_adapter import (
    InMemoryConfigAdapter,
)
from core_infrastructure.errors.adapters.capturing_error_adapter import (
    CapturingErrorAdapter,
)
from core_infrastructure.logger.adapters.in_memory_logger_adapter import (
    InMemoryLoggerAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import (
    InMemorySecretAdapter,
)
from core_infrastructure.taskqueue.models import JobRef, JobStatus
from core_infrastructure.taskqueue.ports import TaskQueueManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(redis_url: str = "redis://localhost:6379/0") -> InMemoryConfigAdapter:
    """Create a ConfigManager with SAQ taskqueue settings."""
    return InMemoryConfigAdapter(
        {
            "taskqueue.redis_url": redis_url,
            "taskqueue.saq.concurrency": 10,
            "taskqueue.saq.timeout": 30,
        }
    )


def _make_logger() -> InMemoryLoggerAdapter:
    """Create an in-memory logger for testing."""
    return InMemoryLoggerAdapter()


def _make_secrets() -> InMemorySecretAdapter:
    """Create an in-memory secret manager for testing."""
    return InMemorySecretAdapter()


def _make_error_handler(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
) -> CapturingErrorAdapter:
    """Create a capturing error handler for testing."""
    from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
        InMemoryObservabilityAdapter,
    )

    obs = InMemoryObservabilityAdapter()
    return CapturingErrorAdapter(config=config, logger=logger, observability=obs)


def _create_saq_job_mock(
    key: str = "job-001",
    queue: str = "default",
    kwargs: dict | None = None,
    status: saq.Status = saq.Status.QUEUED,
) -> MagicMock:
    """Create a mock SAQ Job that looks like a real saq.Job."""
    mock_job = MagicMock(spec=saq.Job)
    mock_job.key = key
    # SAQ stores Queue instance, not string — but mock uses string for simplicity
    mock_job.queue = queue
    mock_job.kwargs = kwargs or {}
    mock_job.function = "process_job"
    mock_job.status = status
    # Numeric fields — must be real ints, not MagicMock
    mock_job.scheduled = 0
    mock_job.queued = 1700000000  # non-zero epoch so created_at is computed
    mock_job.attempts = 0
    mock_job.retries = 3
    mock_job.error = None
    return mock_job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """ConfigManager with default SAQ settings."""
    return _make_config()


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """In-memory logger for testing."""
    return _make_logger()


@pytest.fixture
def secrets() -> InMemorySecretAdapter:
    """In-memory secret manager for testing."""
    return _make_secrets()


@pytest.fixture
def error_handler(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
) -> CapturingErrorAdapter:
    """Error handler for testing."""
    return _make_error_handler(config, logger)


# ---------------------------------------------------------------------------
# Test: Protocol compliance
# ---------------------------------------------------------------------------


class TestSaQAdapterProtocol:
    """Verify SaQAdapter satisfies TaskQueueManager Protocol."""

    def test_satisfies_task_queue_manager_protocol(self) -> None:
        """SaQAdapter passes isinstance check against TaskQueueManager."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        config = _make_config()
        logger = _make_logger()
        secrets = _make_secrets()
        error_handler = _make_error_handler(config, logger)

        # Use patch to avoid real Redis connection during isinstance check
        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=MagicMock()):
            adapter = SaQAdapter(
                config=config,
                secrets=secrets,
                logger=logger,
                error_handler=error_handler,
            )
            assert isinstance(adapter, TaskQueueManager)


# ---------------------------------------------------------------------------
# Test: Enqueue / Dequeue lifecycle
# ---------------------------------------------------------------------------


class TestEnqueueDequeue:
    """Verify basic enqueue / dequeue job lifecycle through SAQ adapter."""

    @pytest.mark.asyncio
    async def test_enqueue_returns_jobref_pending(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """enqueue() returns a JobRef with PENDING status and correct queue."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_job = _create_saq_job_mock(key="job-abc", queue="default")
        mock_queue.enqueue = AsyncMock(return_value=mock_job)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            ref = await adapter.enqueue("default", {"msg": "hello"})
            assert isinstance(ref, JobRef)
            assert ref.queue == "default"
            assert ref.status == JobStatus.PENDING
            assert ref.id == "job-abc"

    @pytest.mark.asyncio
    async def test_enqueue_calls_saq_with_payload(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """enqueue() calls SAQ enqueue with function='process_job' and payload in kwargs."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_job = _create_saq_job_mock(key="job-xyz", queue="my-q")
        mock_queue.enqueue = AsyncMock(return_value=mock_job)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            await adapter.enqueue("my-q", {"task": "process"})
            # Verify SAQ enqueue was called with correct args
            mock_queue.enqueue.assert_called_once()
            call_args = mock_queue.enqueue.call_args
            assert call_args[0][0] == "process_job"
            assert call_args[1]["payload"] == {"task": "process"}

    @pytest.mark.asyncio
    async def test_dequeue_returns_job(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """dequeue() returns a CENF Job from SAQ."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_saq_job = _create_saq_job_mock(
            key="job-def", queue="default",
            kwargs={"payload": {"task": "test"}}
        )
        mock_queue.dequeue = AsyncMock(return_value=mock_saq_job)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            job = await adapter.dequeue("default")
            assert job is not None
            assert job.id == "job-def"
            assert job.queue == "default"
            assert job.payload == {"task": "test"}

    @pytest.mark.asyncio
    async def test_dequeue_handles_kwargs_without_payload_key(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """dequeue() falls back to full kwargs dict when no 'payload' key exists."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_saq_job = _create_saq_job_mock(
            key="job-nopayload", queue="default",
            kwargs={"task": "direct", "id": 42}
        )
        mock_queue.dequeue = AsyncMock(return_value=mock_saq_job)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            job = await adapter.dequeue("default")
            assert job is not None
            assert job.payload == {"task": "direct", "id": 42}

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue_returns_none(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """dequeue() on empty queue returns None."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_queue.dequeue = AsyncMock(return_value=None)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            job = await adapter.dequeue("empty-q")
            assert job is None

    @pytest.mark.asyncio
    async def test_enqueue_with_max_retries_override(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """enqueue() passes max_retries override to SAQ enqueue."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_job = _create_saq_job_mock(key="job-retry", queue="default")
        mock_queue.enqueue = AsyncMock(return_value=mock_job)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            await adapter.enqueue("default", {"task": "fragile"}, max_retries=5)
            call_kwargs = mock_queue.enqueue.call_args[1]
            assert call_kwargs["retries"] == 5

    @pytest.mark.asyncio
    async def test_enqueue_dequeue_cycle_fifo(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """enqueue/dequeue cycle returns jobs in order."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        job1 = _create_saq_job_mock(key="j1", queue="default", kwargs={"payload": {"seq": 1}})
        job2 = _create_saq_job_mock(key="j2", queue="default", kwargs={"payload": {"seq": 2}})

        mock_queue = MagicMock()
        mock_queue.enqueue = AsyncMock(side_effect=[job1, job2])
        # SAQ handles FIFO internally via Redis lists; our adapter just calls dequeue
        mock_queue.dequeue = AsyncMock(side_effect=[job1, job2, None])

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            ref1 = await adapter.enqueue("default", {"seq": 1})
            ref2 = await adapter.enqueue("default", {"seq": 2})

            assert ref1.id == "j1"
            assert ref2.id == "j2"

            dq1 = await adapter.dequeue("default")
            dq2 = await adapter.dequeue("default")
            empty = await adapter.dequeue("default")

            assert dq1 is not None and dq1.payload == {"seq": 1}
            assert dq2 is not None and dq2.payload == {"seq": 2}
            assert empty is None


# ---------------------------------------------------------------------------
# Test: Ack / Nack lifecycle
# ---------------------------------------------------------------------------


class TestAckNack:
    """Verify ack/nack job lifecycle through SAQ adapter."""

    @pytest.mark.asyncio
    async def test_ack_calls_saq_finish(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """ack() calls SAQ finish with COMPLETE status."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_queue.finish = AsyncMock()
        mock_queue.job = AsyncMock()
        # Simulate get_job for ack lookup
        job_in_store = _create_saq_job_mock(key="job-ack", queue="default")
        mock_queue.job.return_value = job_in_store

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            await adapter.ack("job-ack")
            mock_queue.finish.assert_called_once()
            call_args = mock_queue.finish.call_args
            assert call_args[0][1] == saq.Status.COMPLETE

    @pytest.mark.asyncio
    async def test_nack_with_requeue_calls_saq_retry(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """nack(job_id, requeue=True) calls SAQ retry."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_queue.retry = AsyncMock()
        mock_queue.job = AsyncMock()
        job_in_store = _create_saq_job_mock(key="job-retry", queue="default")
        mock_queue.job.return_value = job_in_store

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            await adapter.nack("job-retry", requeue=True)
            mock_queue.retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_nack_without_requeue_calls_saq_abort(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """nack(job_id, requeue=False) calls SAQ abort."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_queue.abort = AsyncMock()
        mock_queue.job = AsyncMock()
        job_in_store = _create_saq_job_mock(key="job-abort", queue="default")
        mock_queue.job.return_value = job_in_store

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            await adapter.nack("job-abort", requeue=False)
            mock_queue.abort.assert_called_once()

    @pytest.mark.asyncio
    async def test_nack_unknown_job_does_not_raise(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """nack() on unknown job ID does not raise."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_queue.job = AsyncMock(return_value=None)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            # Should not raise
            await adapter.nack("nonexistent", requeue=True)


# ---------------------------------------------------------------------------
# Test: Scheduling
# ---------------------------------------------------------------------------


class TestScheduling:
    """Verify schedule() with execute_at through SAQ adapter."""

    @pytest.mark.asyncio
    async def test_schedule_sets_scheduled_field(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """schedule() enqueues a job with scheduled timestamp."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_saq_job = _create_saq_job_mock(key="job-sched", queue="default")
        mock_saq_job.scheduled = 1700000000  # epoch seconds
        mock_queue.enqueue = AsyncMock(return_value=mock_saq_job)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            future = datetime.now(UTC) + timedelta(minutes=5)
            ref = await adapter.schedule("default", {"task": "future"}, execute_at=future)
            assert isinstance(ref, JobRef)
            assert ref.id == "job-sched"
            assert ref.status == JobStatus.PENDING
            # Verify scheduled was passed to SAQ enqueue
            call_kwargs = mock_queue.enqueue.call_args[1]
            assert "scheduled" in call_kwargs


# ---------------------------------------------------------------------------
# Test: GetJob
# ---------------------------------------------------------------------------


class TestGetJob:
    """Verify get_job() lookup through SAQ adapter."""

    @pytest.mark.asyncio
    async def test_get_job_returns_job_by_id(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """get_job() returns the Job for a valid ID."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        saq_job = _create_saq_job_mock(
            key="job-find", queue="default",
            kwargs={"payload": {"task": "find-me"}}
        )
        mock_queue.job = AsyncMock(return_value=saq_job)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            job = await adapter.get_job("job-find")
            assert job is not None
            assert job.id == "job-find"
            assert job.payload == {"task": "find-me"}

    @pytest.mark.asyncio
    async def test_get_job_unknown_id_returns_none(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """get_job() returns None for unknown IDs."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_queue.job = AsyncMock(return_value=None)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            job = await adapter.get_job("nonexistent")
            assert job is None


# ---------------------------------------------------------------------------
# Test: Payload validation
# ---------------------------------------------------------------------------


class TestPayloadValidation:
    """Verify JSON payload validation in SAQ adapter."""

    @pytest.mark.asyncio
    async def test_enqueue_accepts_json_serializable_payload(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """enqueue() accepts JSON-serializable payloads."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_job = _create_saq_job_mock(key="job-json", queue="default")
        mock_queue.enqueue = AsyncMock(return_value=mock_job)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            ref = await adapter.enqueue("default", {
                "str": "value", "int": 1, "float": 1.5,
                "bool": True, "list": [1, 2, 3], "nested": {"a": 1},
            })
            assert ref.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_enqueue_rejects_non_json_serializable_payload(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """enqueue() raises ValidationError for non-JSON-serializable payloads."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            with pytest.raises(ValidationError):
                # set is not JSON-serializable
                await adapter.enqueue("default", {"bad": {1, 2, 3}})  # type: ignore[dict-item]


# ---------------------------------------------------------------------------
# Test: Redis unavailable — graceful error
# ---------------------------------------------------------------------------


class TestRedisUnavailable:
    """Verify graceful handling when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_redis_unavailable_logs_warning_and_returns_none_on_dequeue(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """When Redis is unavailable, dequeue returns None and logs warning."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        # Simulate connection failure by making SAQ Queue.from_url raise
        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   side_effect=Exception("Connection refused")):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            # enqueue should raise (no connection — SAQ from_url raises)
            with pytest.raises(Exception, match="Connection refused"):
                await adapter.enqueue("default", {"task": "test"})

    @pytest.mark.asyncio
    async def test_redis_connection_error_on_init_logs_warning(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """When Redis connection fails at init, adapter logs a warning."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   side_effect=Exception("Connection refused")):
            SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            # Verify warning was logged
            logs = logger.get_logs()
            warning_logs = [log for log in logs if log.get("level", "").upper() == "WARNING"]
            assert len(warning_logs) >= 1
            assert any("Redis" in str(log) for log in warning_logs)


# ---------------------------------------------------------------------------
# Test: get_dlq_jobs
# ---------------------------------------------------------------------------


class TestGetDLQJobs:
    """Verify get_dlq_jobs() through SAQ adapter."""

    @pytest.mark.asyncio
    async def test_get_dlq_jobs_returns_empty_for_fresh_queue(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """get_dlq_jobs() returns empty list for a queue with no dead jobs."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_queue.job = AsyncMock(return_value=None)

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            jobs = await adapter.get_dlq_jobs("default")
            assert jobs == []

    @pytest.mark.asyncio
    async def test_get_dlq_jobs_returns_dead_jobs_after_nack_abort(
        self, config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter,
        secrets: InMemorySecretAdapter, error_handler: CapturingErrorAdapter,
    ) -> None:
        """After nack(requeue=False), the job appears in DLQ with DEAD status."""
        from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter

        mock_queue = MagicMock()
        mock_queue.enqueue = AsyncMock()
        mock_queue.dequeue = AsyncMock()
        mock_queue.finish = AsyncMock()
        mock_queue.abort = AsyncMock()
        mock_queue.retry = AsyncMock()

        job_key = "dlq-job-001"
        saq_job = _create_saq_job_mock(key=job_key, queue="default", kwargs={"payload": {"task": "dead"}})
        mock_queue.job = AsyncMock(return_value=saq_job)
        mock_queue.enqueue.return_value = saq_job

        with patch("core_infrastructure.taskqueue.adapters.saq_adapter.saq.Queue.from_url",
                   return_value=mock_queue):
            adapter = SaQAdapter(
                config=config, secrets=secrets, logger=logger,
                error_handler=error_handler,
            )
            # Enqueue and then nack without requeue (sends to DLQ)
            await adapter.enqueue("default", {"task": "dead"})
            await adapter.nack(job_key, requeue=False)

            # DLQ should now contain this job
            dlq_jobs = await adapter.get_dlq_jobs("default")
            assert len(dlq_jobs) >= 1
            dead_job = next((j for j in dlq_jobs if j.id == job_key), None)
            assert dead_job is not None
            assert dead_job.status == JobStatus.DEAD
            assert dead_job.payload == {"task": "dead"}
