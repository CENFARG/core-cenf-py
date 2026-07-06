"""StateMachineManager — deterministic workflow execution with state machines.

Provides the StateMachineManager Protocol contract and adapters for
development/testing (InMemoryStateMachineAdapter) and production
(ProductionStateMachineAdapter).
"""

from core_infrastructure.state_machine.adapters.in_memory_state_machine_adapter import (
    InMemoryStateMachineAdapter,
)
from core_infrastructure.state_machine.adapters.production_state_machine_adapter import (
    ProductionStateMachineAdapter,
)
from core_infrastructure.state_machine.models import (
    StateDefinition,
    StateMachineConfig,
    StateMachineStatus,
    TransitionEvent,
    TransitionRule,
)
from core_infrastructure.state_machine.ports import ContextT, StateMachineManager, StateT

__all__ = [
    "ContextT",
    "InMemoryStateMachineAdapter",
    "ProductionStateMachineAdapter",
    "StateDefinition",
    "StateMachineConfig",
    "StateMachineManager",
    "StateMachineStatus",
    "StateT",
    "TransitionEvent",
    "TransitionRule",
]
