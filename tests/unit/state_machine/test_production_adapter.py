"""Unit tests for ProductionStateMachineAdapter.

Tests cover:
- Production adapter logs transitions via LoggerManager
- Metrics emitted via ObservabilityManager
- Error strategy rollback works
- Async handlers supported

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.state_machine.adapters.production_state_machine_adapter import (
    ProductionStateMachineAdapter,
)
from core_infrastructure.state_machine.models import (
    StateDefinition,
    StateMachineConfig,
    TransitionRule,
)


def _build_production_machine(
    logger: InMemoryLoggerAdapter,
    obs: InMemoryObservabilityAdapter,
    on_error: str = "stop",
) -> ProductionStateMachineAdapter[str, dict[str, str]]:
    """Build a 3-state production machine: A -> B -> C."""
    config = StateMachineConfig(
        initial_state="A",
        max_iterations=10,
        strict_mode=True,
        on_error_strategy=on_error,  # type: ignore[arg-type]
    )
    sm: ProductionStateMachineAdapter[str, dict[str, str]] = (
        ProductionStateMachineAdapter(config, logger, obs)
    )
    sm.register_state("A", StateDefinition(name="A"))
    sm.register_state("B", StateDefinition(name="B"))
    sm.register_state("C", StateDefinition(name="C"))
    sm.register_transition(TransitionRule(from_state="A", to_state="B"))
    sm.register_transition(TransitionRule(from_state="B", to_state="C"))
    sm.register_handler("A", lambda ctx: "B")
    sm.register_handler("B", lambda ctx: "C")
    return sm


class TestProductionLogging:
    """Verify production adapter logs transitions."""

    @pytest.mark.asyncio
    async def test_transitions_logged(
        self,
        logger: InMemoryLoggerAdapter,
        observability: InMemoryObservabilityAdapter,
    ) -> None:
        """Production adapter logs each transition at INFO level."""
        sm = _build_production_machine(logger, observability)
        await sm.run({})
        logs = logger.get_logs()
        messages = [log["message"] for log in logs]
        assert "state_machine.started" in messages
        assert "state_machine.transition" in messages
        assert "state_machine.terminated" in messages

    @pytest.mark.asyncio
    async def test_transition_log_contains_states(
        self,
        logger: InMemoryLoggerAdapter,
        observability: InMemoryObservabilityAdapter,
    ) -> None:
        """Transition logs contain from_state and to_state."""
        sm = _build_production_machine(logger, observability)
        await sm.run({})
        transition_logs = [
            log for log in logger.get_logs()
            if log["message"] == "state_machine.transition"
        ]
        assert len(transition_logs) == 2
        assert transition_logs[0]["from_state"] == "A"
        assert transition_logs[0]["to_state"] == "B"


class TestProductionMetrics:
    """Verify production adapter emits metrics."""

    @pytest.mark.asyncio
    async def test_transition_counter_emitted(
        self,
        logger: InMemoryLoggerAdapter,
        observability: InMemoryObservabilityAdapter,
    ) -> None:
        """Transition counter is emitted for each transition."""
        sm = _build_production_machine(logger, observability)
        await sm.run({})
        counters = [
            m for m in observability.get_metrics()
            if m["name"] == "cenf.state_machine.transitions_total"
        ]
        assert len(counters) == 2

    @pytest.mark.asyncio
    async def test_duration_histogram_emitted(
        self,
        logger: InMemoryLoggerAdapter,
        observability: InMemoryObservabilityAdapter,
    ) -> None:
        """Duration histogram is emitted per handler execution."""
        sm = _build_production_machine(logger, observability)
        await sm.run({})
        histograms = [
            m for m in observability.get_metrics()
            if m["name"] == "cenf.state_machine.transition_duration_ms"
        ]
        assert len(histograms) == 2

    @pytest.mark.asyncio
    async def test_error_counter_on_failure(
        self,
        logger: InMemoryLoggerAdapter,
        observability: InMemoryObservabilityAdapter,
    ) -> None:
        """Error counter emitted when handler raises."""
        sm = _build_production_machine(logger, observability, on_error="stop")

        def bad(ctx: dict[str, str]) -> str:
            raise RuntimeError("boom")

        sm.register_handler("A", bad)  # type: ignore[arg-type]
        await sm.run({})
        error_counters = [
            m for m in observability.get_metrics()
            if m["name"] == "cenf.state_machine.errors_total"
        ]
        assert len(error_counters) == 1


class TestProductionErrorStrategy:
    """Verify error strategies in production adapter."""

    @pytest.mark.asyncio
    async def test_rollback_strategy(
        self,
        logger: InMemoryLoggerAdapter,
        observability: InMemoryObservabilityAdapter,
    ) -> None:
        """Rollback strategy reverts to previous state on error."""
        sm = _build_production_machine(logger, observability, on_error="rollback")
        call_count = 0

        def flaky_b(ctx: dict[str, str]) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient")
            return "C"

        sm.register_handler("B", flaky_b)  # type: ignore[arg-type]
        status = await sm.run({})
        assert status.is_terminated is True


class TestProductionAsyncHandlers:
    """Verify production adapter supports async handlers."""

    @pytest.mark.asyncio
    async def test_async_handler_supported(
        self,
        logger: InMemoryLoggerAdapter,
        observability: InMemoryObservabilityAdapter,
    ) -> None:
        """Async handlers are awaited correctly."""
        sm = _build_production_machine(logger, observability)

        async def async_a(ctx: dict[str, str]) -> str:
            return "B"

        async def async_b(ctx: dict[str, str]) -> str:
            return "C"

        sm.register_handler("A", async_a)  # type: ignore[arg-type]
        sm.register_handler("B", async_b)  # type: ignore[arg-type]
        status = await sm.run({})
        assert status.current_state == "C"
        assert status.transition_count == 2
        assert status.errors == []
