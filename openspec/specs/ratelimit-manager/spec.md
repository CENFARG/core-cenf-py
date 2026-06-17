---
Spec_ID: SPEC_M16
Title: RateLimiterManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [rate-limit, token-bucket, sliding-window, headers]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M16: RateLimiterManager

## Purpose

Provide unified rate limiting via Token Bucket and Sliding Window algorithms. Protects endpoints, operations, and alert channels from DoS and overload. Returns standard rate limit headers.

**Does NOT**: Couple to any HTTP framework (FastAPI, Flask), persist state in domain databases.

> **NOTE**: This manager is SPEC ONLY — implementation planned for a future phase.

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class RateLimiterManager(Protocol):
    """@ai-directive: Use is_allowed before any rate-limited operation. Bucket keys are arbitrary strings."""

    async def is_allowed(self, bucket_key: str, cost: float = 1.0) -> bool:
        """Check if an operation is allowed under the rate limit. Consumes tokens if allowed."""
        ...

    async def get_remaining(self, bucket_key: str) -> int:
        """Get remaining tokens/capacity for a bucket."""
        ...

    async def get_reset_time(self, bucket_key: str) -> float:
        """Get the Unix timestamp when the bucket resets."""
        ...

    def configure_bucket(self, bucket_key: str, capacity: int, refill_rate: float, window_type: str = "token_bucket") -> None:
        """Configure a rate limit bucket with capacity and refill rate."""
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class RateLimitSettings(BaseModel):
    default_capacity: int = Field(default=100, ge=1, le=10000)
    default_refill_rate: float = Field(default=10.0, ge=0.1, le=1000.0)
    backend: Literal["memory", "redis"] = Field(default="memory")
    redis_url: str | None = Field(default=None)

class BucketConfig(BaseModel):
    bucket_key: str = Field(min_length=1, max_length=256)
    capacity: int = Field(ge=1, le=10000)
    refill_rate: float = Field(ge=0.1, le=1000.0)
    window_type: Literal["token_bucket", "sliding_window"] = Field(default="token_bucket")
```

## Gherkin Scenarios

### Scenario: Token bucket allows requests within capacity

- GIVEN bucket "api:/users" with capacity=10, refill_rate=1.0
- WHEN `is_allowed("api:/users")` is called 10 times
- THEN all 10 calls return `True`
- AND the 11th call returns `False`

### Scenario: Token bucket refills over time

- GIVEN bucket "api:/users" with capacity=10, refill_rate=1.0 (1 token/second)
- WHEN all 10 tokens are consumed
- AND 5 seconds pass
- THEN `is_allowed("api:/users")` returns `True` (5 tokens refilled)
- AND `get_remaining("api:/users")` returns approximately 4

### Scenario: Sliding window precision

- GIVEN bucket "alert:slack" with sliding window, max 10 requests per 60 seconds
- WHEN 10 requests are made at t=0
- AND a request is made at t=30
- THEN it returns `False` (still within window)
- AND at t=61, it returns `True` (window expired)

### Scenario: Standard headers returned

- GIVEN bucket "api:/users" with capacity=100
- WHEN a request is processed
- THEN the response includes headers:
  - `X-RateLimit-Limit: 100`
  - `X-RateLimit-Remaining: 99`
  - `X-RateLimit-Reset: <unix_timestamp>`
- AND if rate limited, `Retry-After: <seconds>` is included

### Scenario: Redis backend for distributed state

- GIVEN backend="redis" with redis_url configured
- WHEN `is_allowed("api:/users")` is called from process A
- AND `is_allowed("api:/users")` is called from process B
- THEN both processes share the same token count
- AND the combined requests respect the global limit

### Scenario: Custom cost per operation

- GIVEN bucket "api:/heavy" with capacity=100
- WHEN `is_allowed("api:/heavy", cost=10.0)` is called
- THEN 10 tokens are consumed
- AND `get_remaining("api:/heavy")` returns 90

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Redis connection lost | TRANSIENT | Fall back to in-memory, log error |
| Invalid bucket config | VALIDATION | Re-raise immediately |
| Misconfiguration | PERMANENT | Fail bootstrap |

## RED Metrics

- `cenf.ratelimit.allowed_total{bucket_key="..."}` (counter)
- `cenf.ratelimit.denied_total{bucket_key="..."}` (counter)
- `cenf.ratelimit.errors_total` (counter)
- `cenf.ratelimit.check_duration_seconds` (histogram)
- `cenf.ratelimit.tokens_remaining{bucket_key="..."}` (gauge)

## Test Requirements

- **Unit**: `InMemoryRateLimitAdapter` — dict-based token bucket simulation.
- **Integration**: `TokenBucketAdapter` and `SlidingWindowAdapter` with Redis testcontainer.
- **E2E**: Verify standard headers in HTTP response, distributed state across processes.

## Do's and Don'ts

**Do**:
- Implement Token Bucket with configurable capacity and refill rate
- Implement Sliding Window Log for precision in short windows (<1 minute)
- Store state in Redis (production) or in-memory (dev/test)
- Return standard headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After
- Emit OTel metrics with bucket_key label

**Don't**:
- Couple to any HTTP framework (FastAPI, Flask) — the Protocol is generic
- Persist rate limiting state in domain databases
- Allow negative token counts
- Block the main flow when checking rate limits
