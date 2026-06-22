---
sidebar_position: 11
---

# ExternalAPIManager (M11)

Resilient HTTP client with per-host circuit breaker, exponential backoff retry with jitter, and W3C trace context propagation. All infrastructure managers that need outbound HTTP communication consume this interface. Timeouts are mandatory — circuit breaker protects by host.

## Protocol

`ExternalAPIManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.external_api.ports`.

### `async request(method, url, headers, body, timeout, retry_policy) → ApiResponse`

Execute an HTTP request with circuit breaker and retry logic. This is the core method — `get()` and `post()` are convenience wrappers.

```python
async def request(
    self,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float | None = None,
    retry_policy: RetryPolicy | None = None,
) -> ApiResponse: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `method` | `str` | HTTP method (`GET`, `POST`, `PUT`, `DELETE`, etc.) |
| `url` | `str` | Full request URL (max 2048 chars) |
| `headers` | `dict \| None` | Optional request headers |
| `body` | `dict \| None` | Optional request body (JSON-serializable) |
| `timeout` | `float \| None` | Timeout in seconds (overrides default 30s) |
| `retry_policy` | `RetryPolicy \| None` | Per-request retry policy override |

**Returns:** `ApiResponse` — never raises on HTTP errors. Status code 0 for connection errors, 503 for open circuit.

**@ai-directive:** Circuit breaker is per-host — hosts are extracted from URL. Auth headers are handled by AuthManager, not by this Protocol.

---

### `async get(url, headers, timeout) → ApiResponse`

Convenience method for HTTP GET requests. Delegates to `request("GET", ...)`.

```python
async def get(
    self,
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> ApiResponse: ...
```

---

### `async post(url, body, headers, timeout) → ApiResponse`

Convenience method for HTTP POST requests. Delegates to `request("POST", ...)`.

```python
async def post(
    self,
    url: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> ApiResponse: ...
```

---

### `get_circuit_state(host) → CircuitState`

Get the current circuit breaker state for a host. Synchronous — reads cached state, no I/O.

```python
def get_circuit_state(self, host: str) -> CircuitState: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `host` | `str` | Hostname extracted from URL |

**Returns:** `CircuitState` — one of `CLOSED`, `OPEN`, `HALF_OPEN`.

---

## Models

**File:** `core_infrastructure.external_api.models`

### `CircuitState` (StrEnum)

Circuit breaker states with transitions:

```
CLOSED ──(5 consecutive failures)──▶ OPEN
OPEN   ──(30s recovery timeout)───▶ HALF_OPEN
HALF_OPEN ──(success)──────────────▶ CLOSED
HALF_OPEN ──(failure)──────────────▶ OPEN
```

### `ApiResponse`

| Field | Type | Description |
|-------|------|-------------|
| `status_code` | `int` | HTTP status code (0 for connection errors) |
| `headers` | `dict[str, str]` | Response headers |
| `body` | `Any` | Parsed response body (untyped — callers MUST validate) |
| `elapsed_ms` | `float` | Request duration in milliseconds |

### `RetryPolicy`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_retries` | `int` | `3` | Maximum retry attempts |
| `backoff_base` | `float` | `2.0` | Base for exponential backoff: `base^attempt * factor` |
| `backoff_factor` | `float` | `1.0` | Multiplier for backoff calculation |
| `jitter` | `bool` | `True` | Add random jitter (±25%) to prevent thundering herd |
| `retryable_statuses` | `list[int]` | `[429, 502, 503, 504]` | Status codes that trigger retry |

### `RequestConfig`

Bundled configuration: `method`, `url`, `headers`, `body`, `timeout`, `retry_policy`.

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `ResilientHTTPAdapter` | `aiohttp` / `urllib` | Production — circuit breaker, retry, W3C trace context via `traceparent` |
| `MockHTTPAdapter` | In-memory dict | Testing — preconfigure responses, response sequences, circuit state injection, timeout simulation |

---

## Usage Example

```python
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter
from core_infrastructure.external_api.models import CircuitState, RetryPolicy

http_client = MockHTTPAdapter()

# Configure mock responses
http_client.set_response("GET", "https://ocr-api.example.com/v1/status",
                         status_code=200, body={"status": "healthy", "version": "2.1.0"})
http_client.set_response("POST", "https://ocr-api.example.com/v1/extract",
                         status_code=201, body={"job_id": "ocr-12345"})

# GET request
get_response = await http_client.get("https://ocr-api.example.com/v1/status")
assert get_response.status_code == 200

# POST with body
post_response = await http_client.post(
    "https://ocr-api.example.com/v1/extract",
    body={"document_url": "memory://docs/report.pdf"},
)
assert post_response.status_code == 201

# Circuit breaker inspection
circuit_state = http_client.get_circuit_state("ocr-api.example.com")
assert circuit_state == CircuitState.CLOSED

# Response sequences for retry testing
http_client.set_response_sequence("GET", "https://api.example.com/unstable", [
    (503, {"error": "unavailable"}),
    (503, {"error": "unavailable"}),
    (200, {"ok": True}),
])

# Custom retry policy
policy = RetryPolicy(max_retries=5, backoff_base=2.0, jitter=True)
resp = await http_client.request("GET", "https://api.example.com/data",
                                  retry_policy=policy)

# Force circuit breaker open for resilience testing
http_client.set_circuit_state("api.example.com", CircuitState.OPEN)
circuit_resp = await http_client.get("https://api.example.com/data")
assert circuit_resp.status_code == 503  # Circuit open
```

---

## @ai-directive

> **Circuit breaker protects by host. Timeouts are mandatory.** Never call an external API without going through ExternalAPIManager. The circuit breaker is per-host — hosts are extracted from URL. Auth headers are handled by AuthManager, not by this Protocol. Never pass raw credentials in the headers dict. `get_circuit_state()` is synchronous (reads cached state, no I/O).

- W3C trace context propagation via `traceparent` header from contextvars.
- Retryable statuses: `429`, `502`, `503`, `504`.
- Circuit thresholds: 5 consecutive failures → OPEN, 30s recovery → HALF_OPEN, success → CLOSED.

## Related

- [AuthManager](auth-manager.md) — provides auth headers for outbound requests
- [ObservabilityManager](observability-manager.md) — receives `cenf.external_api.*` metrics
- [LoggerManager](logger-manager.md) — all requests logged at DEBUG with `status_code` and `elapsed_ms`
