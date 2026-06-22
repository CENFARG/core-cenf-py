---
sidebar_position: 16
---

# RateLimiterManager (M16)

Unified rate limiting with Token Bucket and Sliding Window algorithms. Protects endpoints, operations, and alert channels from DoS and overload. Supports Redis-backed distributed state for cross-process rate limiting, with graceful fallback to in-memory. Returns standard HTTP rate limit headers. **Use `is_allowed()` before any rate-limited operation.**

## Protocol

`RateLimiterManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.ratelimit.ports`.

### `async is_allowed(bucket_key, cost) → bool`

Check if an operation is allowed under the rate limit. Consumes `cost` tokens from the bucket if sufficient tokens are available.

```python
async def is_allowed(self, bucket_key: str, cost: float = 1.0) -> bool: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `bucket_key` | `str` | Arbitrary string identifying the rate limit bucket |
| `cost` | `float` | Number of tokens to consume (default 1.0) |

**Returns:** `True` if allowed (tokens consumed), `False` if rate-limited (no tokens consumed).

---

### `async get_remaining(bucket_key) → int`

Get remaining tokens for a bucket. Read-only — does NOT consume tokens.

```python
async def get_remaining(self, bucket_key: str) -> int: ...
```

**Returns:** Remaining token count (floored to int).

---

### `async get_reset_time(bucket_key) → float`

Get the Unix timestamp when the bucket will be full again.

```python
async def get_reset_time(self, bucket_key: str) -> float: ...
```

**Returns:** Unix timestamp when bucket reaches full capacity.

---

### `configure_bucket(bucket_key, capacity, refill_rate, window_type) → None`

Configure a rate limit bucket. Must be called before `is_allowed()` for the given key. Overwrites existing configuration.

```python
def configure_bucket(
    self,
    bucket_key: str,
    capacity: int,
    refill_rate: float,
    window_type: str = "token_bucket",
) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `bucket_key` | `str` | Arbitrary bucket identifier |
| `capacity` | `int` | Maximum tokens the bucket can hold (1–10000) |
| `refill_rate` | `float` | Tokens added per second (0.1–1000.0) |
| `window_type` | `str` | Algorithm: `"token_bucket"` or `"sliding_window"` |

---

### `get_json_schema() → dict[str, Any]` *(static)*

Return JSON Schema for agent discovery (AX).

```python
@staticmethod
def get_json_schema() -> dict[str, Any]: ...
```

---

## Models

**File:** `core_infrastructure.ratelimit.models`

### `RateLimitConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_capacity` | `int` (1–10000) | `100` | Default max tokens per bucket |
| `default_refill_rate` | `float` (0.1–1000.0) | `10.0` | Default tokens added per second |
| `redis_enabled` | `bool` | `False` | Whether Redis-backed distributed rate limiting is active |

### `BucketState`

Internal token bucket state: `tokens` (float, ≥0), `last_refill` (Unix timestamp), `capacity` (int), `refill_rate` (float).

### `RateLimitHeaders`

Standard HTTP rate limit response headers:

| Field | Header | Description |
|-------|--------|-------------|
| `limit` | `X-RateLimit-Limit` | Total capacity |
| `remaining` | `X-RateLimit-Remaining` | Tokens left |
| `reset` | `X-RateLimit-Reset` | Unix timestamp of reset |
| `retry_after` | `Retry-After` | Seconds until retry (or `None`) |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `TokenBucketAdapter` | In-memory + optional Redis via CacheManager | Production — Token Bucket and Sliding Window with distributed state |
| `InMemoryRateLimitAdapter` | In-memory dict | Testing — configurable `"always_allow"` / `"always_deny"` modes |

**Redis persistence:** When `CacheManager` (with Redis backend) is provided, bucket state is persisted to Redis with key prefix `cenf:ratelimit:{bucket_key}`. On Redis failure, gracefully falls back to in-memory dicts only. Bucket state JSON includes `tokens`, `last_refill`, `capacity`, `refill_rate`.

---

## Usage Example

```python
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import (
    InMemoryRateLimitAdapter,
)
from core_infrastructure.ratelimit.models import RateLimitHeaders

rate_limiter = InMemoryRateLimitAdapter(mode="always_allow")

# Configure buckets for different API endpoints
rate_limiter.configure_bucket("api:ocr", capacity=100, refill_rate=10.0,
                              window_type="token_bucket")
rate_limiter.configure_bucket("api:storage", capacity=50, refill_rate=5.0,
                              window_type="token_bucket")

# Check before rate-limited operation
for i in range(5):
    allowed = await rate_limiter.is_allowed("api:ocr", cost=1.0)
    if not allowed:
        raise RateLimitError("Too many requests")

# Query remaining capacity
remaining = await rate_limiter.get_remaining("api:ocr")  # → 95
reset_time = await rate_limiter.get_reset_time("api:ocr")

# Testing: always_deny mode
deny_limiter = InMemoryRateLimitAdapter(mode="always_deny")
await deny_limiter.is_allowed("api:ocr")  # → False

# Production: TokenBucketAdapter with Redis
from core_infrastructure.ratelimit.adapters.token_bucket_adapter import TokenBucketAdapter
prod_limiter = TokenBucketAdapter(config, logger, error_handler, cache=redis_cache)
prod_limiter.configure_bucket("api:/users", capacity=1000, refill_rate=100.0)

# Map to HTTP headers
headers = RateLimitHeaders(
    limit=1000,
    remaining=await prod_limiter.get_remaining("api:/users"),
    reset=await prod_limiter.get_reset_time("api:/users"),
    retry_after=None,
)
```

---

## @ai-directive

> **Use `is_allowed()` before any rate-limited operation.** Bucket keys are arbitrary strings — choose meaningful names (e.g., `"api:ocr"`, `"endpoint:/users"`). `is_allowed()` returns False when limits exceeded — never raises. Redis key format is `cenf:ratelimit:{bucket_key}`. Bucket state JSON includes tokens, last_refill, capacity, refill_rate, and timestamps.

## Related

- [CacheManager](cache-manager.md) — optional Redis backend for distributed rate limiting
- [ConfigManager](config-manager.md) — supplies `ratelimit.default_capacity` and `ratelimit.default_refill_rate`
- [AlertManager](alert-manager.md) — rate-limit alert dispatch channels
