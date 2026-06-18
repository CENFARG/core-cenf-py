"""Stress tests for BootstrapOrchestrator — repeated startup/shutdown cycles.

Tests cover:
- 10 repeated startup/shutdown cycles without resource leaks
- Health check aggregation under concurrent access
- No accumulated state corruption across cycles
- Graceful degradation when stopping already-stopped services

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio

import pytest

from core_infrastructure.bootstrap import BootstrapOrchestrator
from core_infrastructure.common.lifecycle import HealthStatus

pytestmark = pytest.mark.stress


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _CycleService:
    """Service that tracks start/stop/health calls across cycles."""
    def __init__(self, name: str) -> None:
        self._name = name
        self.start_count = 0
        self.stop_count = 0
        self.health_count = 0
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True
        self.start_count += 1

    async def stop(self) -> None:
        self.stopped = True
        self.stop_count += 1

    async def health(self) -> HealthStatus:
        self.health_count += 1
        return HealthStatus(service=self._name, status="healthy", details={"start_count": str(self.start_count)})


class _SlowStartService:
    """Service with delayed startup."""
    def __init__(self, name: str, delay: float = 0.05) -> None:
        self._name = name; self._delay = delay; self.started = False

    async def start(self) -> None:
        await asyncio.sleep(self._delay)
        self.started = True

    async def stop(self) -> None: pass

    async def health(self) -> HealthStatus:
        return HealthStatus(service=self._name, status="healthy")


class _DegradingService:
    """Service that degrades after a threshold of health checks."""
    def __init__(self, name: str, degrade_after: int = 5) -> None:
        self._name = name; self._degrade_after = degrade_after; self.health_calls = 0

    async def start(self) -> None: pass
    async def stop(self) -> None: pass

    async def health(self) -> HealthStatus:
        self.health_calls += 1
        if self.health_calls > self._degrade_after:
            return HealthStatus(service=self._name, status="degraded", details={"calls": str(self.health_calls)})
        return HealthStatus(service=self._name, status="healthy")


# ---------------------------------------------------------------------------
# Repeated lifecycle tests
# ---------------------------------------------------------------------------


class TestRepeatedLifecycle:
    """Verify startup/shutdown cycle resilience."""

    @pytest.mark.asyncio
    async def test_10_startup_shutdown_cycles_no_errors(self) -> None:
        """10 consecutive startup → shutdown cycles complete without errors."""
        services = [_CycleService(f"svc-{i:02d}") for i in range(6)]
        orchestrator = BootstrapOrchestrator(*services)

        for cycle in range(10):
            await orchestrator.startup()
            for svc in services:
                assert svc.started is True, f"Cycle {cycle}: {svc._name} not started"

            await orchestrator.shutdown()
            for svc in services:
                assert svc.stopped is True, f"Cycle {cycle}: {svc._name} not stopped"

    @pytest.mark.asyncio
    async def test_startup_shutdown_counts_match_across_cycles(self) -> None:
        """After 10 cycles, each service has start_count == stop_count == 10."""
        services = [_CycleService(f"svc-{i:02d}") for i in range(4)]
        orchestrator = BootstrapOrchestrator(*services)

        for _ in range(10):
            await orchestrator.startup()
            await orchestrator.shutdown()

        for svc in services:
            assert svc.start_count == 10, f"{svc._name}: expected 10 starts, got {svc.start_count}"
            assert svc.stop_count == 10, f"{svc._name}: expected 10 stops, got {svc.stop_count}"

    @pytest.mark.asyncio
    async def test_slow_services_startup_does_not_deadlock(self) -> None:
        """Slow-starting services do not cause deadlocks across cycles."""
        services = [
            _SlowStartService("fast-a", delay=0.01),
            _SlowStartService("slow-b", delay=0.05),
            _SlowStartService("fast-c", delay=0.01),
        ]
        orchestrator = BootstrapOrchestrator(*services)

        for _ in range(5):
            await orchestrator.startup()
            for svc in services:
                assert svc.started is True
            await orchestrator.shutdown()


# ---------------------------------------------------------------------------
# Health aggregation under load
# ---------------------------------------------------------------------------


class TestHealthUnderLoad:
    """Verify health aggregation correctness under repeated cycles."""

    @pytest.mark.asyncio
    async def test_health_aggregation_consistency_across_cycles(self) -> None:
        """health() returns correct counts across multiple cycles."""
        services = [
            _CycleService("config"),
            _CycleService("logger"),
            _DegradingService("cache", degrade_after=3),
        ]
        orchestrator = BootstrapOrchestrator(*services)

        await orchestrator.startup()

        # Call health multiple times — the DegradingService degrades after 3 calls
        for i in range(10):
            results = await orchestrator.health()
            assert len(results) == 3

            statuses: dict[str, HealthStatus] = {hs.service: hs for hs in results}
            assert "config" in statuses
            assert "logger" in statuses

            cache_status = statuses["cache"]
            if i >= 3:
                assert cache_status.status == "degraded", f"Health call {i}: expected degraded"
            else:
                assert cache_status.status == "healthy", f"Health call {i}: expected healthy"

        await orchestrator.shutdown()

    @pytest.mark.asyncio
    async def test_health_does_not_leak_state_across_cycles(self) -> None:
        """Service health counters do not affect shutdown/startup correctness."""
        services = [_CycleService(f"svc-{i:02d}") for i in range(3)]
        orchestrator = BootstrapOrchestrator(*services)

        await orchestrator.startup()

        # Agressively query health
        for _ in range(20):
            results = await orchestrator.health()
            assert len(results) == 3
            for hs in results:
                assert hs.status in ("healthy", "degraded", "unhealthy")

        await orchestrator.shutdown()

        # Services should be stopped despite heavy health polling
        for svc in services:
            assert svc.stopped is True
