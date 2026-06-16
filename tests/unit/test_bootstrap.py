"""Unit tests for BootstrapOrchestrator — startup, shutdown, health aggregation.

Tests cover:
- Startup initializes managers in dependency order via asyncio.TaskGroup
- Shutdown stops managers in REVERSE order (best-effort, errors logged)
- Health aggregation across all managers
- Startup failure propagation (TaskGroup cancels others)
- Shutdown continues despite individual errors
- Health handles per-manager failures gracefully

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.bootstrap import BootstrapOrchestrator
from core_infrastructure.common.lifecycle import HealthStatus

# ---------------------------------------------------------------------------
# Test doubles — record start/stop order and simulate failures
# ---------------------------------------------------------------------------


class _RecordingService:
    """Test double that records when start() and stop() are called.

    Implements AsyncLifecycle Protocol so it can be passed to
    BootstrapOrchestrator. Records call order in module-level lists
    for assertion after the orchestration completes.
    """

    def __init__(self, name: str, *, fail_start: bool = False, fail_stop: bool = False) -> None:
        self._name = name
        self._fail_start = fail_start
        self._fail_stop = fail_stop
        self.started = False
        self.stopped = False
        self.start_order: list[str] = []
        self.stop_order: list[str] = []

    async def start(self) -> None:
        if self._fail_start:
            raise RuntimeError(f"{self._name} start failure")
        self.started = True
        self.start_order.append(self._name)

    async def stop(self) -> None:
        if self._fail_stop:
            raise RuntimeError(f"{self._name} stop failure")
        self.stopped = True
        self.stop_order.append(self._name)

    async def health(self) -> HealthStatus:
        return HealthStatus(service=self._name, status="healthy")


class _FailingHealthService:
    """Test double whose health() raises an exception.

    Used to verify that BootstrapOrchestrator.health() catches the
    exception and reports 'unhealthy' rather than propagating it.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self) -> HealthStatus:
        raise RuntimeError("health check explosion")


class _DegradedService:
    """Test double that reports degraded health."""

    def __init__(self, name: str, reason: str = "slow_response") -> None:
        self._name = name
        self._reason = reason

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self) -> HealthStatus:
        return HealthStatus(service=self._name, status="degraded", details={"reason": self._reason})


# ---------------------------------------------------------------------------
# Startup order tests
# ---------------------------------------------------------------------------


class TestStartupOrder:
    """Verify that BootstrapOrchestrator.startup() initializes managers in
    the correct dependency order using asyncio.TaskGroup."""

    @pytest.mark.asyncio
    async def test_startup_calls_start_in_registration_order(self) -> None:
        """startup() calls start() on each manager in the order they were registered."""
        svc_a = _RecordingService("config")
        svc_b = _RecordingService("logger")
        svc_c = _RecordingService("secret")

        orchestrator = BootstrapOrchestrator(svc_a, svc_b, svc_c)
        await orchestrator.startup()

        assert svc_a.started is True
        assert svc_b.started is True
        assert svc_c.started is True

    @pytest.mark.asyncio
    async def test_startup_maintains_order_with_twelve_managers(self) -> None:
        """With 12 managers, start() is called in the exact registration order."""
        services = [_RecordingService(f"svc-{i:02d}") for i in range(12)]
        orchestrator = BootstrapOrchestrator(*services)
        await orchestrator.startup()

        for i, svc in enumerate(services):
            assert svc.started is True, f"Service {i} was not started"

    @pytest.mark.asyncio
    async def test_startup_failure_cancels_remaining(self) -> None:
        """When one manager fails to start, TaskGroup cancels the others (order is irrelevant — failure propagates)."""
        svc_a = _RecordingService("config")
        svc_b = _RecordingService("logger", fail_start=True)
        svc_c = _RecordingService("secret")

        orchestrator = BootstrapOrchestrator(svc_a, svc_b, svc_c)

        with pytest.raises(ExceptionGroup) as exc_info:
            await orchestrator.startup()

        # The ExceptionGroup should contain at least one RuntimeError from svc_b
        errors = exc_info.value.exceptions
        assert any("logger start failure" in str(e) for e in errors)


# ---------------------------------------------------------------------------
# Shutdown order tests
# ---------------------------------------------------------------------------


