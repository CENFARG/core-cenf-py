"""CapturingErrorAdapter — ErrorHandlingManager test double that captures errors.

Unlike ClassificationAdapter, this adapter CAPTURES errors instead of
re-raising them. Decorated functions return None on error instead of
propagating the exception. Captured errors are accessible via
get_captured() for TDD assertions.

Security: Captured errors are held in memory only — no persistence.
Observability: Still emits RED metrics and logs (configurable).
@ai-directive: This adapter exists solely for testing. NEVER use it in
    production code paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import functools
from typing import Any

from core_infrastructure.common.errors import (
    AuthError,
    CenfError,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationError,
)
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.models import ErrorClassification, ErrorReport
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.observability.ports import ObservabilityManager

# Internal mapping from CenfError subclasses to ErrorClassification
_ERROR_CLASS_MAP: dict[type, ErrorClassification] = {
    TransientError: ErrorClassification.TRANSIENT,
    PermanentError: ErrorClassification.PERMANENT,
    ValidationError: ErrorClassification.VALIDATION,
    AuthError: ErrorClassification.AUTH,
    RateLimitError: ErrorClassification.RATE_LIMIT,
}


class CapturingErrorAdapter:
    """ErrorHandlingManager test double that captures errors instead of re-raising.

    Receives ConfigManager, LoggerManager, and ObservabilityManager via
    constructor (DI pattern). The @handle_errors decorator factory wraps
    any sync function with automatic error capture — decorated functions
    return None instead of propagating exceptions.

    Args:
        config: ConfigManager for feature flags and settings.
        logger: LoggerManager for structured log emission.
        observability: ObservabilityManager for RED metric emission.

    Usage::

        handler = CapturingErrorAdapter(config, logger, observability)

        @handler.handle_errors()
        def risky_operation() -> str:
            raise TransientError("boom")

        result = risky_operation()  # Returns None, does NOT raise
        assert len(handler.get_captured()) == 1
    """

    def __init__(
        self,
        config: ConfigManager,
        logger: LoggerManager,
        observability: ObservabilityManager,
    ) -> None:
        self._config = config
        self._logger = logger
        self._observability = observability
        self._captured: list[Exception] = []

    # ------------------------------------------------------------------
    # Public API — ErrorHandlingManager Protocol
    # ------------------------------------------------------------------

    def classify(self, error: Exception) -> ErrorClassification:
        """Classify an exception using the CenfError taxonomy.

        Args:
            error: The exception to classify.

        Returns:
            ErrorClassification: The matching taxonomy member.
        """
        if isinstance(error, CenfError):
            error_type = type(error)
            for cls, classification in _ERROR_CLASS_MAP.items():
                if issubclass(error_type, cls):
                    return classification
            return ErrorClassification.PERMANENT

        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return ErrorClassification.TRANSIENT

        return ErrorClassification.PERMANENT

    def report(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log the error and emit a RED counter (still active in test mode).

        Args:
            error: The exception to report.
            context: Optional contextual metadata.
        """
        classification = self.classify(error)
        self._logger.error(
            f"[{classification.name}] {error}",
            exc=error,
            error_type=classification.name,
        )
        self._observability.increment_counter(
            "cenf.error.classified_total",
            value=1.0,
            attributes={
                "error_type": classification.name,
                "error_class": type(error).__qualname__,
            },
        )

    def handle(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> ErrorReport:
        """Capture, report, and return structured ErrorReport.

        Unlike ClassificationAdapter, the error is CAPTURED (appended to
        internal buffer) rather than re-raised. The returned ErrorReport
        satisfies the ErrorHandlingManager Protocol contract.

        Args:
            error: The exception to handle.
            context: Optional contextual metadata.

        Returns:
            ErrorReport: Structured report with classification and context.
        """
        self._captured.append(error)
        self.report(error, context)
        classification = self.classify(error)
        return ErrorReport(
            error_type=classification.name,
            message=str(error),
            source=type(error).__qualname__,
        )

    def handle_errors(self, **decorator_opts: Any) -> Any:
        """Return a @handle_errors decorator that CAPTURES instead of re-raising.

        Decorated functions return None when an exception occurs.

        Args:
            **decorator_opts: Reserved for future use.

        Returns:
            A decorator that wraps the target sync function.
        """

        def decorator(func: Any) -> Any:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    self._captured.append(exc)
                    self.report(
                        exc,
                        context={"source": f"{func.__module__}.{func.__qualname__}"},
                    )
                    return None

            return wrapper

        return decorator

    # ------------------------------------------------------------------
    # Test-specific helpers (not part of ErrorHandlingManager Protocol)
    # ------------------------------------------------------------------

    def get_captured(self) -> list[Exception]:
        """Return all captured errors in capture order.

        Returns:
            list[Exception]: All errors captured since construction or last clear.
        """
        return list(self._captured)

    def clear_captured(self) -> None:
        """Reset the captured error buffer."""
        self._captured.clear()
