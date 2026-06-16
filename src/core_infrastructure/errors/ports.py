"""ErrorHandlingManager Protocol — the contract every error handler must satisfy.

Defines the error classification and reporting interface consumed by all
infrastructure managers. The @handle_errors decorator factory provides a
type-safe way to wrap functions with automatic classification, logging,
and metric emission.

Security: Error classification never includes raw secrets. ErrorReport
    messages are sanitized before emission.
Observability: Every @handle_errors invocation emits a RED counter
    ``cenf.error.classified_total{error_type="..."}``.
@ai-directive: handle_errors is a synchronous decorator factory. It MUST
    be applied BEFORE any framework-level middleware that catches exceptions.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

from core_infrastructure.errors.models import ErrorClassification, ErrorReport

F = TypeVar("F", bound=Callable[..., Any])


@runtime_checkable
class ErrorHandlingManager(Protocol):
    """Error classification and reporting contract for all infrastructure managers.

    All managers that need structured error handling consume this interface
    via the @handle_errors decorator factory. The decorator classifies
    exceptions using the CenfError taxonomy, logs them via LoggerManager,
    emits RED metrics via ObservabilityManager, and ALWAYS re-raises
    (NEVER swallows errors).

    Rules:
        - classify() maps any Exception to an ErrorClassification.
        - report() logs and emits metrics for a classified error.
        - handle() performs classify + report in sequence.
        - handle_errors() returns a decorator that wraps sync functions.
        - Errors are NEVER swallowed — always re-raised after classification.

    @ai-directive: When adding a new error taxonomy member, update both
        ErrorClassification enum AND classify() implementation.
    """

    def classify(self, error: Exception) -> ErrorClassification:
        """Classify an exception using the CenfError taxonomy.

        For CenfError subclasses, the mapping is direct (TransientError →
        TRANSIENT). For standard library exceptions, heuristics apply
        (e.g., TimeoutError → TRANSIENT).

        Args:
            error: The exception to classify.

        Returns:
            ErrorClassification: The matching taxonomy member.
        """
        ...

    def report(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log and emit metrics for a classified error.

        Args:
            error: The exception to report.
            context: Optional dict with correlation_id, tenant_id, source keys.
        """
        ...

    def handle(
        self,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> ErrorReport:
        """Classify and report an error in a single call.

        Args:
            error: The exception to handle.
            context: Optional contextual metadata.

        Returns:
            ErrorReport: Structured error report for observability backends.
        """
        ...

    def handle_errors(self, **decorator_opts: Any) -> Callable[[F], F]:
        """Return a decorator that classifies, logs, and re-raises errors.

        The returned decorator wraps any synchronous function. When the
        wrapped function raises, the decorator:
        1. Classifies the exception via ``classify()``
        2. Logs it via LoggerManager
        3. Emits a RED counter via ObservabilityManager
        4. RE-RAISES the exception (NEVER swallows)

        Args:
            **decorator_opts: Optional keyword arguments passed to the decorator
                (e.g., ``reraise=True``, ``log_level="ERROR"``).

        Returns:
            Callable[[F], F]: A decorator that wraps the target function.

        @ai-directive: The decorator MUST use @functools.wraps to preserve
            function metadata. It MUST NEVER swallow errors.
        """
        ...
