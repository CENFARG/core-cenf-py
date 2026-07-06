"""StateMachineManager Protocol — the contract every state machine adapter must satisfy.

Defines the state machine interface for deterministic workflow execution.
States are registered with definitions, transitions are governed by rules
with optional guards, and handlers drive the execution loop.

Security: Handlers and guards are callables — NEVER accept untrusted code
    as handlers. Validate handler sources in production deployments.
Observability: Transition events are recorded for audit. Production adapters
    emit metrics via ObservabilityManager on each transition.
@ai-directive: State machines are deterministic — given the same state and
    context, the same transitions occur. NEVER introduce randomness in handlers.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol, TypeVar, runtime_checkable

from core_infrastructure.state_machine.models import (
    StateDefinition,
    StateMachineStatus,
    TransitionRule,
)

StateT = TypeVar("StateT")
ContextT = TypeVar("ContextT")


@runtime_checkable
class StateMachineManager(Protocol[StateT, ContextT]):
    """Deterministic state machine contract for workflow execution.

    All CENF programs that need deterministic workflow execution consume
    this interface. Concrete adapters provide in-memory execution for
    testing and production-grade execution with logging and metrics.

    Rules:
        - register_state() defines valid states.
        - register_transition() defines valid transitions between states.
        - register_handler() binds a handler callable to a state.
        - run() executes the state machine loop until termination.
        - strict_mode=True raises ValidationError on invalid transitions.
        - max_iterations prevents infinite loops.

    @ai-directive: NEVER register handlers from untrusted sources.
        State machine handlers execute with full context access.
    """

    def register_state(self, state: StateT, definition: StateDefinition) -> None:
        """Register a named state in the machine.

        Args:
            state: The state identifier.
            definition: State metadata and description.
        """
        ...

    def register_transition(self, rule: TransitionRule) -> None:
        """Register a valid transition between two states.

        Args:
            rule: Transition rule with optional guard and callback.
        """
        ...

    def register_handler(
        self, state: StateT, handler: Callable[[ContextT], StateT]
    ) -> None:
        """Bind a handler to a state.

        The handler receives the context and returns the next state.

        Args:
            state: The state to bind the handler to.
            handler: Callable that takes ContextT and returns next StateT.
        """
        ...

    def get_handler(self, state: StateT) -> Callable[[ContextT], StateT] | None:
        """Get the handler registered for a state.

        Args:
            state: The state to look up.

        Returns:
            The handler callable, or None if no handler is registered.
        """
        ...

    def get_valid_transitions(self, state: StateT) -> list[TransitionRule]:
        """Get all valid transitions from a given state.

        Args:
            state: The source state.

        Returns:
            List of TransitionRule objects from the given state.
        """
        ...

    def is_valid_transition(self, from_state: StateT, to_state: StateT) -> bool:
        """Check if a transition between two states is registered.

        Args:
            from_state: Source state.
            to_state: Target state.

        Returns:
            True if the transition is registered.
        """
        ...

    def validate_transition(self, from_state: StateT, to_state: StateT) -> None:
        """Validate a transition, raising ValidationError if invalid.

        Args:
            from_state: Source state.
            to_state: Target state.

        Raises:
            ValidationError: If the transition is not registered.
        """
        ...

    async def run(
        self, ctx: ContextT, start_state: StateT | None = None
    ) -> StateMachineStatus:
        """Execute the state machine loop until termination.

        Args:
            ctx: The context object passed to every handler.
            start_state: Optional override for the initial state.

        Returns:
            StateMachineStatus: Final status after execution.
        """
        ...

    def get_status(self) -> StateMachineStatus:
        """Get the current runtime status.

        Returns:
            StateMachineStatus: Current status snapshot.
        """
        ...

    def reset(self) -> None:
        """Reset the machine to its initial configuration.

        Clears runtime state (events, status) but preserves registered
        states, transitions, and handlers.
        """
        ...

    def register_lifecycle_hook(
        self,
        hook_type: Literal["on_enter", "on_exit", "on_error"],
        state: StateT,
        hook: Callable[[ContextT], None],
    ) -> None:
        """Register a lifecycle hook for a specific state.

        Args:
            hook_type: When the hook fires (enter, exit, or error).
            state: The state the hook is bound to.
            hook: Callable invoked with the context.
        """
        ...
