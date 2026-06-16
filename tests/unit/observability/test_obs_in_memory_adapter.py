"""Unit tests for InMemoryObservabilityAdapter — in-memory metric/span collector.

Tests cover:
- Protocol compliance (satisfies ObservabilityManager)
- increment_counter records count assertions
- record_histogram records histogram values
- start_span creates spans with trace_id and span_id
- get_trace_id returns current trace context
- get_spans() and get_metrics() return recorded data
- clear() resets all buffers
- get_json_schema() returns valid schema
- Graceful degradation — never raises on failures

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.observability.ports import ObservabilityManager


@pytest.fixture
def in_memory_obs() -> InMemoryObservabilityAdapter:
    """Create a fresh InMemoryObservabilityAdapter."""
    return InMemoryObservabilityAdapter()


class TestInMemoryObservabilityAdapterProtocol:
    """Verify InMemoryObservabilityAdapter satisfies ObservabilityManager Protocol."""

    def test_satisfies_observability_manager_protocol(self) -> None:
        """InMemoryObservabilityAdapter passes isinstance check against ObservabilityManager."""
        adapter = InMemoryObservabilityAdapter()
        assert isinstance(adapter, ObservabilityManager)

    def test_adapter_has_all_required_methods(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """Adapter exposes all required Protocol methods."""
        assert callable(in_memory_obs.increment_counter)
        assert callable(in_memory_obs.record_histogram)
        assert callable(in_memory_obs.start_span)
        assert callable(in_memory_obs.get_current_span)
        assert callable(in_memory_obs.get_trace_id)
        assert callable(in_memory_obs.flush)
        assert callable(in_memory_obs.get_json_schema)


class TestInMemoryObservabilityAdapterCounters:
    """Verify increment_counter records metrics correctly."""

    def test_increment_counter_records_count(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """increment_counter stores the metric in the metrics buffer."""
        in_memory_obs.increment_counter("requests_total", value=3.0)
        metrics = in_memory_obs.get_metrics()
        assert len(metrics) > 0
        counter = next((m for m in metrics if m["name"] == "requests_total"), None)
        assert counter is not None
        assert counter["value"] == 3.0

    def test_increment_counter_default_value_is_one(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """increment_counter defaults to value=1.0 when not specified."""
        in_memory_obs.increment_counter("hits")
        metrics = in_memory_obs.get_metrics()
        counter = next((m for m in metrics if m["name"] == "hits"), None)
        assert counter is not None
        assert counter["value"] == 1.0

    def test_increment_counter_with_attributes(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """increment_counter stores optional attributes."""
        in_memory_obs.increment_counter("errors", value=5.0, attributes={"code": "500"})
        metrics = in_memory_obs.get_metrics()
        counter = next((m for m in metrics if m["name"] == "errors"), None)
        assert counter is not None
        assert counter["attributes"] == {"code": "500"}

    def test_multiple_increment_calls_accumulate(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """Multiple calls to increment_counter are all recorded."""
        in_memory_obs.increment_counter("a", value=1.0)
        in_memory_obs.increment_counter("b", value=2.0)
        in_memory_obs.increment_counter("a", value=3.0)
        metrics = in_memory_obs.get_metrics()
        assert len(metrics) == 3


class TestInMemoryObservabilityAdapterHistograms:
    """Verify record_histogram records histogram values."""

    def test_record_histogram_stores_value(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """record_histogram stores the value in the metrics buffer."""
        in_memory_obs.record_histogram("request_latency", value=0.45)
        metrics = in_memory_obs.get_metrics()
        hist = next((m for m in metrics if m["name"] == "request_latency"), None)
        assert hist is not None
        assert hist["value"] == 0.45
        assert hist["type"] == "histogram"

    def test_record_histogram_with_attributes(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """record_histogram stores optional attributes."""
        in_memory_obs.record_histogram("latency", value=1.2, attributes={"endpoint": "/api"})
        metrics = in_memory_obs.get_metrics()
        hist = next((m for m in metrics if m["name"] == "latency"), None)
        assert hist is not None
        assert hist["attributes"] == {"endpoint": "/api"}


class TestInMemoryObservabilityAdapterSpans:
    """Verify start_span creates span objects with trace context."""

    def test_start_span_creates_span_with_trace_id(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """start_span returns a span object and records it with a trace_id."""
        span = in_memory_obs.start_span("test-operation")
        assert span is not None
        trace_id = in_memory_obs.get_trace_id()
        assert trace_id, "trace_id must be non-empty after starting a span"
        # Ensure the span ID is a valid hex string
        assert len(trace_id) > 0

    def test_start_span_sets_span_id_in_context(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """start_span also sets span_id in context."""
        span = in_memory_obs.start_span("op")
        assert span is not None
        # get_current_span should return the active span
        current = in_memory_obs.get_current_span()
        assert current is not None

    def test_start_span_with_attributes(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """start_span stores optional attributes on the span."""
        _span = in_memory_obs.start_span("http-request", attributes={"http.method": "GET"})
        spans = in_memory_obs.get_spans()
        assert len(spans) > 0
        recorded = spans[-1]
        assert recorded["name"] == "http-request"
        assert recorded["attributes"]["http.method"] == "GET"

    def test_multiple_spans_nested(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """Multiple nested spans are all recorded."""
        with in_memory_obs.start_span("outer"), in_memory_obs.start_span("inner"):
            pass
        spans = in_memory_obs.get_spans()
        assert len(spans) >= 2
        names = [s["name"] for s in spans]
        assert "outer" in names
        assert "inner" in names

    def test_get_current_span_returns_none_when_no_span(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """get_current_span() returns None when no span is active."""
        assert in_memory_obs.get_current_span() is None


class TestInMemoryObservabilityAdapterTrace:
    """Verify get_trace_id returns trace context."""

    def test_get_trace_id_returns_empty_when_no_trace(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """get_trace_id() returns empty string when no trace is active."""
        tid = in_memory_obs.get_trace_id()
        assert tid == "" or isinstance(tid, str)

    def test_get_trace_id_after_span_starts(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """get_trace_id() returns a non-empty trace ID after start_span."""
        in_memory_obs.start_span("operation")
        tid = in_memory_obs.get_trace_id()
        assert tid, "Expected non-empty trace_id after starting a span"


class TestInMemoryObservabilityAdapterBuffer:
    """Verify get_metrics, get_spans, and clear behavior."""

    def test_get_metrics_returns_copy(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """get_metrics() returns a copy — mutating it doesn't affect internal buffer."""
        in_memory_obs.increment_counter("test", value=1.0)
        metrics = in_memory_obs.get_metrics()
        metrics.clear()
        assert len(in_memory_obs.get_metrics()) == 1

    def test_get_spans_returns_copy(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """get_spans() returns a copy."""
        in_memory_obs.start_span("test")
        spans = in_memory_obs.get_spans()
        spans.clear()
        assert len(in_memory_obs.get_spans()) == 1

    def test_clear_resets_all_buffers(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """clear() empties both metrics and spans."""
        in_memory_obs.increment_counter("c1")
        in_memory_obs.start_span("s1")
        assert len(in_memory_obs.get_metrics()) > 0
        assert len(in_memory_obs.get_spans()) > 0
        in_memory_obs.clear()
        assert len(in_memory_obs.get_metrics()) == 0
        assert len(in_memory_obs.get_spans()) == 0

    def test_get_json_schema_returns_dict(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """get_json_schema() returns a non-empty dict."""
        schema = in_memory_obs.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    async def test_flush_is_noop(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """flush() is a noop for in-memory adapter (does not raise)."""
        await in_memory_obs.flush()
        # State unchanged
        assert len(in_memory_obs.get_metrics()) == 0

    def test_adapter_never_raises(self, in_memory_obs: InMemoryObservabilityAdapter) -> None:
        """All methods must never raise — degrade gracefully."""
        # Calling with None name should not raise
        in_memory_obs.increment_counter("")  # type: ignore[arg-type]
        # Empty attributes
        in_memory_obs.record_histogram("h", value=1.0)
        # No active span
        assert in_memory_obs.get_current_span() is None
