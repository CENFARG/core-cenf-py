"""InMemoryObservabilityAdapter — in-memory span/metric collector for testing.

Collects all metrics and spans in memory for test assertions. Satisfies
the ObservabilityManager Protocol and provides get_metrics(), get_spans(),
and clear() for inspecting and resetting the collected data.

Security: All data stays in process memory — no network export.
Observability: Deterministic — always returns the same result for the
    same input. Ideal for TDD assertion cycles.
@ai-directive: This adapter exists solely for testing. NEVER use it in
    production code paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import uuid
from typing import Any

from core_infrastructure.observability.models import ObservabilitySettings


class _InMemorySpan:
    """A minimal span implementation for testing.

    Records span data (name, attributes, trace_id, span_id) in memory.
    Usable as a context manager for RAII-style span management.
    """

    def __init__(
        self,
        name: str,
        trace_id: str,
        span_id: str,
        attributes: dict[str, Any] | None = None,
        on_close: Any = None,
    ) -> None:
        self.name = name
        self.trace_id = trace_id
        self.span_id = span_id
        self.attributes: dict[str, Any] = dict(attributes) if attributes else {}
        self._on_close = on_close

    def __enter__(self) -> _InMemorySpan:
        return self

    def __exit__(self, *args: Any) -> None:
        if callable(self._on_close):
            self._on_close(self)

    def to_dict(self) -> dict[str, Any]:
        """Serialize span data to a dictionary for assertions.

        Returns:
            dict: Span data with name, trace_id, span_id, and attributes.
        """
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "attributes": dict(self.attributes),
        }


class InMemoryObservabilityAdapter:
    """In-memory ObservabilityManager for unit test assertions.

    All metric and span calls are recorded in internal lists. The adapter
    satisfies the ``ObservabilityManager`` Protocol and provides inspection
    methods for TDD.

    Usage::

        obs = InMemoryObservabilityAdapter()
        obs.increment_counter("requests", value=5.0)
        obs.start_span("my-op")
        metrics = obs.get_metrics()
        spans = obs.get_spans()
    """

    def __init__(self) -> None:
        self._metrics: list[dict[str, Any]] = []
        self._spans: list[dict[str, Any]] = []
        self._active_span_stack: list[_InMemorySpan] = []
        self._active_trace_id: str = ""

    # ------------------------------------------------------------------
    # Public API — ObservabilityManager Protocol
    # ------------------------------------------------------------------

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Record a counter increment in the metrics buffer.

        Args:
            name: Metric name.
            value: Increment amount (default 1.0).
            attributes: Optional label dict.
        """
        self._metrics.append({
            "type": "counter",
            "name": name,
            "value": value,
            "attributes": dict(attributes) if attributes else {},
        })

    def record_histogram(
        self,
        name: str,
        value: float,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Record a histogram observation in the metrics buffer.

        Args:
            name: Metric name.
            value: Observed value.
            attributes: Optional label dict.
        """
        self._metrics.append({
            "type": "histogram",
            "name": name,
            "value": value,
            "attributes": dict(attributes) if attributes else {},
        })

    def start_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> _InMemorySpan:
        """Start a new tracing span and record it in memory.

        Generates a new trace_id if this is the root span, otherwise
        inherits the current trace context.

        Args:
            name: Span name.
            attributes: Optional span attributes.

        Returns:
            _InMemorySpan: A span object usable as a context manager.
        """
        # Generate trace_id if this is a root span
        if not self._active_trace_id:
            self._active_trace_id = uuid.uuid4().hex

        span_id = uuid.uuid4().hex[:16]

        span = _InMemorySpan(
            name=name,
            trace_id=self._active_trace_id,
            span_id=span_id,
            attributes=attributes,
            on_close=self._on_span_close,
        )

        # Push onto active stack
        self._active_span_stack.append(span)

        # Record span data
        self._spans.append(span.to_dict())

        return span

    def get_current_span(self) -> _InMemorySpan | None:
        """Return the most recently started (innermost) active span.

        Returns:
            _InMemorySpan or None: The active span, or None.
        """
        if self._active_span_stack:
            return self._active_span_stack[-1]
        return None

    def get_trace_id(self) -> str:
        """Return the current trace_id hex string.

        Returns:
            str: Trace ID as hex string, or ``""`` if no trace is active.
        """
        return self._active_trace_id

    async def flush(self) -> None:
        """Flush is a noop for in-memory adapter.

        All data is already stored in memory. No-op to satisfy Protocol.
        """
        return

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing ObservabilitySettings.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return ObservabilitySettings.model_json_schema()

    # ------------------------------------------------------------------
    # Test-specific helpers (not part of ObservabilityManager Protocol)
    # ------------------------------------------------------------------

    def get_metrics(self) -> list[dict[str, Any]]:
        """Return a shallow copy of all recorded metrics.

        Returns:
            list[dict[str, Any]]: All recorded metric entries.
        """
        return list(self._metrics)

    def get_spans(self) -> list[dict[str, Any]]:
        """Return a shallow copy of all recorded spans.

        Returns:
            list[dict[str, Any]]: All recorded span data.
        """
        return list(self._spans)

    def clear(self) -> None:
        """Reset all buffers to empty."""
        self._metrics.clear()
        self._spans.clear()
        self._active_span_stack.clear()
        self._active_trace_id = ""

    def _on_span_close(self, span: _InMemorySpan) -> None:
        """Remove the span from the active stack when it ends.

        Args:
            span: The span being closed.
        """
        if self._active_span_stack and self._active_span_stack[-1] is span:
            self._active_span_stack.pop()
        # Reset trace_id when all spans are closed
        if not self._active_span_stack:
            self._active_trace_id = ""