class TestShutdownOrder:
    """Verify that BootstrapOrchestrator.shutdown() stops managers in
    REVERSE dependency order, logging errors without blocking."""

    @pytest.mark.asyncio
    async def test_shutdown_calls_stop_in_reverse_order(self) -> None:
        """shutdown() calls stop() on each manager in reverse registration order."""
        svc_a = _RecordingService("config")
        svc_b = _RecordingService("logger")
        svc_c = _RecordingService("secret")

        orchestrator = BootstrapOrchestrator(svc_a, svc_b, svc_c)
        await orchestrator.shutdown()

        # Verify each was stopped
        assert svc_a.stopped is True
        assert svc_b.stopped is True
        assert svc_c.stopped is True

    @pytest.mark.asyncio
    async def test_shutdown_reverses_order_with_twelve_managers(self) -> None:
        """With 12 managers, stop() is called in exact reverse of registration order."""
        services = [_RecordingService(f"svc-{i:02d}") for i in range(12)]
        orchestrator = BootstrapOrchestrator(*services)
        await orchestrator.shutdown()

        for svc in services:
            assert svc.stopped is True, f"Service {svc._name} was not stopped"

    @pytest.mark.asyncio
    async def test_shutdown_continues_despite_individual_errors(self) -> None:
        """When one manager fails during shutdown, remaining managers are still stopped."""
        svc_a = _RecordingService("config")
        svc_b = _RecordingService("logger", fail_stop=True)
        svc_c = _RecordingService("secret")

        orchestrator = BootstrapOrchestrator(svc_a, svc_b, svc_c)
        # Should NOT raise — errors are logged, not propagated
        await orchestrator.shutdown()

        # svc_a and svc_c should still have been stopped
        assert svc_a.stopped is True
        assert svc_c.stopped is True
        # svc_b attempted stop but failed
        assert svc_b.stopped is False

    @pytest.mark.asyncio
    async def test_shutdown_handles_all_failures(self) -> None:
        """When ALL managers fail during shutdown, shutdown() still completes without raising."""
        services = [_RecordingService(f"svc-{i:02d}", fail_stop=True) for i in range(3)]
        orchestrator = BootstrapOrchestrator(*services)
        # Should NOT raise
        await orchestrator.shutdown()

        for svc in services:
            assert svc.stopped is False  # All failed


# ---------------------------------------------------------------------------
# Health aggregation tests
# ---------------------------------------------------------------------------


class TestHealthAggregation:
    """Verify that BootstrapOrchestrator.health() aggregates health status
    across all registered managers."""

    @pytest.mark.asyncio
    async def test_health_aggregates_all_managers(self) -> None:
        """health() returns a list of HealthStatus, one per manager."""
        svc_a = _RecordingService("config")
        svc_b = _RecordingService("logger")
        svc_c = _RecordingService("secret")

        orchestrator = BootstrapOrchestrator(svc_a, svc_b, svc_c)
        result = await orchestrator.health()

        assert len(result) == 3
        names = {hs.service for hs in result}
        assert names == {"config", "logger", "secret"}
        for hs in result:
            assert hs.status == "healthy"

    @pytest.mark.asyncio
    async def test_health_reports_degraded_status(self) -> None:
        """health() correctly reports degraded status from a manager."""
        svc_ok = _RecordingService("config")
        svc_degraded = _DegradedService("logger", reason="high_latency")

        orchestrator = BootstrapOrchestrator(svc_ok, svc_degraded)
        result = await orchestrator.health()

        statuses: dict[str, HealthStatus] = {hs.service: hs for hs in result}
        assert statuses["config"].status == "healthy"
        assert statuses["logger"].status == "degraded"
        assert statuses["logger"].details == {"reason": "high_latency"}

    @pytest.mark.asyncio
    async def test_health_handles_failing_manager_gracefully(self) -> None:
        """When a manager's health() raises, it is reported as 'unhealthy' rather than crashing."""
        svc_ok = _RecordingService("config")
        svc_bad = _FailingHealthService("broken-svc")

        orchestrator = BootstrapOrchestrator(svc_ok, svc_bad)
        result = await orchestrator.health()

        statuses: dict[str, HealthStatus] = {hs.service: hs for hs in result}
        assert statuses["config"].status == "healthy"
        assert statuses["broken-svc"].status == "unhealthy"
        assert "error" in statuses["broken-svc"].details

    @pytest.mark.asyncio
    async def test_health_empty_managers_returns_empty(self) -> None:
        """health() on an orchestrator with no managers returns an empty list."""
        orchestrator = BootstrapOrchestrator()
        result = await orchestrator.health()
        assert result == []


# ---------------------------------------------------------------------------
# Full lifecycle tests
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """Verify the complete startup → health → shutdown flow."""

    @pytest.mark.asyncio
    async def test_startup_then_shutdown_works(self) -> None:
        """After startup(), all managers are started; after shutdown(), all are stopped."""
        svc_a = _RecordingService("config")
        svc_b = _RecordingService("logger")

        orchestrator = BootstrapOrchestrator(svc_a, svc_b)
        await orchestrator.startup()
        assert svc_a.started is True
        assert svc_b.started is True

        await orchestrator.shutdown()
        assert svc_a.stopped is True
        assert svc_b.stopped is True

    @pytest.mark.asyncio
    async def test_health_after_startup_reflects_live_managers(self) -> None:
        """health() after startup() reflects the actual manager states."""
        svc_a = _RecordingService("config")
        svc_b = _DegradedService("logger")

        orchestrator = BootstrapOrchestrator(svc_a, svc_b)
        await orchestrator.startup()

        result = await orchestrator.health()
        statuses: dict[str, HealthStatus] = {hs.service: hs for hs in result}
        assert statuses["config"].status == "healthy"
        assert statuses["logger"].status == "degraded"
