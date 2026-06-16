"""NoopObservabilityAdapter — no-op ObservabilityManager for testing/disabling.

A minimal adapter that satisfies the ObservabilityManager Protocol but
performs no actual telemetry. All methods are no-ops. Useful for tests
that don't need observability assertions or for running in environments
where telemetry is disabled.

Security: Zero telemetry data is collected or exported.
Observability: Null — this adapter is intentionally opaque.
@ai-directive: Use InMemoryObservabilityAdapter when you need to assert
    on metrics/spans. Use this when telemetry is irrelevant to the test.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from core_infrastructure.observability.models import ObservabilitySettings


class NoopObservabilityAdapter:
    """No-op ObservabilityManager that silently discards all telemetry.

    All Protocol methods are implemented as no-ops. Satisfies the
    ObservabilityManager Protocol for use in tests and disabled-telemetry
    environments.

    Usage::

        obs = NoopObservabilityAdapter()
        obs.increment_counter("anything")  # silently discarded
        obs.start_span("anything")         # returns a null span
    """

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """No-op — metric is discarded.

        Args:
            name: Metric name (ignored).
            value: Increment amount (ignored).
            attributes: Label dict (ignored).
        """
        return

    def record_histogram(
        self,
        name: str,
        value: float,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """No-op — histogram observation is discarded.

        Args:
            name: Metric name (ignored).
            value: Observed value (ignored).
            attributes: Label dict (ignored).
        """
        return

    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Any:
        """Return a null span that does nothing.

        Args:
            name: Span name (ignored).
            attributes: Span attributes (ignored).

        Returns:
            Any: A null span context manager.
        """
        return _NullSpan()

    def get_current_span(self) -> Any:
        """Return None — no active span.

        Returns:
            None: Always returns None.
        """
        return None

    def get_trace_id(self) -> str:
        """Return empty string — no active trace.

        Returns:
            str: Always returns ``""``.
        """
        return ""

    async def flush(self) -> None:
        """No-op — no data to flush."""
        return

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing ObservabilitySettings.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return ObservabilitySettings.model_json_schema()


class _NullSpan:
    """A no-op span returned when no tracing is active.

    Usable as a context manager — does nothing on enter/exit.
    """

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass
