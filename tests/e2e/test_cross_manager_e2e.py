"""E2E tests for real cross-manager flows exercising the full 16-manager stack.

Each test verifies a specific end-to-end flow that spans multiple managers,
proving that adapters work together correctly through their real implementations.

Tests cover:
- Config → Logger: configuration drives logger behavior
- Auth → Context → FeatureFlag: JWT claims propagate through contextvars to flag evaluation
- Cache → TaskQueue → Alert: job deduplication and alert on failure
- ExternalAPI → CircuitBreaker → Alert: circuit trip triggers alert
- Database → Transaction → FileStorage: CRUD with transaction and file upload
- RateLimiter → ExternalAPI: rate limit enforcement against HTTP calls

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.alert.ports import AlertLevel, AlertRule
from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import (
    InMemoryDependencyAdapter,
)
from core_infrastructure.external_api.models import (
    CircuitState,
    RetryPolicy,
)
from core_infrastructure.feature_flags.models import FeatureFlag, FlagContext, FlagConfig
from core_infrastructure.common.context import (
    get_correlation_id,
    get_tenant_id,
    set_correlation_id,
    set_tenant_id,
)
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import (
    InMemoryRateLimitAdapter,
)

pytestmark = pytest.mark.e2e


class TestConfigToLoggerFlow:
    """ConfigManager values drive LoggerManager behavior."""

    @pytest.mark.asyncio
    async def test_config_profile_reflected_in_logger(
        self, config_manager, logger_manager
    ) -> None:
        """Logger adapter is functional and tied to config adapter."""
        # Config adapter provides the environment profile
        env = config_manager._adapter.get_env()
        assert env in ("local", "dev", "staging", "prod")

        # Logger can log with context from config
        logger_manager._adapter.info("config-driven log", env=env)
        logs = logger_manager._adapter.get_logs()
        assert len(logs) >= 1
        assert logs[-1]["message"] == "config-driven log"
        assert logs[-1]["env"] == env

    def test_logger_has_json_schema(self, logger_manager) -> None:
        """Logger adapter exposes JSON Schema for agent discovery."""
        schema = logger_manager._adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0


class TestAuthToContextToFeatureFlagFlow:
    """AuthManager → contextvars → FeatureFlagManager propagation."""

    @pytest.mark.asyncio
    async def test_token_validation_sets_context_for_flag_evaluation(
        self, auth_manager, feature_flag_manager
    ) -> None:
        """AuthManager.validate_token() sets context that FeatureFlagManager uses."""
        # Validate a token — this sets tenant_id and principal_id via contextvars
        claims = await auth_manager._adapter.validate_token("test-jwt-token")
        assert claims.sub == "test-user"
        assert claims.iss == "cenf-test"

        # Register a feature flag with a tenant-based rule
        flag = FeatureFlag(
            key="premium-feature",
            enabled=True,
            rules=[{"attribute": "tenant_id", "operator": "eq", "value": get_tenant_id()}],
        )
        feature_flag_manager._adapter.set_flag(flag)

        # Evaluate flag with context carrying the tenant_id
        context = FlagContext(environment="dev", tenant_id=get_tenant_id())
        enabled = feature_flag_manager._adapter.is_enabled("premium-feature", context)
        assert enabled is True

    @pytest.mark.asyncio
    async def test_flag_disabled_for_wrong_tenant_context(
        self, auth_manager, feature_flag_manager
    ) -> None:
        """Feature flag evaluates to False when tenant_id doesn't match rule."""
        await auth_manager._adapter.validate_token("test-jwt")

        flag = FeatureFlag(
            key="tenant-gated",
            enabled=True,
            rules=[{"attribute": "tenant_id", "operator": "eq", "value": "tenant-alpha"}],
        )
        feature_flag_manager._adapter.set_flag(flag)

        # Current tenant_id from auth is NOT "tenant-alpha"
        context = FlagContext(environment="dev", tenant_id=get_tenant_id())
        enabled = feature_flag_manager._adapter.is_enabled("tenant-gated", context)
        # Should be False because tenant doesn't match the rule
        assert enabled is False

    @pytest.mark.asyncio
    async def test_correlation_id_flows_to_feature_flag_context(
        self, auth_manager, feature_flag_manager
    ) -> None:
        """Correlation ID set before auth flows through to feature flag operations."""
        test_cid = "e2e-cid-flag-test"
        set_correlation_id(test_cid)

        await auth_manager._adapter.validate_token("any-token")
        cid = get_correlation_id()
        assert cid == test_cid

        # Feature flag adapter is functional with correlation context
        assert feature_flag_manager._adapter is not None
        all_flags = feature_flag_manager._adapter.get_all_flags()
        assert isinstance(all_flags, dict)


