"""Pytest fixtures for StateMachineManager unit tests.

Provides InMemoryLoggerAdapter and InMemoryObservabilityAdapter for
production adapter tests, plus pre-configured state machine configs.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.state_machine.adapters.in_memory_state_machine_adapter import (
    InMemoryStateMachineAdapter,
)
from core_infrastructure.state_machine.models import StateMachineConfig


@pytest.fixture
def sm_config() -> StateMachineConfig:
    """Default state machine config for tests."""
    return StateMachineConfig(initial_state="A", max_iterations=10, strict_mode=True)


@pytest.fixture
def sm_adapter(sm_config: StateMachineConfig) -> InMemoryStateMachineAdapter[str, dict[str, str]]:
    """InMemoryStateMachineAdapter with default config."""
    return InMemoryStateMachineAdapter(sm_config)


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """InMemoryLoggerAdapter for production adapter tests."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    """InMemoryObservabilityAdapter for production adapter tests."""
    return InMemoryObservabilityAdapter()
