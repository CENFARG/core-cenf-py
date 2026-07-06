"""CENF StateMachineManager models — state definitions, transitions, events, config, status.

Defines the Pydantic models for the state machine domain: state definitions
for registering named states, transition rules with guards and callbacks,
transition events for audit trails, machine configuration, and runtime status.

Security: TransitionRule.guard and on_transition callables are excluded from
    serialization (Field(exclude=True)). Never expose handler references.
Observability: TransitionEvent records timestamps and context snapshots for
    post-mortem analysis. Each event carries success/error state.
@ai-directive: StateMachineConfig.on_error_strategy controls error recovery.
    Use "stop" for fail-fast, "rollback" for safe recovery, "retry" with caution.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field


class StateDefinition(BaseModel):
    """Definition of a named state in the state machine.

    Attributes:
        name: Unique state identifier.
        description: Optional human-readable description.
        metadata: Arbitrary metadata dict for extensibility.
    """

    name: str = Field(..., min_length=1, description="Unique state identifier.")
    description: str | None = Field(default=None, description="Human-readable description.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata.")


class TransitionRule(BaseModel):
    """Rule governing a valid transition between two states.

    Attributes:
        from_state: Source state name.
        to_state: Target state name.
        guard: Optional callable that returns False to block the transition.
        on_transition: Optional callback invoked after a successful transition.
    """

    from_state: str = Field(..., min_length=1, description="Source state name.")
    to_state: str = Field(..., min_length=1, description="Target state name.")
    guard: Callable[..., bool] | None = Field(
        default=None, exclude=True, description="Guard callable; False blocks."
    )
    on_transition: Callable[..., None] | None = Field(
        default=None, exclude=True, description="Callback after transition."
    )


class TransitionEvent(BaseModel):
    """Audit record for a single state transition attempt.

    Attributes:
        from_state: Source state name.
        to_state: Target state name.
        timestamp: Unix timestamp of the transition.
        context_snapshot: Snapshot of relevant context at transition time.
        success: Whether the transition succeeded.
        error: Error message if the transition failed.
    """

    from_state: str = Field(..., min_length=1, description="Source state name.")
    to_state: str = Field(..., min_length=1, description="Target state name.")
    timestamp: float = Field(..., description="Unix timestamp of the transition.")
    context_snapshot: dict[str, Any] = Field(
        default_factory=dict, description="Context snapshot at transition time."
    )
    success: bool = Field(default=True, description="Whether the transition succeeded.")
    error: str | None = Field(default=None, description="Error message on failure.")


class StateMachineConfig(BaseModel):
    """Configuration for a state machine instance.

    Attributes:
        initial_state: The state the machine starts in.
        max_iterations: Safety limit to prevent infinite loops.
        strict_mode: If True, invalid transitions raise ValidationError.
        on_error_strategy: Recovery strategy on handler errors.
    """

    initial_state: str = Field(..., min_length=1, description="Starting state name.")
    max_iterations: int = Field(default=100, ge=1, description="Max loop iterations.")
    strict_mode: bool = Field(default=True, description="Raise on invalid transitions.")
    on_error_strategy: Literal["rollback", "stop", "retry"] = Field(
        default="stop", description="Error recovery strategy."
    )


class StateMachineStatus(BaseModel):
    """Runtime status snapshot of a state machine.

    Attributes:
        current_state: The current active state.
        is_running: True while the run loop is executing.
        is_terminated: True after the run loop completes.
        transition_count: Number of successful transitions.
        errors: List of error messages encountered.
        start_time: Unix timestamp when run() started.
    """

    current_state: str = Field(..., description="Current active state.")
    is_running: bool = Field(default=False, description="True while run loop active.")
    is_terminated: bool = Field(default=False, description="True after run completes.")
    transition_count: int = Field(default=0, ge=0, description="Successful transitions.")
    errors: list[str] = Field(default_factory=list, description="Error messages.")
    start_time: float | None = Field(default=None, description="Unix start timestamp.")
