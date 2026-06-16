"""Unit tests for ClassificationAdapter — ErrorHandlingManager implementation.

Tests cover:
- @handle_errors classifies TransientError and re-raises
- @handle_errors classifies PermanentError and re-raises
- @handle_errors classifies ValidationError and re-raises
- @handle_errors classifies AuthError and re-raises
- @handle_errors classifies RateLimitError and re-raises
- ExceptionGroup (PEP 654) recursive unwrapping
- Metric emission via ObservabilityManager.increment_counter
- Log verification via LoggerManager
- Errors are NEVER swallowed (always re-raised)
- @functools.wraps preserves function metadata

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.common.errors import (
    AuthError,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationError,
)
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.classification_adapter import ClassificationAdapter
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)


@pytest.fixture
def error_handler() -> ClassificationAdapter:
    """Create a ClassificationAdapter with in-memory deps."""
    config = InMemoryConfigAdapter()
    logger = InMemoryLoggerAdapter()
    observability = InMemoryObservabilityAdapter()
    return ClassificationAdapter(config=config, logger=logger, observability=observability)


class TestClassificationAdapterProtocol:
    """Verify ClassificationAdapter satisfies ErrorHandlingManager Protocol."""

    def test_satisfies_protocol(self, error_handler: ClassificationAdapter) -> None:
        """ClassificationAdapter passes isinstance check."""
        assert isinstance(error_handler, ErrorHandlingManager)

    def test_has_classify_method(self, error_handler: ClassificationAdapter) -> None:
        """Adapter has classify() method."""
        assert callable(error_handler.classify)

    def test_has_handle_errors_decorator(self, error_handler: ClassificationAdapter) -> None:
        """Adapter has handle_errors decorator factory."""
        assert callable(error_handler.handle_errors)


class TestHandleErrorsDecorator:
    """Verify @handle_errors decorator classifies and re-raises errors."""

    def test_transient_error_classified_and_re_raised(self, error_handler: ClassificationAdapter) -> None:
        """@handle_errors classifies TransientError and re-raises it."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            raise TransientError("temporary failure")

        with pytest.raises(TransientError) as exc_info:
            failing_func()

        assert exc_info.value.error_type is not None
        assert "temporary failure" in str(exc_info.value)

    def test_permanent_error_classified_and_re_raised(self, error_handler: ClassificationAdapter) -> None:
        """@handle_errors classifies PermanentError and re-raises it."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            raise PermanentError("permanent failure")

        with pytest.raises(PermanentError) as exc_info:
            failing_func()

        assert "permanent failure" in str(exc_info.value)

    def test_validation_error_classified_and_re_raised(self, error_handler: ClassificationAdapter) -> None:
        """@handle_errors classifies ValidationError and re-raises it."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            raise ValidationError("invalid input", details={"field": "email"})

        with pytest.raises(ValidationError) as exc_info:
            failing_func()

        assert "invalid input" in str(exc_info.value)
        assert exc_info.value.details.get("field") == "email"

    def test_auth_error_classified_and_re_raised(self, error_handler: ClassificationAdapter) -> None:
        """@handle_errors classifies AuthError and re-raises it."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            raise AuthError("unauthorized access")

        with pytest.raises(AuthError) as exc_info:
            failing_func()

        assert "unauthorized access" in str(exc_info.value)

    def test_rate_limit_error_classified_and_re_raised(self, error_handler: ClassificationAdapter) -> None:
        """@handle_errors classifies RateLimitError and re-raises it."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            raise RateLimitError("too many requests")

        with pytest.raises(RateLimitError) as exc_info:
            failing_func()

        assert "too many requests" in str(exc_info.value)

    def test_unknown_non_cenf_error_still_re_raised(self, error_handler: ClassificationAdapter) -> None:
        """@handle_errors re-raises non-Cenf errors (ValueError, etc.)."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            raise ValueError("some runtime error")

        with pytest.raises(ValueError) as exc_info:
            failing_func()

        assert "some runtime error" in str(exc_info.value)

    def test_decorator_emits_metric_on_error(self, error_handler: ClassificationAdapter) -> None:
        """@handle_errors increments cenf.error.classified_total counter."""

        @error_handler.handle_errors()
        def failing_func() -> int:
            raise TransientError("metric test")

        with pytest.raises(TransientError):
            failing_func()

        metrics = error_handler._observability.get_metrics()
        assert len(metrics) >= 1
        # Find the error classification counter
        error_metrics = [m for m in metrics if "error" in m["name"].lower()]
        assert len(error_metrics) >= 1

    def test_decorator_logs_error(self, error_handler: ClassificationAdapter) -> None:
        """@handle_errors logs the error via LoggerManager."""

        @error_handler.handle_errors()
        def failing_func() -> int:
            raise PermanentError("log test")

        with pytest.raises(PermanentError):
            failing_func()

        logs = error_handler._logger.get_logs()
        assert len(logs) >= 1
        error_logs = [log for log in logs if log.get("level") in ("ERROR", "WARNING")]
        assert len(error_logs) >= 1

    def test_decorator_does_not_swallow_error_on_exception_group(self) -> None:
        """@handle_errors re-raises even when ExceptionGroup contains CenfErrors."""

        # Need a fresh handler to test this specifically
        config = InMemoryConfigAdapter()
        logger = InMemoryLoggerAdapter()
        obs = InMemoryObservabilityAdapter()
        handler = ClassificationAdapter(config=config, logger=logger, observability=obs)

        @handler.handle_errors()
        def failing_func() -> str:
            raise ExceptionGroup(
                "grouped failures",
                [TransientError("inner 1"), ValueError("inner 2")],
            )

        with pytest.raises(ExceptionGroup) as exc_info:
            failing_func()

        # ExceptionGroup is re-raised (not swallowed)
        assert len(exc_info.value.exceptions) >= 1


class TestFunctoolsWraps:
    """Verify @handle_errors preserves function metadata via @functools.wraps."""

    def test_preserves_function_name(self, error_handler: ClassificationAdapter) -> None:
        """Decorated function keeps its __name__."""

        @error_handler.handle_errors()
        def my_custom_func(x: int) -> int:
            return x + 1

        assert my_custom_func.__name__ == "my_custom_func"

    def test_preserves_docstring(self, error_handler: ClassificationAdapter) -> None:
        """Decorated function keeps its __doc__."""

        @error_handler.handle_errors()
        def documented_func(x: int) -> int:
            """Returns x plus one."""
            return x + 1

        assert documented_func.__doc__ == "Returns x plus one."


class TestExceptionGroupUnwrapping:
    """Verify ExceptionGroup (PEP 654) recursive unwrapping behavior."""

    def test_exception_group_with_single_cenf_error(self, error_handler: ClassificationAdapter) -> None:
        """When ExceptionGroup wraps a single TransientError."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            raise ExceptionGroup("single", [TransientError("grouped transient")])

        with pytest.raises(ExceptionGroup) as exc_info:
            failing_func()

        group_excs = exc_info.value.exceptions
        assert len(group_excs) == 1
        assert isinstance(group_excs[0], TransientError)

    def test_exception_group_with_mixed_errors(self, error_handler: ClassificationAdapter) -> None:
        """When ExceptionGroup contains both CenfError and non-Cenf."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            raise ExceptionGroup(
                "mixed",
                [TransientError("t"), ValueError("v"), RateLimitError("r")],
            )

        with pytest.raises(ExceptionGroup) as exc_info:
            failing_func()

        group_excs = exc_info.value.exceptions
        assert len(group_excs) == 3
        types = [type(e) for e in group_excs]
        assert TransientError in types
        assert ValueError in types
        assert RateLimitError in types

    def test_nested_exception_groups_re_raised(self, error_handler: ClassificationAdapter) -> None:
        """Nested ExceptionGroups are re-raised without unwrapping."""

        @error_handler.handle_errors()
        def failing_func() -> str:
            inner = ExceptionGroup("inner", [TransientError("nested")])
            raise ExceptionGroup("outer", [inner])

        with pytest.raises(ExceptionGroup) as exc_info:
            failing_func()

        # The outer ExceptionGroup is re-raised
        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], ExceptionGroup)
