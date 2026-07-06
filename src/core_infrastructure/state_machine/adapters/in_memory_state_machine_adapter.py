"""InMemoryStateMachineAdapter — dict-backed state machine adapter for testing.

Provides a fully in-memory StateMachineManager implementation for unit tests.
All states, transitions, handlers, and events are stored in dicts and lists.
Supports lifecycle hooks, error strategies, and strict mode validation.

Security: This adapter exists for testing only. NEVER use in production.
Observability: TransitionEvent records are accumulated for assertion.
@ai-directive: InMemory adapter supports sync handlers only. For async
    handler support, use ProductionStateMachineAdapter.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time as _time
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Literal

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.state_machine.models import (
    StateDefinition,
    StateMachineConfig,
    StateMachineStatus,
    TransitionEvent,
    TransitionRule,
)


class InMemoryStateMachineAdapter[StateT, ContextT]:
    """Dict-backed state machine for unit testing.

    Stores all registration data in dicts. The run() loop dispatches
    handlers synchronously, validates transitions, and records events.

    Args:
        config: StateMachineConfig controlling initial state and behavior.

    Usage::

        config = StateMachineConfig(initial_state="idle")
        sm = InMemoryStateMachineAdapter(config)
        sm.register_state("idle", StateDefinition(name="idle"))
        sm.register_transition(TransitionRule(from_state="idle", to_state="done"))
        sm.register_handler("idle", lambda ctx: "done")
        status = await sm.run(ctx={})
    """

    def __init__(self, config: StateMachineConfig) -> None:
        self._config = config
        self._states: dict[Any, StateDefinition] = {}
        self._transitions: list[TransitionRule] = []
        self._handlers: dict[Any, Callable[..., Any]] = {}
        self._hooks: dict[str, dict[Any, list[Callable[..., None]]]] = {
            "on_enter": defaultdict(list),
            "on_exit": defaultdict(list),
            "on_error": defaultdict(list),
        }
        self._events: list[TransitionEvent] = []
        self._status = StateMachineStatus(current_state=config.initial_state)

    # ------------------------------------------------------------------
    # Public API — StateMachineManager Protocol
    # ------------------------------------------------------------------

    def register_state(self, state: StateT, definition: StateDefinition) -> None:
        """Register a named state in the machine."""
        self._states[state] = definition

    def register_transition(self, rule: TransitionRule) -> None:
        """Register a valid transition between two states."""
        self._transitions.append(rule)

    def register_handler(
        self, state: StateT, handler: Callable[[ContextT], StateT]
    ) -> None:
        """Bind a handler to a state."""
        self._handlers[state] = handler

    def get_handler(self, state: StateT) -> Callable[[ContextT], StateT] | None:
        """Get the handler registered for a state."""
        return self._handlers.get(state)

    def get_valid_transitions(self, state: StateT) -> list[TransitionRule]:
        """Get all valid transitions from a given state."""
        return [r for r in self._transitions if r.from_state == state]

    def is_valid_transition(self, from_state: StateT, to_state: StateT) -> bool:
        """Check if a transition between two states is registered."""
        return any(
            r.from_state == from_state and r.to_state == to_state
            for r in self._transitions
        )

    def validate_transition(self, from_state: StateT, to_state: StateT) -> None:
        """Validate a transition, raising ValidationError if invalid."""
        if not self.is_valid_transition(from_state, to_state):
            raise ValidationError(
                f"Invalid transition: {from_state} -> {to_state}"
            )

    async def run(
        self, ctx: ContextT, start_state: StateT | None = None
    ) -> StateMachineStatus:
        """Execute the state machine loop until termination."""
        current: Any = start_state if start_state is not None else self._config.initial_state
        previous: Any = None
        self._status = StateMachineStatus(
            current_state=str(current), is_running=True, start_time=_time.time(),
        )
        self._fire_hook("on_enter", current, ctx)

        for _ in range(self._config.max_iterations):
            handler = self._handlers.get(current)
            if handler is None:
                break
            try:
                next_state: Any = handler(ctx)
            except Exception as exc:
                self._handle_error(current, ctx, exc)
                if not self._apply_error_strategy(previous):
                    break
                continue

            if not self.is_valid_transition(current, next_state):
                if self._config.strict_mode:
                    self._status.is_running = False
                    self._status.is_terminated = True
                    raise ValidationError(
                        f"Invalid transition: {current} -> {next_state}"
                    )
                self._status.errors.append(
                    f"Invalid transition: {current} -> {next_state}"
                )
                break

            rule = self._get_rule(current, next_state)
            if rule and rule.guard and not rule.guard(ctx):
                self._status.errors.append(f"Guard blocked: {current} -> {next_state}")
                break

            self._fire_hook("on_exit", current, ctx)
            self._events.append(TransitionEvent(
                from_state=str(current), to_state=str(next_state),
                timestamp=_time.time(), success=True,
            ))
            if rule and rule.on_transition:
                rule.on_transition(ctx)

            previous = current
            current = next_state
            self._status.transition_count += 1
            self._status.current_state = str(current)
            self._fire_hook("on_enter", current, ctx)

        self._status.is_running = False
        self._status.is_terminated = True
        return self._status

    def get_status(self) -> StateMachineStatus:
        """Get the current runtime status."""
        return self._status

    def reset(self) -> None:
        """Reset runtime state, preserving registrations."""
        self._events.clear()
        self._status = StateMachineStatus(current_state=self._config.initial_state)

    def register_lifecycle_hook(
        self,
        hook_type: Literal["on_enter", "on_exit", "on_error"],
        state: StateT,
        hook: Callable[[ContextT], None],
    ) -> None:
        """Register a lifecycle hook for a specific state."""
        self._hooks[hook_type][state].append(hook)

    # ------------------------------------------------------------------
    # Test helpers (not part of Protocol)
    # ------------------------------------------------------------------

    def get_events(self) -> list[TransitionEvent]:
        """Return all recorded transition events."""
        return list(self._events)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire_hook(self, hook_type: str, state: Any, ctx: Any) -> None:
        """Fire all registered hooks for a state."""
        for hook in self._hooks[hook_type].get(state, []):
            hook(ctx)

    def _get_rule(self, from_state: Any, to_state: Any) -> TransitionRule | None:
        """Find the transition rule for a state pair."""
        for r in self._transitions:
            if r.from_state == from_state and r.to_state == to_state:
                return r
        return None

    def _handle_error(self, state: Any, ctx: Any, exc: Exception) -> None:
        """Record an error event and fire error hooks."""
        self._fire_hook("on_error", state, ctx)
        self._status.errors.append(str(exc))
        self._events.append(TransitionEvent(
            from_state=str(state), to_state=str(state),
            timestamp=_time.time(), success=False, error=str(exc),
        ))

    def _apply_error_strategy(self, previous: Any) -> bool:
        """Apply on_error_strategy. Returns True to continue, False to stop."""
        strategy = self._config.on_error_strategy
        if strategy == "stop":
            return False
        if strategy == "rollback" and previous is not None:
            self._status.current_state = str(previous)
            return True
        return strategy == "retry"
