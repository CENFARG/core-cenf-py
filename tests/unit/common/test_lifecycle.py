"""Unit tests for common.lifecycle — AsyncLifecycle Protocol and HealthStatus model.

Tests cover:
- HealthStatus Pydantic model validation and is_healthy() logic
- AsyncLifecycle runtime-checkable Protocol contract
- LifecycleManager aggregation of multiple lifecycle objects
- Idempotent start/stop and health() error safety

Author: CENF AI Team
Version: 0.1.0
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.common.lifecycle import AsyncLifecycle, HealthStatus, LifecycleManager


class TestHealthStatus:
    """Verify HealthStatus Pydantic model."""

    def test_minimal_construction(self) -> None:
        """HealthStatus can be created with just the service name."""
        hs = HealthStatus(service="test-svc")
        assert hs.service == "test-svc"
        assert hs.status == "healthy"  # default

    def test_all_fields_accessible(self) -> None:
        """All HealthStatus fields are accessible as attributes."""
        now = datetime.now(UTC)
        hs = HealthStatus(
            service="auth-manager",
            status="degraded",
            version="1.2.3",
            timestamp=now,
            details={"reason": "high_latency"},
        )
        assert hs.service == "auth-manager"
        assert hs.status == "degraded"
        assert hs.version == "1.2.3"
        assert hs.timestamp == now
        assert hs.details == {"reason": "high_latency"}

    def test_default_version_matches_pattern(self) -> None:
        """Default version is '0.1.0' which matches semver pattern."""
        hs = HealthStatus(service="test")
        assert hs.version == "0.1.0"

    def test_default_timestamp_is_utc(self) -> None:
        """Default timestamp is timezone-aware UTC."""
        hs = HealthStatus(service="test")
        assert hs.timestamp.tzinfo is not None
        assert hs.timestamp.tzinfo == UTC

    def test_default_details_is_empty_dict(self) -> None:
        """details defaults to empty dict."""
        hs = HealthStatus(service="test")
        assert hs.details == {}

    def test_default_status_is_healthy(self) -> None:
        """Default status is 'healthy'."""
        hs = HealthStatus(service="test")
        assert hs.status == "healthy"

    def test_empty_service_name_fails(self) -> None:
        """service field with min_length=1 rejects empty string."""
        with pytest.raises(PydanticValidationError):
            HealthStatus(service="")

    def test_service_name_exceeds_128_chars_fails(self) -> None:
        """service field with max_length=128 rejects > 128 chars."""
        with pytest.raises(PydanticValidationError):
            HealthStatus(service="x" * 129)

    def test_invalid_status_value_fails(self) -> None:
        """status must be 'healthy', 'degraded', or 'unhealthy'."""
        with pytest.raises(PydanticValidationError):
            HealthStatus(service="test", status="broken")  # type: ignore[arg-type]

    def test_accepts_healthy_status(self) -> None:
        """'healthy' is a valid status."""
        hs = HealthStatus(service="test", status="healthy")
        assert hs.status == "healthy"

    def test_accepts_degraded_status(self) -> None:
        """'degraded' is a valid status."""
        hs = HealthStatus(service="test", status="degraded")
        assert hs.status == "degraded"

    def test_accepts_unhealthy_status(self) -> None:
        """'unhealthy' is a valid status."""
        hs = HealthStatus(service="test", status="unhealthy")
        assert hs.status == "unhealthy"

    def test_invalid_version_pattern_fails(self) -> None:
        """version must match semver pattern X.Y.Z."""
        with pytest.raises(PydanticValidationError):
            HealthStatus(service="test", version="not-a-version")


class TestHealthStatusIsHealthy:
    """Verify is_healthy() method logic."""

    def test_healthy_returns_true(self) -> None:
        """is_healthy() returns True when status == 'healthy'."""
        assert HealthStatus(service="s", status="healthy").is_healthy() is True

    def test_degraded_returns_false(self) -> None:
        """is_healthy() returns False when status == 'degraded'."""
        assert HealthStatus(service="s", status="degraded").is_healthy() is False

    def test_unhealthy_returns_false(self) -> None:
        """is_healthy() returns False when status == 'unhealthy'."""
        assert HealthStatus(service="s", status="unhealthy").is_healthy() is False


class TestAsyncLifecycleProtocol:
    """Verify AsyncLifecycle Protocol contract."""

    def test_protocol_exists_and_is_importable(self) -> None:
        """AsyncLifecycle Protocol is importable from common.lifecycle."""
        assert AsyncLifecycle is not None

    def test_protocol_is_runtime_checkable(self) -> None:
        """AsyncLifecycle is decorated with @runtime_checkable."""
        # A runtime_checkable protocol allows isinstance checks at runtime.
        assert hasattr(AsyncLifecycle, "__protocol_attrs__") or hasattr(
            AsyncLifecycle, "_is_runtime_protocol"
        )

    def test_protocol_requires_start_method(self) -> None:
        """AsyncLifecycle requires an async start() method."""
        assert hasattr(AsyncLifecycle, "start")

    def test_protocol_requires_stop_method(self) -> None:
        """AsyncLifecycle requires an async stop() method."""
        assert hasattr(AsyncLifecycle, "stop")

    def test_protocol_requires_health_method(self) -> None:
        """AsyncLifecycle requires an async health() -> HealthStatus method."""
        assert hasattr(AsyncLifecycle, "health")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing start/stop/health satisfies AsyncLifecycle."""

        class ValidService:
            async def start(self) -> None: ...
            async def stop(self) -> None: ...
            async def health(self) -> HealthStatus: ...

        assert isinstance(ValidService(), AsyncLifecycle)

    def test_class_missing_start_fails_protocol(self) -> None:
        """A class without start() does NOT satisfy AsyncLifecycle."""

        class IncompleteService:
            async def stop(self) -> None: ...
            async def health(self) -> HealthStatus: ...

        assert not isinstance(IncompleteService(), AsyncLifecycle)

    def test_class_missing_health_fails_protocol(self) -> None:
        """A class without health() does NOT satisfy AsyncLifecycle."""

        class IncompleteService:
            async def start(self) -> None: ...
            async def stop(self) -> None: ...

        assert not isinstance(IncompleteService(), AsyncLifecycle)


