"""ObservabilityManager Protocol — the contract every telemetry adapter must satisfy.

Defines the observability interface consumed by all infrastructure managers
for emitting RED metrics (Rate, Errors, Duration), creating tracing spans,
and propagating trace context across async boundaries.

Security: Traces MUST NOT include credentials, tokens, or PII.
Observability: All counters and spans use the ``cenf.*`` namespace for
    standardization across services.
@ai-directive: ObservabilityManager methods are SYNC except flush().
    NEVER throw on telemetry failure — degrade gracefully.

Author: CENF AI Team
Version: 0.1.0
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ObservabilityManager(Protocol):
    """Telemetry contract for distributed tracing and RED metrics.

    All infrastructure managers report metrics and create spans through
    this interface. Concrete adapters use OpenTelemetry SDK (production)
    or in-memory collectors (testing).

    Rules:
        - All metric methods MUST NEVER raise — degrade silently on failure.
        - increment_counter defaults value to 1.0 if not specified.
        - start_span returns a span object usable as a context manager.
        - get_trace_id returns empty string when no trace is active.
        - flush() is async — called during shutdown to prevent span loss.
        - get_json_schema() enables LLM agent discovery.

    @ai-directive: When adding a new metric type, update both the Protocol
        and all adapter implementations.
    """

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Increment a named counter by the given value.

        Args:
            name: Metric name (e.g., ``"cenf.http.requests_total"``).
            value: Increment amount (default 1.0).
            attributes: Optional key-value labels for the metric.
        """
        ...

    def record_histogram(
        self,
        name: str,
        value: float,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Record a value on a named histogram.

        Args:
            name: Metric name (e.g., ``"cenf.http.request_duration_seconds"``).
            value: The observed value.
            attributes: Optional key-value labels for the metric.
        """
        ...

    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """Start a new tracing span.

        Args:
            name: Span name (e.g., ``"HTTP GET /api/users"``).
            attributes: Optional key-value span attributes.

        Returns:
            A span object usable as a context manager (``with span:``).
            The exact type depends on the adapter.

        Observability: This method sets ``trace_id`` and ``span_id`` in
            ``common.context`` contextvars for downstream LoggerManager injection.
        """
        ...

    def get_current_span(self) -> Any:
        """Return the currently active span, or None if no span is active.

        Returns:
            The active span object, or ``None``.
        """
        ...

    def get_trace_id(self) -> str:
        """Return the current trace_id hex string.

        Returns:
            str: Trace ID as hex string, or ``""`` if no trace is active.
        """
        ...

    async def flush(self) -> None:
        """Force-flush all pending telemetry data.

        Called during graceful shutdown to prevent data loss. Must be
        idempotent and safe to call multiple times.

        Observability: After this returns, all spans and metrics have been
            exported (or best-effort delivered).
        """
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing ObservabilitySettings.

        Used by LLM agents for tool discovery (AX — Agent Experience).

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        ...
