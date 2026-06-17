---
Spec_ID: SPEC_09
Title: Observability
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [otel, metrics, tracing, circuit-breaker, retry]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_09: Observability

## Purpose

Define complete OpenTelemetry integration: RED metrics per manager under `cenf.*` namespace, circuit breaker configs (ExternalAPIManager), retry policies with exponential backoff + jitter, and rate limiting metrics.

## RED Metrics Standard

Every manager SHALL emit three RED metric types under the `cenf.*` namespace:

| Metric Type | Name Pattern | Purpose |
|-------------|-------------|---------|
| **Rate** | `cenf.{manager}.requests_total` | Count of operations |
| **Errors** | `cenf.{manager}.errors_total{error_type="..."}` | Count of failures by type |
| **Duration** | `cenf.{manager}.duration_seconds` | Histogram of operation latency |

### Manager-Specific RED Metrics

| Manager | Rate Counter | Error Counter | Duration Histogram |
|---------|-------------|---------------|-------------------|
| Config | `cenf.config.reload_total` | `cenf.config.errors_total` | `cenf.config.reload_duration_seconds` |
| Logger | `cenf.logger.log_total{level="..."}` | `cenf.logger.errors_total` | `cenf.logger.log_duration_seconds` |
| Secret | `cenf.secret.get_total` | `cenf.secret.errors_total` | `cenf.secret.get_duration_seconds` |
| Error | `cenf.error.classified_total{error_type="..."}` | `cenf.error.pending_count` | — |
| Observability | `cenf.observability.spans_total` | `cenf.observability.flush_errors_total` | `cenf.observability.flush_duration_seconds` |
| Auth | `cenf.auth.validate_total` | `cenf.auth.errors_total{reason="..."}` | `cenf.auth.validate_duration_seconds` |
| Cache | `cenf.cache.hit_total`, `cenf.cache.miss_total` | `cenf.cache.errors_total` | `cenf.cache.get_duration_seconds` |
| Database | `cenf.database.query_total` | `cenf.database.errors_total` | `cenf.database.query_duration_seconds` |
| FileStorage | `cenf.filestorage.upload_total`, `cenf.filestorage.download_total` | `cenf.filestorage.errors_total` | `cenf.filestorage.operation_duration_seconds` |
| TaskQueue | `cenf.taskqueue.enqueue_total`, `cenf.taskqueue.dequeue_total` | `cenf.taskqueue.errors_total` | `cenf.taskqueue.process_duration_seconds` |
| ExternalAPI | `cenf.external_api.requests_total{method="..."}` | `cenf.external_api.errors_total{status="..."}` | `cenf.external_api.request_duration_seconds` |
| FeatureFlag | `cenf.feature_flags.evaluated_total` | `cenf.feature_flags.errors_total` | `cenf.feature_flags.eval_duration_seconds` |
| Dependency | `cenf.dependency.resolve_total` | `cenf.dependency.errors_total` | `cenf.dependency.resolve_duration_seconds` |
| DynamicPrompting | `cenf.prompting.assemble_total` | `cenf.prompting.errors_total` | `cenf.prompting.assemble_duration_seconds` |
| Alert | `cenf.alert.sent_total{channel="..."}` | `cenf.alert.errors_total` | `cenf.alert.send_duration_seconds` |
| RateLimit | `cenf.ratelimit.allowed_total`, `cenf.ratelimit.denied_total` | `cenf.ratelimit.errors_total` | `cenf.ratelimit.check_duration_seconds` |

## Circuit Breaker Configuration (ExternalAPIManager)

### Circuit Breaker States

| State | Condition | Behavior |
|-------|-----------|----------|
| **CLOSED** | Normal operation | Requests pass through |
| **OPEN** | Failure threshold exceeded | All requests fail immediately |
| **HALF_OPEN** | Recovery timeout elapsed | Allow one probe request |

### Configuration Parameters

```python
class CircuitBreakerSettings(BaseModel):
    failure_threshold_pct: float = Field(default=50.0, ge=10.0, le=100.0)
    recovery_timeout_seconds: float = Field(default=30.0, ge=5.0)
    min_requests: int = Field(default=10, ge=1, le=100)
    half_open_max_requests: int = Field(default=3, ge=1, le=10)
```

#### Scenario: Circuit breaker state transitions

- GIVEN circuit is CLOSED with 50% failure rate threshold
- WHEN 10 consecutive requests fail (exceeding min_requests)
- THEN circuit transitions to OPEN
- AND all subsequent requests fail immediately with `CircuitOpenError`
- AFTER 30 seconds (recovery_timeout), circuit transitions to HALF_OPEN
- WHEN one probe request succeeds
- THEN circuit transitions back to CLOSED

## Retry Policies

### Exponential Backoff + Jitter

All retryable operations (TRANSIENT, RATE_LIMIT errors) SHALL use:

```python
class RetrySettings(BaseModel):
    max_retries: int = Field(default=3, ge=1, le=10)
    backoff_base_seconds: float = Field(default=2.0, ge=0.5)
    backoff_max_seconds: float = Field(default=30.0, ge=5.0)
    jitter_factor: float = Field(default=0.5, ge=0.0, le=1.0)
```

**Formula**: `delay = min(backoff_base * (2 ** attempt) + random(0, jitter_factor * delay), backoff_max)`

#### Scenario: Retry with exponential backoff

- GIVEN a TRANSIENT error on first attempt
- WHEN retry policy is applied
- THEN attempt 1 waits ~2s, attempt 2 waits ~4s, attempt 3 waits ~8s
- AND jitter adds ±50% randomness to each delay
- AND no delay exceeds `backoff_max_seconds` (30s)

### Retryable vs Non-Retryable

| ErrorType | Retry? | Strategy |
|-----------|--------|----------|
| TRANSIENT | Yes | Exponential backoff + jitter |
| RATE_LIMIT | Yes | Backoff until `Retry-After` header or default |
| VALIDATION | No | Log and re-raise immediately |
| AUTH | No | Log and re-raise immediately |
| PERMANENT | No | Log and re-raise immediately |

## Rate Limiting Metrics

### Token Bucket Metrics

| Counter | Labels | Description |
|---------|--------|-------------|
| `cenf.ratelimit.allowed_total` | `bucket_key` | Requests that passed rate limit |
| `cenf.ratelimit.denied_total` | `bucket_key` | Requests that were rate-limited |
| `cenf.ratelimit.tokens_remaining` | `bucket_key` | Current tokens in bucket (gauge) |

### Sliding Window Metrics

| Counter | Labels | Description |
|---------|--------|-------------|
| `cenf.ratelimit.window_requests_total` | `bucket_key`, `window` | Requests in current window |
| `cenf.ratelimit.window_limit` | `bucket_key`, `window` | Max requests per window (gauge) |

## OpenTelemetry Initialization

### TracerProvider Setup

- `BatchSpanProcessor` with `OTLPSpanExporter`
- `TraceIdRatioBased` sampler (configurable rate)
- `W3CTraceContextPropagator` for HTTP header propagation

### MeterProvider Setup

- `PeriodicExportingMetricReader` with configurable interval
- `OTLPMetricExporter` for metric export

### Context Sync

- `trace_id` and `span_id` from OTel spans are synced to `contextvars`
- LoggerManager reads these contextvars and injects them into every log record

#### Scenario: Trace context propagation

- GIVEN an HTTP request arrives with `traceparent: 00-abc123-def456-01`
- WHEN ExternalAPIManager processes the request
- THEN `trace_id` contextvar is set to `abc123`
- AND LoggerManager includes `trace_id=abc123` in all log records
- AND new spans created by ObservabilityManager are children of the incoming trace