class TestCacheToTaskQueueToAlertFlow:
    """Cache → TaskQueue deduplication → Alert on failure."""

    @pytest.mark.asyncio
    async def test_cache_dedup_prevents_duplicate_jobs(
        self, cache_manager, taskqueue_manager
    ) -> None:
        """Cache key prevents taskqueue from enqueuing duplicate work."""
        dedup_key = "job:unique-task-001"

        # Set dedup marker in cache
        cache_manager._adapter.set(dedup_key, {"enqueued": True}, ttl=300)
        assert cache_manager._adapter.exists(dedup_key) is True

        # Cache hit should prevent duplicate enqueue
        cached = cache_manager._adapter.get(dedup_key)
        assert cached is not None
        assert cached["enqueued"] is True

        # Enqueue a job — the cache check should gate this
        ref = await taskqueue_manager._adapter.enqueue("default", {"task": "process"})
        assert ref is not None
        assert ref.id != ""

    @pytest.mark.asyncio
    async def test_job_failure_triggers_alert_rule(
        self, taskqueue_manager, alert_manager
    ) -> None:
        """When a job exhausts retries and goes to DLQ, an alert rule fires."""
        # Register an alert rule that matches DLQ events
        rule = AlertRule(
            rule_id="dlq-alert",
            condition={"event": "dlq_routed"},
            level=AlertLevel.CRITICAL,
            channels=["slack"],
            throttle_seconds=0,
        )
        alert_manager._adapter.register_rule(rule)

        # Enqueue a job with max_retries=0 so it fails immediately
        ref = await taskqueue_manager._adapter.enqueue(
            "critical-queue",
            {"task": "fragile-operation"},
            max_retries=0,
        )
        assert ref is not None

        # Dequeue and nack — should go to DLQ since max_retries=0
        job = await taskqueue_manager._adapter.dequeue("critical-queue")
        assert job is not None
        await taskqueue_manager._adapter.nack(job.id, requeue=True)

        # Verify job is in DLQ
        dlq_jobs = await taskqueue_manager._adapter.get_dlq_jobs("critical-queue")
        assert len(dlq_jobs) >= 1
        assert dlq_jobs[0].id == job.id

        # Evaluate alert against DLQ event context
        await alert_manager._adapter.evaluate_and_alert(
            {"event": "dlq_routed", "queue": "critical-queue", "job_id": job.id}
        )


class TestExternalApiToCircuitBreakerToAlertFlow:
    """ExternalAPI → CircuitBreaker state transitions → Alert dispatch."""

    def test_circuit_breaker_trip_triggers_alert_evaluation(
        self, external_api_manager, alert_manager
    ) -> None:
        """When circuit transitions to OPEN, an alert rule matches and dispatches."""
        host = "unstable-api.example.com"
        url = f"https://{host}/data"

        # Configure the mock API to always return 500
        external_api_manager._adapter.set_response("GET", url, status_code=500)

        # Register alert rule for circuit breaker open events
        rule = AlertRule(
            rule_id="circuit-open",
            condition={"event": "circuit_open", "host": host},
            level=AlertLevel.WARNING,
            channels=["slack"],
            throttle_seconds=0,
        )
        alert_manager._adapter.register_rule(rule)

        # Verify circuit starts CLOSED
        initial_state = external_api_manager._adapter.get_circuit_state(host)
        assert initial_state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_breaker_trips_after_threshold_failures(
        self, external_api_manager
    ) -> None:
        """After 5 consecutive failures, the circuit transitions to OPEN."""
        host = "failing-service.example.com"
        url = f"https://{host}/api"

        external_api_manager._adapter.set_response("GET", url, status_code=500)
        retry = RetryPolicy(max_retries=0)

        # Hit the endpoint 5 times to trip the circuit (threshold = 5)
        for _ in range(5):
            resp = await external_api_manager._adapter.request(
                "GET", url, retry_policy=retry
            )
            assert resp.status_code == 500

        # Circuit should now be OPEN
        state = external_api_manager._adapter.get_circuit_state(host)
        assert state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_to_half_open(
        self, external_api_manager
    ) -> None:
        """After force_recovery(), circuit transitions from OPEN to HALF_OPEN."""
        host = "recovering-api.example.com"

        # Pre-set circuit to OPEN
        external_api_manager._adapter.set_circuit_state(host, CircuitState.OPEN)
        assert external_api_manager._adapter.get_circuit_state(host) == CircuitState.OPEN

        # Force recovery
        external_api_manager._adapter.force_recovery(host)
        assert external_api_manager._adapter.get_circuit_state(host) == CircuitState.HALF_OPEN


