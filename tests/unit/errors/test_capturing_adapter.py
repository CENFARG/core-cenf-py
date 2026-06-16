"""Unit tests for CapturingErrorAdapter — test double for ErrorHandlingManager.

Tests cover:
- Capturing instead of re-raising errors
- get_captured() returns all captured errors
- Captured errors retain original type and message
- clear_captured() resets the error buffer
- Protocol compliance (satisfies ErrorHandlingManager)

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.common.errors import (
    AuthError,
    PermanentError,
    TransientError,
    ValidationError,
)
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)


@pytest.fixture
def capturing_handler() -> CapturingErrorAdapter:
    """Create a CapturingErrorAdapter with in-memory deps."""
    config = InMemoryConfigAdapter()
    logger = InMemoryLoggerAdapter()
    observability = InMemoryObservabilityAdapter()
    return CapturingErrorAdapter(config=config, logger=logger, observability=observability)


class TestCapturingErrorAdapterProtocol:
    """Verify CapturingErrorAdapter satisfies ErrorHandlingManager Protocol."""

    def test_satisfies_protocol(self, capturing_handler: CapturingErrorAdapter) -> None:
        """CapturingErrorAdapter passes isinstance check."""
        assert isinstance(capturing_handler, ErrorHandlingManager)

    def test_has_classify_method(self, capturing_handler: CapturingErrorAdapter) -> None:
        """Adapter has classify() method."""
        assert callable(capturing_handler.classify)


class TestCapturingBehavior:
    """Verify errors are captured instead of re-raised."""

    def test_capture_transient_error(self, capturing_handler: CapturingErrorAdapter) -> None:
        """CapturingErrorAdapter captures TransientError without raising."""

        @capturing_handler.handle_errors()
        def failing_func() -> str:
            raise TransientError("captured transient")

        result = failing_func()
        assert result is None

        captured = capturing_handler.get_captured()
        assert len(captured) == 1
        assert isinstance(captured[0], TransientError)
        assert "captured transient" in str(captured[0])

    def test_capture_permanent_error(self, capturing_handler: CapturingErrorAdapter) -> None:
        """CapturingErrorAdapter captures PermanentError."""

        @capturing_handler.handle_errors()
        def failing_func() -> str:
            raise PermanentError("captured permanent")

        result = failing_func()
        assert result is None

        captured = capturing_handler.get_captured()
        assert len(captured) == 1
        assert isinstance(captured[0], PermanentError)

    def test_capture_validation_error(self, capturing_handler: CapturingErrorAdapter) -> None:
        """CapturingErrorAdapter captures ValidationError with details."""

        @capturing_handler.handle_errors()
        def failing_func() -> str:
            raise ValidationError("bad data", details={"key": "name"})

        failing_func()
        captured = capturing_handler.get_captured()
        assert len(captured) == 1
        err = captured[0]
        assert isinstance(err, ValidationError)
        assert err.details.get("key") == "name"

    def test_capture_auth_error(self, capturing_handler: CapturingErrorAdapter) -> None:
        """CapturingErrorAdapter captures AuthError."""

        @capturing_handler.handle_errors()
        def failing_func() -> str:
            raise AuthError("forbidden")

        failing_func()
        captured = capturing_handler.get_captured()
        assert len(captured) == 1
        assert isinstance(captured[0], AuthError)

    def test_non_cenf_error_still_captured(self, capturing_handler: CapturingErrorAdapter) -> None:
        """CapturingErrorAdapter captures non-Cenf errors as well."""

        @capturing_handler.handle_errors()
        def failing_func() -> str:
            raise ValueError("bare runtime error")

        failing_func()
        captured = capturing_handler.get_captured()
        assert len(captured) == 1
        assert isinstance(captured[0], ValueError)

    def test_multiple_errors_captured(self, capturing_handler: CapturingErrorAdapter) -> None:
        """Multiple decorated function calls accumulate captured errors."""

        @capturing_handler.handle_errors()
        def fail_once() -> str:
            raise TransientError("first")

        @capturing_handler.handle_errors()
        def fail_twice() -> str:
            raise PermanentError("second")

        fail_once()
        fail_twice()

        captured = capturing_handler.get_captured()
        assert len(captured) == 2
        assert isinstance(captured[0], TransientError)
        assert isinstance(captured[1], PermanentError)

    def test_successful_function_returns_value(self, capturing_handler: CapturingErrorAdapter) -> None:
        """Decorated function that succeeds returns its value."""

        @capturing_handler.handle_errors()
        def success_func(x: int) -> int:
            return x * 2

        result = success_func(21)
        assert result == 42
        assert len(capturing_handler.get_captured()) == 0

    def test_clear_captured_resets_buffer(self, capturing_handler: CapturingErrorAdapter) -> None:
        """clear_captured() empties the error buffer."""

        @capturing_handler.handle_errors()
        def fail() -> str:
            raise TransientError("before clear")

        fail()
        assert len(capturing_handler.get_captured()) == 1
        capturing_handler.clear_captured()
        assert len(capturing_handler.get_captured()) == 0
