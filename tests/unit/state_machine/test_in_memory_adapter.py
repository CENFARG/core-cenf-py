"""Unit tests for InMemoryStateMachineAdapter.

Tests cover:
- register + get_handler roundtrip
- register + validate transition (valid and invalid)
- run() happy path (A -> B -> C)
- run() invalid transition -> error state
- run() max_iterations guard
- lifecycle hooks (on_enter, on_exit, on_error)
- reset() clears state
- get_status() during and after run

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.state_machine.adapters.in_memory_state_machine_adapter import (
    InMemoryStateMachineAdapter,
)
from core_infrastructure.state_machine.models import (
    StateDefinition,
    StateMachineConfig,
    TransitionRule,
)


def _build_abc_machine(
    strict: bool = True,
    on_error: str = "stop",
    max_iter: int = 10,
) -> InMemoryStateMachineAdapter[str, dict[str, str]]:
    """Build a 3-state machine: A -> B -> C (terminal)."""
    config = StateMachineConfig(
        initial_state="A",
        max_iterations=max_iter,
        strict_mode=strict,
        on_error_strategy=on_error,  # type: ignore[arg-type]
    )
    sm: InMemoryStateMachineAdapter[str, dict[str, str]] = (
        InMemoryStateMachineAdapter(config)
    )
    sm.register_state("A", StateDefinition(name="A"))
    sm.register_state("B", StateDefinition(name="B"))
    sm.register_state("C", StateDefinition(name="C"))
    sm.register_transition(TransitionRule(from_state="A", to_state="B"))
    sm.register_transition(TransitionRule(from_state="B", to_state="C"))
    sm.register_handler("A", lambda ctx: "B")
    sm.register_handler("B", lambda ctx: "C")
    return sm


class TestRegisterAndGet:
    """Verify registration and retrieval roundtrips."""

    def test_register_and_get_handler(
        self, sm_adapter: InMemoryStateMachineAdapter[str, dict[str, str]]
    ) -> None:
        """register_handler + get_handler roundtrip."""
        handler = lambda ctx: "next"  # noqa: E731
        sm_adapter.register_handler("A", handler)
        assert sm_adapter.get_handler("A") is handler

    def test_get_handler_returns_none_for_unknown(
        self, sm_adapter: InMemoryStateMachineAdapter[str, dict[str, str]]
    ) -> None:
        """get_handler returns None for unregistered state."""
        assert sm_adapter.get_handler("unknown") is None

    def test_validate_transition_valid(
        self, sm_adapter: InMemoryStateMachineAdapter[str, dict[str, str]]
    ) -> None:
        """validate_transition passes for registered transitions."""
        sm_adapter.register_transition(TransitionRule(from_state="A", to_state="B"))
        sm_adapter.validate_transition("A", "B")  # Should not raise

    def test_validate_transition_invalid(
        self, sm_adapter: InMemoryStateMachineAdapter[str, dict[str, str]]
    ) -> None:
        """validate_transition raises ValidationError for unknown transitions."""
        with pytest.raises(ValidationError):
            sm_adapter.validate_transition("A", "Z")

    def test_is_valid_transition(
        self, sm_adapter: InMemoryStateMachineAdapter[str, dict[str, str]]
    ) -> None:
        """is_valid_transition returns True/False correctly."""
        sm_adapter.register_transition(TransitionRule(from_state="A", to_state="B"))
        assert sm_adapter.is_valid_transition("A", "B") is True
        assert sm_adapter.is_valid_transition("A", "Z") is False

    def test_get_valid_transitions(
        self, sm_adapter: InMemoryStateMachineAdapter[str, dict[str, str]]
    ) -> None:
        """get_valid_transitions returns all rules from a state."""
        r1 = TransitionRule(from_state="A", to_state="B")
        r2 = TransitionRule(from_state="A", to_state="C")
        sm_adapter.register_transition(r1)
        sm_adapter.register_transition(r2)
        rules = sm_adapter.get_valid_transitions("A")
        assert len(rules) == 2


class TestRunHappyPath:
    """Verify run() executes the state machine loop correctly."""

    @pytest.mark.asyncio
    async def test_abc_happy_path(self) -> None:
        """run() traverses A -> B -> C and terminates."""
        sm = _build_abc_machine()
        status = await sm.run({})
        assert status.current_state == "C"
        assert status.transition_count == 2
        assert status.is_terminated is True
        assert status.is_running is False
        assert status.errors == []

    @pytest.mark.asyncio
    async def test_events_recorded(self) -> None:
        """run() records TransitionEvent for each transition."""
        sm = _build_abc_machine()
        await sm.run({})
        events = sm.get_events()
        assert len(events) == 2
        assert events[0].from_state == "A"
        assert events[0].to_state == "B"
        assert events[0].success is True
        assert events[1].from_state == "B"
        assert events[1].to_state == "C"

    @pytest.mark.asyncio
    async def test_start_state_override(self) -> None:
        """run() respects start_state override."""
        sm = _build_abc_machine()
        status = await sm.run({}, start_state="B")
        assert status.current_state == "C"
        assert status.transition_count == 1


class TestRunErrorHandling:
    """Verify run() handles errors and invalid transitions."""

    @pytest.mark.asyncio
    async def test_invalid_transition_strict_raises(self) -> None:
        """strict_mode raises ValidationError on invalid transition."""
        sm = _build_abc_machine(strict=True)
        sm.register_handler("B", lambda ctx: "Z")  # Z not registered
        with pytest.raises(ValidationError):
            await sm.run({})

    @pytest.mark.asyncio
    async def test_invalid_transition_non_strict_records_error(self) -> None:
        """Non-strict mode records error and terminates."""
        sm = _build_abc_machine(strict=False)
        sm.register_handler("B", lambda ctx: "Z")
        status = await sm.run({})
        assert status.is_terminated is True
        assert len(status.errors) == 1
        assert "Invalid transition" in status.errors[0]

    @pytest.mark.asyncio
    async def test_handler_exception_stop_strategy(self) -> None:
        """on_error_strategy='stop' terminates on handler exception."""
        sm = _build_abc_machine(on_error="stop")

        def bad_handler(ctx: dict[str, str]) -> str:
            raise RuntimeError("boom")

        sm.register_handler("A", bad_handler)  # type: ignore[arg-type]
        status = await sm.run({})
        assert status.is_terminated is True
        assert "boom" in status.errors

    @pytest.mark.asyncio
    async def test_max_iterations_guard(self) -> None:
        """max_iterations prevents infinite loops."""
        sm = _build_abc_machine(max_iter=3)
        # Create a loop: A -> B -> A -> B -> ...
        sm.register_transition(TransitionRule(from_state="C", to_state="A"))
        sm.register_handler("C", lambda ctx: "A")
        status = await sm.run({})
        assert status.is_terminated is True
        assert status.transition_count <= 3


class TestLifecycleHooks:
    """Verify lifecycle hooks fire at the correct times."""

    @pytest.mark.asyncio
    async def test_on_enter_hook(self) -> None:
        """on_enter hook fires when entering a state."""
        sm = _build_abc_machine()
        entered: list[str] = []
        sm.register_lifecycle_hook("on_enter", "A", lambda ctx: entered.append("A"))
        sm.register_lifecycle_hook("on_enter", "B", lambda ctx: entered.append("B"))
        await sm.run({})
        assert entered == ["A", "B"]

    @pytest.mark.asyncio
    async def test_on_exit_hook(self) -> None:
        """on_exit hook fires when leaving a state."""
        sm = _build_abc_machine()
        exited: list[str] = []
        sm.register_lifecycle_hook("on_exit", "A", lambda ctx: exited.append("A"))
        sm.register_lifecycle_hook("on_exit", "B", lambda ctx: exited.append("B"))
        await sm.run({})
        assert exited == ["A", "B"]

    @pytest.mark.asyncio
    async def test_on_error_hook(self) -> None:
        """on_error hook fires when a handler raises."""
        sm = _build_abc_machine(on_error="stop")
        errors: list[str] = []
        sm.register_lifecycle_hook("on_error", "A", lambda ctx: errors.append("A"))

        def bad(ctx: dict[str, str]) -> str:
            raise RuntimeError("fail")

        sm.register_handler("A", bad)  # type: ignore[arg-type]
        await sm.run({})
        assert errors == ["A"]


class TestResetAndStatus:
    """Verify reset() and get_status() behavior."""

    @pytest.mark.asyncio
    async def test_reset_clears_events_and_status(self) -> None:
        """reset() clears events and resets status."""
        sm = _build_abc_machine()
        await sm.run({})
        assert sm.get_status().transition_count == 2
        sm.reset()
        status = sm.get_status()
        assert status.transition_count == 0
        assert status.current_state == "A"
        assert sm.get_events() == []

    @pytest.mark.asyncio
    async def test_get_status_during_and_after_run(self) -> None:
        """get_status() returns correct state after run."""
        sm = _build_abc_machine()
        status_before = sm.get_status()
        assert status_before.is_running is False
        assert status_before.is_terminated is False
        await sm.run({})
        status_after = sm.get_status()
        assert status_after.is_terminated is True
        assert status_after.is_running is False

    @pytest.mark.asyncio
    async def test_rollback_strategy(self) -> None:
        """on_error_strategy='rollback' reverts to previous state."""
        sm = _build_abc_machine(on_error="rollback", max_iter=5)

        call_count = 0

        def failing_b(ctx: dict[str, str]) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient")
            return "C"

        sm.register_handler("B", failing_b)  # type: ignore[arg-type]
        status = await sm.run({})
        assert status.is_terminated is True

    @pytest.mark.asyncio
    async def test_guard_blocks_transition(self) -> None:
        """Guard callable returning False blocks the transition."""
        sm = _build_abc_machine()
        sm.register_transition(
            TransitionRule(from_state="A", to_state="B", guard=lambda ctx: False)
        )
        # Re-register to override the original rule
        sm._transitions = [
            TransitionRule(from_state="A", to_state="B", guard=lambda ctx: False),
            TransitionRule(from_state="B", to_state="C"),
        ]
        status = await sm.run({})
        assert status.transition_count == 0
        assert "Guard blocked" in status.errors[0]
