"""Integration tests for BootstrapOrchestrator lifecycle.

Uses the integration conftest fixtures (all 12 managers wired together)
to verify the full startup → health → shutdown lifecycle.

Tests cover:
- Full startup with all 12 managers via TaskGroup
- Health check aggregation with all 12 managers
- Graceful shutdown with all 12 managers
- Startup failure propagation (simulated)

Author: CENF AI Team
Version: 0.1.0
"""

import pytest


class TestBootstrapFullLifecycle:
    """Verify full bootstrap lifecycle with all 12 managers."""

    @pytest.mark.asyncio
    async def test_full_startup_with_all_managers(self, bootstrap_orchestrator) -> None:
        """BootstrapOrchestrator.startup() initializes all 12 managers without error."""
        await bootstrap_orchestrator.startup()
        # Should reach here without exception
        assert True

    @pytest.mark.asyncio
    async def test_health_after_startup_aggregates_all(self, bootstrap_orchestrator) -> None:
        """health() returns 12 statuses after startup completes."""
        await bootstrap_orchestrator.startup()

        results = await bootstrap_orchestrator.health()

        assert len(results) == 12
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
        }
        assert services == expected, f"Missing services: {expected - services}"

    @pytest.mark.asyncio
    async def test_all_managers_healthy_after_startup(self, bootstrap_orchestrator) -> None:
        """All managers report healthy after successful startup."""
        await bootstrap_orchestrator.startup()

        results = await bootstrap_orchestrator.health()

        for hs in results:
            assert hs.status == "healthy", f"Manager '{hs.service}' is {hs.status}"

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_all_managers(self, bootstrap_orchestrator) -> None:
        """BootstrapOrchestrator.shutdown() stops all 12 managers without error."""
        await bootstrap_orchestrator.startup()
        await bootstrap_orchestrator.shutdown()
        # Should reach here without exception
        assert True

    @pytest.mark.asyncio
    async def test_startup_then_shutdown_complete_cycle(self, bootstrap_orchestrator) -> None:
        """Startup → health → shutdown completes the full lifecycle."""
        await bootstrap_orchestrator.startup()

        # Health check mid-lifecycle
        results = await bootstrap_orchestrator.health()
        assert len(results) == 12
        for hs in results:
            assert hs.status == "healthy"

        await bootstrap_orchestrator.shutdown()


class TestStartupFailurePropagation:
    """Verify that startup failures propagate correctly."""

    @pytest.mark.asyncio
    async def test_failing_startup_raises_exception_group(self, bootstrap_orchestrator) -> None:
        """When a manager fails to start, the error propagates as an ExceptionGroup.

        Note: This test verifies the exception propagation mechanism.
        All our integration fixtures are healthy, so we test the pattern
        by injecting a failing service into a fresh orchestrator.
        """
        from core_infrastructure.bootstrap import BootstrapOrchestrator
        from core_infrastructure.common.lifecycle import HealthStatus

        class FailingStartService:
            async def start(self) -> None:
                raise RuntimeError("simulated startup failure")

            async def stop(self) -> None:
                pass

            async def health(self) -> HealthStatus:
                return HealthStatus(service="failing", status="healthy")

        orch = BootstrapOrchestrator(FailingStartService())

        with pytest.raises((ExceptionGroup, RuntimeError)) as exc_info:
            await orch.startup()

        # ExceptionGroup wraps the original error
        if isinstance(exc_info.value, ExceptionGroup):
            assert any("simulated startup failure" in str(e) for e in exc_info.value.exceptions)
        else:
            assert "simulated startup failure" in str(exc_info.value)
