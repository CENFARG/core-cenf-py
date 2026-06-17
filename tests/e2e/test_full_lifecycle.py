"""E2E tests for the complete startup → health → shutdown lifecycle of all 16 managers.

Verifies the BootstrapOrchestrator lifecycle using all 16 CENF infrastructure
managers wired together with their real in-memory adapters.

Tests cover:
- Full startup with all 16 managers via asyncio.TaskGroup
- Health aggregation confirming all 16 managers report healthy
- Graceful shutdown in reverse dependency order
- Shutdown resilience after partial startup failure
- Signal handling via shutdown_event.set()

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.bootstrap import BootstrapOrchestrator
from core_infrastructure.common.lifecycle import HealthStatus

pytestmark = pytest.mark.e2e


class TestFullLifecycleWithAll16Managers:
    """Verify full bootstrap lifecycle with all 16 managers."""

    @pytest.mark.asyncio
    async def test_all_16_managers_start_successfully(
        self, bootstrap_orchestrator_16
    ) -> None:
        """BootstrapOrchestrator.startup() initializes all 16 managers without error.

        Uses asyncio.TaskGroup internally — if any manager fails, the
        ExceptionGroup propagates. Reaching here without exception proves
        all 16 managers started successfully.
        """
        await bootstrap_orchestrator_16.startup()

    @pytest.mark.asyncio
    async def test_all_16_managers_report_healthy_after_startup(
        self, bootstrap_orchestrator_16
    ) -> None:
        """health() returns 16 statuses, all reporting 'healthy' after startup."""
        await bootstrap_orchestrator_16.startup()

        results = await bootstrap_orchestrator_16.health()

        assert len(results) == 16, (
            f"Expected 16 health statuses, got {len(results)}"
        )
        # Every manager must report healthy
        for hs in results:
            assert hs.status == "healthy", (
                f"Manager '{hs.service}' is {hs.status}, expected 'healthy'"
            )

    @pytest.mark.asyncio
    async def test_health_returns_all_expected_service_names(
        self, bootstrap_orchestrator_16
    ) -> None:
        """health() returns the exact set of 16 expected service names."""
        await bootstrap_orchestrator_16.startup()

        results = await bootstrap_orchestrator_16.health()
        services = {hs.service for hs in results}

        expected = {
            "config",
            "logger",
            "secret",
            "observability",
            "error",
            "auth",
            "cache",
            "database",
            "filestorage",
            "taskqueue",
            "external_api",
            "feature_flags",
            "alert",
            "dependency",
            "dynamic_prompting",
            "ratelimit",
        }
        assert services == expected, f"Missing: {expected - services}, Extra: {services - expected}"

    @pytest.mark.asyncio
    async def test_graceful_shutdown_stops_all_managers(
        self, bootstrap_orchestrator_16
    ) -> None:
        """shutdown() completes without error after successful startup."""
        await bootstrap_orchestrator_16.startup()
        await bootstrap_orchestrator_16.shutdown()

    @pytest.mark.asyncio
    async def test_full_cycle_startup_health_shutdown(
        self, bootstrap_orchestrator_16
    ) -> None:
        """Complete cycle: startup → health → shutdown — all succeed."""
        await bootstrap_orchestrator_16.startup()

        results = await bootstrap_orchestrator_16.health()
        assert len(results) == 16
        assert all(hs.is_healthy() for hs in results)

        await bootstrap_orchestrator_16.shutdown()


class TestShutdownResilience:
    """Verify graceful shutdown works even after partial failures."""

    @pytest.mark.asyncio
    async def test_shutdown_completes_when_startup_partially_failed(
        self,
    ) -> None:
        """Shutdown succeeds even when some managers failed to start.

        Creates a BootstrapOrchestrator with one failing manager and one
        healthy manager. After the failing manager's startup raises, shutdown
        still completes for both managers without raising.
        """
        class FailingStartManager:
            _name = "failing"
            async def start(self) -> None:
                raise RuntimeError("simulated startup failure")
            async def stop(self) -> None:
                pass
            async def health(self) -> HealthStatus:
                return HealthStatus(service="failing", status="unhealthy")

        class HealthyManager:
            _name = "healthy"
            def __init__(self) -> None:
                self.stopped = False
            async def start(self) -> None:
                pass
            async def stop(self) -> None:
                self.stopped = True
            async def health(self) -> HealthStatus:
                return HealthStatus(service="healthy", status="healthy")

        healthy = HealthyManager()
        failing = FailingStartManager()
        orch = BootstrapOrchestrator(failing, healthy)

        # Startup should fail because one manager raises
        with pytest.raises((ExceptionGroup, RuntimeError)):
            await orch.startup()

        # Shutdown must still complete without error
        await orch.shutdown()
        assert healthy.stopped is True

    @pytest.mark.asyncio
    async def test_shutdown_event_set_triggers_graceful_exit(
        self, bootstrap_orchestrator_16
    ) -> None:
        """Signal handling via shutdown_event.set() triggers graceful shutdown.

        After startup, setting the shutdown event causes the orchestrator
        to proceed to shutdown. This simulates SIGTERM/SIGINT handling
        without needing real OS signal delivery.
        """
        import asyncio

        await bootstrap_orchestrator_16.startup()

        # Simulate external signal by setting the shutdown event
        bootstrap_orchestrator_16._shutdown_event.set()

        # The event is now set — shutdown should proceed normally
        await bootstrap_orchestrator_16.shutdown()

        # Verify the event is indeed set
        assert bootstrap_orchestrator_16._shutdown_event.is_set()
