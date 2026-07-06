"""Unit tests for StateMachineManager Protocol contract.

Tests verify the Protocol is runtime_checkable and that adapters satisfy it.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from core_infrastructure.state_machine.adapters.in_memory_state_machine_adapter import (
    InMemoryStateMachineAdapter,
)
from core_infrastructure.state_machine.models import StateMachineConfig
from core_infrastructure.state_machine.ports import StateMachineManager


class TestProtocolContract:
    """Verify Protocol is runtime_checkable and adapters satisfy it."""

    def test_in_memory_adapter_satisfies_protocol(self) -> None:
        """InMemoryStateMachineAdapter satisfies StateMachineManager Protocol."""
        config = StateMachineConfig(initial_state="start")
        adapter: InMemoryStateMachineAdapter[str, dict[str, str]] = (
            InMemoryStateMachineAdapter(config)
        )
        assert isinstance(adapter, StateMachineManager)

    def test_protocol_is_runtime_checkable(self) -> None:
        """StateMachineManager Protocol supports isinstance checks."""
        config = StateMachineConfig(initial_state="start")
        adapter = InMemoryStateMachineAdapter(config)
        # Should not raise TypeError
        isinstance(adapter, StateMachineManager)
