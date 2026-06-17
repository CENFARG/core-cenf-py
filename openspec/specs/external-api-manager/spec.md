---
Spec_ID: SPEC_M11
Title: ExternalAPIManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [http, circuit-breaker, aiohttp, tenacity, retry]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M11: ExternalAPIManager

## Purpose

Provide resilient HTTP client with per-host circuit breaker, tenacity retries with exponential backoff + jitter, and W3C trace context propagation. All requests return ApiResponse — never raise on HTTP errors.

**Does NOT**: Expose specific HTTP clients to domain, handle auth headers directly (use AuthManager).

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

from core_infrastructure.external_api.models import ApiResponse, CircuitState, RetryPolicy

@runtime_checkable
class ExternalAPIManager(Protocol):
    """@ai-directive: Circuit breaker is per-host. Check state before retrying failed requests."""

    async def request(self, method: str, url: str, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None, timeout: float | None = None, retry_policy: RetryPolicy | None = None) -> ApiResponse:
        """Execute HTTP request with circuit breaker and retry logic."""
        ...

    async def get(self, url: str, headers: dict[str, str] | None = None, timeout: float | None = None) -> ApiResponse:
        """Convenience method for HTTP GET."""
        ...

    async def post(self, url: str, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float | None = None) -> ApiResponse:
        """Convenience method for HTTP POST."""
        ...

    def get_circuit_state(self, host: str) -> CircuitState:
        """Get circuit breaker state for a host. Sync — reads cached state."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class ExternalAPISettings(BaseModel):
    default_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    max_retries: int = Field(default=3, ge=1, le=10)
    backoff_base_seconds: float = Field(default=2.0, ge=0.5)
    backoff_max_seconds: float = Field(default=30.0, ge=5.0)
    circuit_failure_threshold_pct: float = Field(default=50.0, ge=10.0, le=100.0)
    circuit_recovery_timeout_seconds: float = Field(default=30.0, ge=5.0)
    circuit_min_requests: int = Field(default=10, ge=1, le=100)
    circuit_half_open_max_requests: int = Field(default=3, ge=1, le=10)
    propagate_context: bool = Field(default=True)

class ApiResponse(BaseModel):
    status_code: int
    headers: dict[str, str]
    body: Any
    elapsed_ms: float
    url: str

class RetryPolicy(BaseModel):
    max_retries: int = Field(default=3)
    backoff_base: float = Field(default=2.0)
    backoff_max: float = Field(default=30.0)
    retryable_statuses: list[int] = Field(default=[429, 502, 503, 504])

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
```

## Gherkin Scenarios

### Scenario: Successful GET request

- WHEN `get("https://api.example.com/users")` is called
- THEN it returns `ApiResponse` with status_code, body, elapsed_ms
- AND `traceparent` header is injected from contextvars

### Scenario: Circuit breaker opens after failures

- GIVEN circuit failure threshold is 50% with min_requests=10
- WHEN 10 consecutive requests to "api.example.com" fail
- THEN `get_circuit_state("api.example.com")` returns `CircuitState.OPEN`
- AND subsequent requests fail immediately without network I/O

### Scenario: Circuit breaker recovery

- GIVEN circuit is OPEN for "api.example.com"
- WHEN 30 seconds pass (recovery timeout)
- THEN circuit transitions to HALF_OPEN
- AND one probe request is allowed through
- IF the probe succeeds, circuit transitions to CLOSED

### Scenario: Retry on 503

- GIVEN a request returns HTTP 503
- WHEN retry policy is applied
- THEN the request is retried with exponential backoff + jitter
- AND after max_retries, the final 503 response is returned

### Scenario: No retry on 404

- GIVEN a request returns HTTP 404
- WHEN retry policy is applied
- THEN the request is NOT retried
- AND the 404 response is returned immediately

### Scenario: Timeout enforcement

- GIVEN default_timeout_seconds = 5.0
- WHEN a request takes longer than 5 seconds
- THEN it raises `TransientError` (timeout)
- AND the circuit breaker records a failure

## Error Classification

| HTTP Status | Classification | Handling |
|-------------|---------------|----------|
| 503, 504, timeout | TRANSIENT | Retry with backoff |
| 404, 400, invalid URL | PERMANENT | Return response, no retry |
| 401, 403 | AUTH | Return response, no retry |
| 429 | RATE_LIMIT | Retry after Retry-After header |
| Circuit OPEN | PERMANENT | Fail immediately |

## RED Metrics

- `cenf.external_api.requests_total{method="..."}` (counter)
- `cenf.external_api.errors_total{status="..."}` (counter)
- `cenf.external_api.request_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryExternalAPIAdapter` — mock responses with circuit state.
- **Integration**: `AiohttpAdapter` with local HTTP server (pytest-httpserver).
- **E2E**: Circuit breaker recovery cycle (CLOSED→OPEN→HALF_OPEN→CLOSED).

## Do's and Don'ts

**Do**:
- Create aiohttp ClientSession in start(), close in stop()
- Implement per-host circuit breaker (dict[str, CircuitBreaker])
- Retry TRANSIENT errors with tenacity exponential backoff + jitter
- Inject traceparent and baggage headers from contextvars
- Return ApiResponse for ALL responses (never raise on HTTP errors)

**Don't**:
- Expose specific HTTP clients to domain
- Handle auth headers directly (use AuthManager)
- Use asyncio.gather for concurrent requests (use TaskGroup)
