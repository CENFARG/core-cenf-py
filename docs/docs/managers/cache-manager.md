---
sidebar_position: 7
---

# CacheManager (M07)

Key-value cache with TTL support and XFetch stampede mitigation via `get_or_set()`. Prevents thundering herd on hot keys using probabilistic early recomputation.

## Protocol

`CacheManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.cache.ports`.

### `get(key: str) → Any`

Retrieve a value from the cache.

```python
def get(self, key: str) -> Any: ...
```

**Returns:** The cached value, or `None` if missing or expired. **Never raises.**

---

### `set(key: str, value: Any, ttl: int | None = None) → None`

Store a value in the cache with an optional TTL.

```python
def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `key` | `str` | The cache key |
| `value` | `Any` | Any Python object |
| `ttl` | `int \| None` | TTL in seconds. If `None`, uses `CacheConfig.default_ttl` |

Overwrites existing keys.

---

### `delete(key: str) → None`

Remove an entry from the cache. Idempotent — deleting a non-existent key succeeds silently.

```python
def delete(self, key: str) -> None: ...
```

---

### `exists(key: str) → bool`

Check if a key exists and has not expired.

```python
def exists(self, key: str) -> bool: ...
```

TTL-aware: returns `False` for expired entries even if they haven't been evicted yet.

---

### `clear() → None`

Remove ALL entries from the cache immediately.

```python
def clear(self) -> None: ...
```

**Observability:** Emits `cenf.cache.clear_total` counter.

---

### `get_or_set(key: str, factory: Callable[[], Any], ttl: int | None = None) → Any`

Get a value from cache or compute and cache it.

```python
def get_or_set(
    self,
    key: str,
    factory: Callable[[], Any],
    ttl: int | None = None,
) -> Any: ...
```

Implements **XFetch stampede mitigation**: when a key is close to expiry, probabilistically recompute early to prevent thundering herd.

| Param | Type | Description |
|-------|------|-------------|
| `key` | `str` | The cache key |
| `factory` | `Callable[[], Any]` | Callable that produces the value when not cached |
| `ttl` | `int \| None` | TTL for the cached value |

**Returns:** The cached or freshly computed value.

**Observability:** Emits `cenf.cache.hit_total` and `cenf.cache.miss_total` counters. Probabilistic early recompute emits `cenf.cache.stampede_recompute_total`.

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing `CacheConfig`.

## Stampede Mitigation — XFetch Algorithm

The XFetch algorithm in `get_or_set()` prevents the **thundering herd** problem: when a popular cache key nears expiration, multiple concurrent requests would normally all try to recompute the value simultaneously.

With XFetch, when `get_or_set()` detects an entry approaching its TTL:
1. Probabilistically decides whether to recompute early (based on `beta` and `delta` parameters)
2. If recompute triggers: one process recomputes while others continue using the stale value
3. If no recompute triggers: continues serving the cached value

### `StampedeConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `beta` | `float` (≥0) | `1.0` | Aggressiveness of early recompute (higher = more aggressive) |
| `delta` | `float` (≥0) | `0.5` | Minimum recompute window as fraction of TTL |

## Models

### `CacheEntry`

**File:** `core_infrastructure.cache.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key` | `str` (1–512) | *(required)* | Cache key |
| `value` | `Any` | `None` | Cached Python object |
| `expires_at` | `float` (≥0) | `time.monotonic()` | Monotonic expiry timestamp |
| `created_at` | `float` (≥0) | `time.monotonic()` | Monotonic creation timestamp |

Uses `time.monotonic()` for expiry tracking — immune to system clock adjustments. Call `is_expired()` to check:

```python
def is_expired(self) -> bool:
    return time.monotonic() >= self.expires_at
```

**Security:** `CacheEntry.value` is untyped (`Any`) — callers MUST NOT cache credentials, tokens, or PII without encryption.

---

### `CacheConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_ttl` | `int` (≥0) | `300` | Default TTL in seconds |
| `max_size` | `int` (≥0) | `10000` | Maximum entries before LRU eviction |
| `backend` | `Literal["memory","redis"]` | `"memory"` | Cache backend |

## Key Prefix Scoping

All cache keys are automatically prefixed with `cenf:cache:{namespace}:` for isolation:

| Manager | Namespace | Example Key |
|---------|-----------|-------------|
| AuthManager | `auth` | `cenf:cache:auth:jwks:https://auth.example.com/.well-known/jwks` |
| DatabaseManager | `db` | `cenf:cache:db:query:users_by_email:hash` |
| FeatureFlagManager | `flags` | `cenf:cache:flags:dark-mode:tenant=cntrs` |

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `MemoryCacheAdapter` | Python dict with LRU eviction | Dev/testing — in-process cache with TTL tracking |
| `RedisCacheAdapter` | Redis | Production — shared cache across multiple instances |

## Usage Example

```python
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter

# Bootstrap
cache = MemoryCacheAdapter(config_manager=config, logger_manager=logger)

# Simple get/set
cache.set("user:42", {"name": "Alice", "role": "admin"}, ttl=600)
user = cache.get("user:42")  # → {"name": "Alice", "role": "admin"}

# Cache miss returns None (NOT an error)
missing = cache.get("nonexistent")  # → None

# Check existence (TTL-aware)
if cache.exists("user:42"):
    logger.info("User 42 is cached")

# Delete (idempotent)
cache.delete("user:42")
cache.delete("nonexistent")  # no-op, no error

# Clear all
cache.clear()

# get_or_set with factory (RECOMMENDED pattern)
def fetch_user_from_db():
    # Expensive DB call
    return db.query("SELECT * FROM users WHERE id = 42")

user = cache.get_or_set(
    key="user:42",
    factory=fetch_user_from_db,
    ttl=300,
)
# If cached → returns cached value (HIT)
# If not cached → calls factory, caches result, returns it (MISS)
# If near expiry → XFetch probabilistic early recompute (stampede mitigation)
```

### Key Design Rules

```python
# ✅ Good: cache miss is normal flow
value = cache.get("key")
if value is None:
    value = compute_expensive()
    cache.set("key", value, ttl=300)

# ✅ Better: use get_or_set (same logic + stampede mitigation)
value = cache.get_or_set("key", compute_expensive, ttl=300)

# ❌ Bad: treating cache miss as an error
value = cache.get("key")
if value is None:
    raise Exception("Cache miss!")
```

## @ai-directive

- **Cache miss is NOT an error.** `get()` returns `None` — this is normal operation.
- `get_or_set()` MUST implement XFetch stampede mitigation. The factory callable MUST be compatible with sync execution.
- NEVER cache credentials, tokens, or PII without encryption. Cache adapters are in-memory by default — values are NOT encrypted.
- `CacheEntry.expires_at` uses `time.monotonic()`, not wall-clock time, to be immune to system clock jumps.

## Related

- [DatabaseManager](database-manager.md) — common `get_or_set` pattern for caching DB queries
- [AuthManager](auth-manager.md) — caches JWKS keys
- [ObservabilityManager](observability-manager.md) — hit/miss/stampede counters
- [LoggerManager](logger-manager.md) — DEBUG-level cache event logging
