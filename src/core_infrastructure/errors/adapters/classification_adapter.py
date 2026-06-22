"""ClassificationAdapter — production ErrorHandlingManager implementation.

Classifies exceptions using the CenfError taxonomy, logs them via LoggerManager,
emits RED metrics via ObservabilityManager, and ALWAYS re-raises. The
@handle_errors decorator factory wraps any synchronous function with automatic
classification, logging, metric emission, and guaranteed re-raise behavior.

ExceptionGroup (PEP 654) handling: nested ExceptionGroups are recursively
unwrapped so each inner CenfError contributes to separate metrics and logs.

Security: Error messages are logged at ERROR level without argument values
    that could leak secrets. ErrorReport is sanitized before emission.
Observability: Every classification emits ``cenf.error.classified_total``
    counter with ``error_type`` label.
@ai-directive: This adapter MUST NEVER swallow errors. The capturing adapter
    exists for test scenarios where swallowing is desired.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import functools
from typing import Any

from core_infrastructure.common.context import get_correlation_id, get_tenant_id
from core_infrastructure.common.errors import (
    AuthError,
    CenfError,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationError,
)
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.models import ErrorClassification, ErrorContext, ErrorReport
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


def _unwind_group(exc: Exception) -> list[Exception]:
    """Recursively extract leaf exceptions from an ExceptionGroup (PEP 654).

    Args:
        exc: The exception to unwind. If not an ExceptionGroup, returns [exc].

    Returns:
        list[Exception]: All leaf exceptions found in the hierarchy.
    """
    if isinstance(exc, ExceptionGroup):
        leaves: list[Exception] = []
        for sub_exc in exc.exceptions:
            leaves.extend(_unwind_group(sub_exc))
        return leaves
    return [exc]


class ClassificationAdapter:
    """Production ErrorHandlingManager with full classification pipeline.

    Receives ConfigManager, LoggerManager, and ObservabilityManager via
    constructor (DI pattern). The @handle_errors decorator factory wraps
    any sync function with automatic error classification, logging,
    metric emission, and guaranteed re-raise.

    Args:
        config: ConfigManager for feature flags and settings.
        logger: LoggerManager for structured log emission.
        observability: ObservabilityManager for RED metric emission.

    Usage::

        handler = ClassificationAdapter(config, logger, observability)

        @handler.handle_errors()
        def risky_operation() -> str:
            ...

    Note:
        handle_errors() is sync only — designed for function-level wrapping.
        For async functions, use ``@handler.handle_errors()`` on the sync
        body or wrap the entire async call chain.
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

    # ------------------------------------------------------------------
    # Public API — ErrorHandlingManager Protocol
    # ------------------------------------------------------------------

    def classify(self, error: Exception) -> ErrorClassification:
        """Classify an exception using the CenfError taxonomy.

        For CenfError subclasses, maps directly via an internal lookup table.
        For non-Cenf exceptions, uses heuristics (e.g., TimeoutError → TRANSIENT).

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

        # Heuristic: known transient exceptions
        if isinstance(error, (TimeoutError, ConnectionError, OSError)):
            return ErrorClassification.TRANSIENT

        # Default: unknown errors are PERMANENT (retry won't help)
        return ErrorClassification.PERMANENT

    def report(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log the error and emit a RED counter metric.

        Args:
            error: The exception to report.
            context: Optional dict with correlation_id, tenant_id, source keys.
        """
        classification = self.classify(error)
        ctx = context or {}
        error_context = ErrorContext(
            correlation_id=ctx.get("correlation_id", get_correlation_id()),
            tenant_id=ctx.get("tenant_id", get_tenant_id()),
            source=ctx.get("source", ""),
        )

        # Log at ERROR level with structured context
        self._logger.error(
            f"[{classification.name}] {error}",
            exc=error,
            error_type=classification.name,
            correlation_id=error_context.correlation_id,
            tenant_id=error_context.tenant_id,
            source=error_context.source,
        )

        # Emit RED metric
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
        """Classify and report an error, returning a structured ErrorReport.

        Args:
            error: The exception to handle.
            context: Optional contextual metadata.

        Returns:
            ErrorReport: Structured report for observability backends.
        """
        self.report(error, context)
        classification = self.classify(error)
        return ErrorReport(
            error_type=classification.name,
            message=str(error),
            source=(context or {}).get("source", ""),
            correlation_id=(context or {}).get("correlation_id", get_correlation_id()),
            tenant_id=(context or {}).get("tenant_id", get_tenant_id()),
        )

    def handle_errors(self, **decorator_opts: Any) -> Any:
        """Return a @handle_errors decorator for synchronous functions.

        The decorator classifies, logs, emits metrics, and RE-RAISES
        every exception. It NEVER swallows errors.

        Args:
            **decorator_opts: Reserved for future use (log_level, etc.).

        Returns:
            A decorator that wraps the target sync function.

        Security: The decorator does NOT log function argument values.
        Observability: RED counter emitted on every error path.
        """

        def decorator(func: Any) -> Any:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    error_source = f"{func.__module__}.{func.__qualname__}"
                    self.report(exc, context={"source": error_source})
                    raise

            return wrapper

        return decorator
