---
Spec_ID: SPEC_M05
Title: ObservabilityManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [otel, tracing, metrics, spans]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M05: ObservabilityManager

## Purpose

Provide OpenTelemetry SDK integration for distributed tracing and RED metrics. Initializes TracerProvider, MeterProvider, and W3C trace context propagator. Syncs trace_id/span_id to contextvars.

**Does NOT**: Replace LoggerManager for basic debug, include credentials/tokens/PII in traces.

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class ObservabilityManager(Protocol):
    """@ai-directive: Methods are SYNC except flush(). NEVER throw on telemetry failure."""

    def increment_counter(self, name: str, value: float = 1.0, attributes: dict[str, Any] | None = None) -> None:
        """Increment a named counter."""
        ...

    def record_histogram(self, name: str, value: float, attributes: dict[str, Any] | None = None) -> None:
        """Record a value on a named histogram."""
        ...

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """Start a new tracing span. Sets trace_id/span_id in contextvars."""
        ...

    def get_current_span(self) -> Any | None:
        """Return the currently active span, or None."""
        ...

    def get_trace_id(self) -> str:
        """Return the current trace_id hex string."""
        ...

    async def flush(self) -> None:
        """Force-flush all pending telemetry data."""
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return JSON Schema describing ObservabilitySettings."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class ObservabilitySettings(BaseModel):
    service_name: str = Field(min_length=1, max_length=128, default="cenf-core")
    exporter_endpoint: str | None = Field(default=None)
    exporter_protocol: Literal["grpc", "http"] = Field(default="grpc")
    sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    batch_size: int = Field(default=512, ge=1, le=8192)
    flush_interval_seconds: int = Field(default=5, ge=1, le=60)
```

## Gherkin Scenarios

### Scenario: Start span sets contextvars

- WHEN `start_span("test-operation")` is called
- THEN `trace_id` and `span_id` contextvars are set
- AND the span object is usable as a context manager

### Scenario: Increment counter

- WHEN `increment_counter("cenf.http.requests_total", value=1.0, attributes={"method": "GET"})` is called
- THEN the counter is incremented with the given attributes

### Scenario: Flush on shutdown

- GIVEN telemetry data is pending in the batch processor
- WHEN `flush()` is called during shutdown
- THEN all pending spans and metrics are exported
- AND the method is idempotent (safe to call multiple times)

### Scenario: Lazy initialization without endpoint

- GIVEN no `exporter_endpoint` is configured
- WHEN ObservabilityManager.start() is called
- THEN it uses InMemorySpanExporter for testing
- AND no OTLP exporter is initialized

### Scenario: Trace context propagation

- GIVEN an incoming HTTP request with `traceparent` header
- WHEN the request is processed
- THEN `trace_id` contextvar is set from the header
- AND all subsequent spans are children of the incoming trace

### Scenario: Telemetry never raises

- GIVEN the OTLP exporter endpoint is unreachable
- WHEN `increment_counter()` is called
- THEN the error is caught internally
- AND the method returns without raising

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Invalid metric name | VALIDATION | Log and return silently |
| Exporter unreachable | TRANSIENT | Log, retry on next flush |
| SDK misconfiguration | PERMANENT | Log at startup, use in-memory fallback |

## RED Metrics

- `cenf.observability.spans_total` (counter)
- `cenf.observability.flush_errors_total` (counter)
- `cenf.observability.flush_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryObservabilityAdapter` — in-memory span/metric collector.
- **Integration**: `OTelAdapter` with `InMemorySpanExporter`.
- **E2E**: Context propagation across `TaskGroup` boundaries.

## Do's and Don'ts

**Do**:
- Initialize TracerProvider + MeterProvider + W3CTraceContextPropagator in start()
- Use lazy initialization if no exporter_endpoint configured
- Sync trace_id/span_id to contextvars for LoggerManager injection
- Call flush() during stop() to prevent span loss

**Don't**:
- Use for basic debug (use LoggerManager)
- Include credentials, tokens, or PII in traces
- Raise on telemetry failure — degrade gracefully