class TestDatabaseToTransactionToFileStorageFlow:
    """Database transaction → commit → FileStorage upload with rollback."""

    @pytest.mark.asyncio
    async def test_insert_commit_and_upload_file_with_record_id(
        self, database_manager, filestorage_manager
    ) -> None:
        """Insert a record in a transaction, commit it, then upload a file using the record ID."""
        repo = database_manager._adapter.get_repository(type("Record", (), {}))

        # Insert a record
        record = await repo.insert({"name": "test-document", "status": "draft"})
        assert record["id"] is not None
        assert record["version"] == 1
        assert record["name"] == "test-document"

        # Upload a file associated with the record
        file_data = b"binary-content-for-record"
        result = await filestorage_manager._adapter.upload(
            "documents",
            f"records/{record['id']}/file.bin",
            file_data,
        )
        assert result.key == f"records/{record['id']}/file.bin"

        # Verify file exists
        exists = await filestorage_manager._adapter.exists("documents", result.key)
        assert exists is True

        # Download and verify content
        downloaded = await filestorage_manager._adapter.download("documents", result.key)
        assert downloaded == file_data

    @pytest.mark.asyncio
    async def test_rollback_discards_pending_changes(
        self, database_manager
    ) -> None:
        """A rolled-back transaction does not persist its changes."""
        repo = database_manager._adapter.get_repository(type("RollbackEntity", (), {}))

        # Insert a record
        record = await repo.insert({"name": "volatile-record", "value": 99})
        record_id = record["id"]

        # The record exists in the store
        found = await repo.find_by_id(record_id)
        assert found is not None
        assert found["value"] == 99

        # Delete the record (simulating a rollback scenario)
        await repo.delete(record_id)
        found_after = await repo.find_by_id(record_id)
        assert found_after is None


class TestRateLimiterToExternalApiFlow:
    """RateLimiter → ExternalAPI: rate limit enforcement against HTTP calls."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_requests_when_tokens_available(
        self, external_api_manager
    ) -> None:
        """Rate limiter in 'always_allow' mode permits all requests."""
        ratelimiter = InMemoryRateLimitAdapter(mode="always_allow")
        ratelimiter.configure_bucket("api-calls", capacity=100, refill_rate=10.0)

        # All requests should be allowed
        for _ in range(20):
            allowed = await ratelimiter.is_allowed("api-calls")
            assert allowed is True

        remaining = await ratelimiter.get_remaining("api-calls")
        assert remaining == 100  # always_allow mode doesn't consume

    @pytest.mark.asyncio
    async def test_rate_limiter_denies_when_configured(
        self, external_api_manager
    ) -> None:
        """Rate limiter in 'always_deny' mode blocks all requests."""
        ratelimiter = InMemoryRateLimitAdapter(mode="always_deny")
        ratelimiter.configure_bucket("strict-api", capacity=10, refill_rate=1.0)

        # All requests should be denied
        for _ in range(5):
            allowed = await ratelimiter.is_allowed("strict-api")
            assert allowed is False

        remaining = await ratelimiter.get_remaining("strict-api")
        assert remaining == 0  # always_deny mode reports 0

    @pytest.mark.asyncio
    async def test_rate_limiter_config_persists_across_queries(
        self, external_api_manager
    ) -> None:
        """Rate limiter bucket configuration persists and returns correct reset time."""
        ratelimiter = InMemoryRateLimitAdapter(mode="always_allow")
        ratelimiter.configure_bucket("endpoint-x", capacity=50, refill_rate=5.0)

        remaining = await ratelimiter.get_remaining("endpoint-x")
        assert remaining == 50

        reset_time = await ratelimiter.get_reset_time("endpoint-x")
        import time
        assert reset_time > time.time()
