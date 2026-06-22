---
sidebar_position: 5
---

# ObservabilityManager (M05)

OpenTelemetry-based RED metrics (Rate, Errors, Duration) and distributed tracing. All infrastructure managers report metrics and create spans through this interface.

## Protocol

`ObservabilityManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.observability.ports`.

### `increment_counter(name: str, value: float = 1.0, attributes: dict[str, Any] | None = None) → None`

Increment a named counter by the given value.

```python
def increment_counter(
    self,
    name: str,
    value: float = 1.0,
    attributes: dict[str, Any] | None = None,
) -> None: ...
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Metric name (e.g., `"cenf.http.requests_total"`) |
| `value` | `float` | `1.0` | Increment amount |
| `attributes` | `dict[str, Any] \| None` | `None` | Key-value labels for the metric |

---

### `record_histogram(name: str, value: float, attributes: dict[str, Any] | None = None) → None`

Record a value on a named histogram.

```python
def record_histogram(
    self,
    name: str,
    value: float,
    attributes: dict[str, Any] | None = None,
) -> None: ...
```

Used for duration distributions (e.g., request latency, operation duration).

---

### `start_span(name: str, attributes: dict[str, Any] | None = None) → Any`

Start a new tracing span.

```python
def start_span(
    self,
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Any: ...
```

**Returns:** A span object usable as a context manager (`with span:`).

Sets `trace_id` and `span_id` in `common.context` contextvars for downstream LoggerManager injection.

---

### `get_current_span() → Any`

Return the currently active span, or `None` if no span is active.

```python
def get_current_span(self) -> Any: ...
```

---

### `get_trace_id() → str`

Return the current trace_id hex string.

```python
def get_trace_id(self) -> str: ...
```

**Returns:** Trace ID as hex string, or `""` if no trace is active.

---

### `async flush() → None`

Force-flush all pending telemetry data.

```python
async def flush(self) -> None: ...
```

Called during graceful shutdown to prevent data loss. Must be idempotent and safe to call multiple times. After this returns, all spans and metrics have been exported (or best-effort delivered).

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing `ObservabilitySettings`.

## RED Metrics

The RED method (Rate, Errors, Duration) is the standard observability pattern for services:

| Metric | Instrument | Convention |
|--------|------------|------------|
| **Rate** | Counter | `cenf.{component}.requests_total` |
| **Errors** | Counter | `cenf.error.classified_total{error_type="..."}` |
| **Duration** | Histogram | `cenf.{component}.request_duration_seconds` |

All counters and spans use the `cenf.*` namespace for standardization across services.

## Context Propagation

When `start_span()` is called, it automatically sets these contextvars:

```python
from core_infrastructure.common import context

# Set by start_span():
context.set_trace_id("a1b2c3d4...")
context.set_span_id("e5f6g7h8...")

# Consumed by LoggerManager (auto-injected into every log record)
```

**Rule:** NEVER pass trace context as function arguments. Always use contextvars.

## Models

### `ObservabilitySettings`

**File:** `core_infrastructure.observability.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `service_name` | `str` (1–128) | `"cenf-core"` | Unique service name in telemetry backend |
| `exporter_endpoint` | `str \| None` | `None` | OTLP collector URL. None = console exporter (dev mode) |
| `exporter_protocol` | `Literal["grpc","http"]` | `"grpc"` | Transport protocol for OTLP exporter |
| `sampling_rate` | `float` (0.0–1.0) | `1.0` | Trace sampling rate (0.0 = no traces, 1.0 = all) |
| `batch_size` | `int` (1–8192) | `512` | Maximum spans per export batch |
| `flush_interval_seconds` | `int` (1–60) | `5` | Interval between periodic metric exports |

When `exporter_endpoint` is `None`, the adapter operates in local/dev mode with a console exporter (no remote collector).

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `OTelAdapter` | OpenTelemetry SDK (OTLP) | Production — exports to collector via gRPC or HTTP |
| `InMemoryObservabilityAdapter` | Python dict | Testing — captures counters and histograms for assertions |
| `NoopObservabilityAdapter` | No-op | Disabled telemetry — all methods are silent no-ops |

## Graceful Degradation

If OTel export fails:
- **Never throw** — degrade gracefully
- Log the failure at DEBUG level
- Continue normal operation without telemetry
- Metrics and spans are dropped (best-effort delivery)
- On next `flush()`, retry the connection

## Usage Example

```python
from core_infrastructure.observability.adapters.otel_adapter import OTelAdapter

# Bootstrap
obs = OTelAdapter(config_manager=config, logger_manager=logger)

# Counter — track request rate
obs.increment_counter("cenf.http.requests_total")
obs.increment_counter(
    "cenf.http.requests_total",
    value=1.0,
    attributes={"method": "GET", "status": "200"},
)

# Histogram — track latency
obs.record_histogram(
    "cenf.http.request_duration_seconds",
    value=0.234,
    attributes={"method": "POST"},
)

# Tracing span — sets trace_id + span_id in context
with obs.start_span("HTTP GET /api/users", attributes={"tenant": "cntrs"}) as span:
    # All LoggerManager calls inside this block auto-include trace_id + span_id
    logger.info("Fetching users")
    trace_id = obs.get_trace_id()   # "a1b2c3d4e5f6..."
    result = fetch_users()
    span.set_attribute("user_count", len(result))

# Graceful shutdown — flush pending data
await obs.flush()

# LLM agent discovery
schema = obs.get_json_schema()
```

## @ai-directive

- If OTel export fails, **degrade gracefully — never throw**.
- All metric methods MUST NEVER raise — degrade silently on failure.
- Traces MUST NOT include credentials, tokens, or PII.
- When adding a new metric type, update both the Protocol and all adapter implementations.

## Related

- [LoggerManager](logger-manager.md) — auto-injects trace_id and span_id from context
- [ErrorHandlingManager](error-handling-manager.md) — emits RED error counters
- [CacheManager](cache-manager.md) — emits hit/miss/stampede counters
- [TaskQueueManager](task-queue-manager.md) — emits enqueue/dequeue/ack/nack counters