class TestLifecycleManager:
    """Verify LifecycleManager aggregator behavior."""

    @pytest.mark.asyncio
    async def test_health_all_reports_each_service(self) -> None:
        """health_all() returns a dict with one entry per registered service."""

        class ServiceA:
            def __init__(self, name: str) -> None:
                self._name = name

            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

            async def health(self) -> HealthStatus:
                return HealthStatus(service=self._name)

        mgr = LifecycleManager()
        mgr.register(ServiceA("svc-a"))
        mgr.register(ServiceA("svc-b"))

        result = await mgr.health_all()
        assert "svc-a" in result
        assert "svc-b" in result
        assert result["svc-a"].status == "healthy"
        assert result["svc-b"].status == "healthy"

    @pytest.mark.asyncio
    async def test_is_system_healthy_all_healthy(self) -> None:
        """is_system_healthy() returns True when all services are healthy."""

        class HealthySvc:
            async def start(self) -> None: ...
            async def stop(self) -> None: ...
            async def health(self) -> HealthStatus:
                return HealthStatus(service="h", status="healthy")

        mgr = LifecycleManager()
        mgr.register(HealthySvc())
        assert await mgr.is_system_healthy() is True

    @pytest.mark.asyncio
    async def test_is_system_healthy_one_degraded(self) -> None:
        """is_system_healthy() returns False when ANY service is degraded."""

        class HealthySvc:
            async def start(self) -> None: ...
            async def stop(self) -> None: ...
            async def health(self) -> HealthStatus:
                return HealthStatus(service="h", status="healthy")

        class DegradedSvc:
            async def start(self) -> None: ...
            async def stop(self) -> None: ...
            async def health(self) -> HealthStatus:
                return HealthStatus(service="d", status="degraded")

        mgr = LifecycleManager()
        mgr.register(HealthySvc())
        mgr.register(DegradedSvc())
        assert await mgr.is_system_healthy() is False

    @pytest.mark.asyncio
    async def test_is_system_healthy_one_unhealthy(self) -> None:
        """is_system_healthy() returns False when ANY service is unhealthy."""

        class UnhealthySvc:
            async def start(self) -> None: ...
            async def stop(self) -> None: ...
            async def health(self) -> HealthStatus:
                return HealthStatus(service="u", status="unhealthy")

        mgr = LifecycleManager()
        mgr.register(UnhealthySvc())
        assert await mgr.is_system_healthy() is False

    @pytest.mark.asyncio
    async def test_health_never_raises_on_error(self) -> None:
        """LifecycleManager.health_all() never raises even if a service's health() raises."""

        class FaultySvc:
            async def start(self) -> None: ...
            async def stop(self) -> None: ...

            async def health(self) -> HealthStatus:
                raise RuntimeError("health check failed")

        mgr = LifecycleManager()
        mgr.register(FaultySvc())
        # Should NOT raise
        result = await mgr.health_all()
        assert len(result) == 1
        # Faulty service should report unhealthy/degraded
        svc_result = next(iter(result.values()))
        assert svc_result.status in ("degraded", "unhealthy")

    @pytest.mark.asyncio
    async def test_empty_manager_health_all(self) -> None:
        """health_all() on an empty manager returns empty dict."""
        mgr = LifecycleManager()
        result = await mgr.health_all()
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_manager_is_system_healthy(self) -> None:
        """is_system_healthy() on an empty manager returns True."""
        mgr = LifecycleManager()
        assert await mgr.is_system_healthy() is True
