---
Spec_ID: SPEC_M07
Title: CacheManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [cache, redis, stampede, xfetch]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M07: CacheManager

## Purpose

Provide key-value cache abstraction with TTL support and stampede mitigation (XFetch algorithm). Uses redis-py asyncio directly — no intermediate facade.

**Does NOT**: Use as primary persistence, add unnecessary abstraction layers over redis-py.

## Python Protocol

```python
from __future__ import annotations
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class CacheManager(Protocol):
    """@ai-directive: Use get_or_set for hot keys to prevent stampede. Never cache credentials."""

    def get(self, key: str) -> Any | None:
        """Retrieve a value from the cache. Returns None for missing/expired."""
        ...

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value with optional TTL."""
        ...

    def delete(self, key: str) -> None:
        """Remove an entry. Idempotent."""
        ...

    def exists(self, key: str) -> bool:
        """Check if key exists and has not expired (TTL-aware)."""
        ...

    def clear(self) -> None:
        """Remove ALL entries immediately."""
        ...

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        """Get from cache or compute and cache. Implements XFetch stampede mitigation."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class CacheSettings(BaseModel):
    backend: Literal["memory", "redis"] = Field(default="memory")
    redis_url: str | None = Field(default=None)
    default_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    max_key_length: int = Field(default=256, ge=32)
    max_value_size_bytes: int = Field(default=1048576, ge=1024)
    stampede_probability: float = Field(default=0.1, ge=0.0, le=1.0)
    namespace: str = Field(min_length=1, max_length=64, default="cenf")
```

## Gherkin Scenarios

### Scenario: Cache hit

- GIVEN key "user:123" is cached with value `{"name": "Alice"}`
- WHEN `get("user:123")` is called
- THEN it returns `{"name": "Alice"}`

### Scenario: Cache miss returns None

- GIVEN key "missing:key" does not exist
- WHEN `get("missing:key")` is called
- THEN it returns `None` (no exception)

### Scenario: get_or_set stampede mitigation

- GIVEN 100 concurrent calls to `get_or_set("hot-key", factory, ttl=60)`
- WHEN the key is near expiry (55 seconds elapsed)
- THEN only ONE call invokes the factory
- AND 99 calls return the cached (possibly stale) value
- AND `cenf.cache.stampede_recompute_total` increments by 1

### Scenario: TTL expiration

- GIVEN key "temp" is set with ttl=5 seconds
- WHEN `exists("temp")` is called after 6 seconds
- THEN it returns `False`

### Scenario: Namespace prefix

- GIVEN namespace="cenf" and key="user:1"
- WHEN `set("user:1", value)` is called
- THEN the actual Redis key is `"cenf:user:1"`

### Scenario: Graceful degradation on Redis failure

- GIVEN Redis connection is lost
- WHEN `get("any-key")` is called
- THEN it returns `None` (cache miss)
- AND the error is logged at ERROR level

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Redis connection lost | TRANSIENT | Return None, log error |
| Non-serializable value | VALIDATION | Re-raise immediately |
| Misconfiguration | PERMANENT | Fail bootstrap |

## RED Metrics

- `cenf.cache.hit_total` (counter)
- `cenf.cache.miss_total` (counter)
- `cenf.cache.errors_total` (counter)
- `cenf.cache.get_duration_seconds` (histogram)
- `cenf.cache.stampede_recompute_total` (counter)
- `cenf.cache.clear_total` (counter)

## Test Requirements

- **Unit**: `InMemoryCacheAdapter` — dict with TTL simulation.
- **Integration**: `RedisAdapter` with testcontainers Redis.
- **E2E**: 100 concurrent `get_or_set` calls, verify single fetch.

## Do's and Don'ts

**Do**:
- Implement XFetch probabilistic early expiration for stampede mitigation
- Use per-key asyncio.Lock for concurrent get_or_set
- Gracefully degrade on Redis failure (return None)
- Prefix all keys with namespace

**Don't**:
- Use as primary persistence
- Add unnecessary abstraction layers over redis-py
- Cache credentials, tokens, or PII without encryption
