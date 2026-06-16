"""CacheManager Protocol — the contract every cache adapter must satisfy.

Defines the key-value cache interface consumed by all infrastructure managers
that need temporary data storage with TTL support. The Protocol includes
stampede mitigation via the XFetch algorithm in get_or_set().

Security: NEVER cache credentials, tokens, or PII without encryption.
    Cache adapters are in-memory by default — values are not encrypted.
Observability: All get/set/delete/expiry events are logged at DEBUG level.
@ai-directive: get_or_set() MUST implement XFetch stampede mitigation.
    The factory callable MUST be async-compatible for I/O-bound value generation.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheManager(Protocol):
    """Key-value cache contract with TTL and stampede mitigation.

    All infrastructure managers that need temporary data storage consume
    this interface. Concrete adapters provide in-memory dict (dev/testing)
    or Redis backend (production).

    Rules:
        - get() returns None for missing or expired keys — never raises.
        - set() overwrites existing keys; TTL is optional, defaults to CacheConfig.default_ttl.
        - delete() is idempotent — deleting a non-existent key succeeds silently.
        - exists() returns False for expired entries (TTL-aware).
        - clear() removes ALL entries immediately.
        - get_or_set() implements XFetch probabilistic early recompute to prevent
          stampede (thundering herd) when a hot key nears expiry.

    @ai-directive: All methods are synchronous. get_or_set() factory may be
        sync or async; sync factories are called directly, async factories
        must be managed by the caller (this Protocol does NOT mandate asyncio).
    """

    def get(self, key: str) -> Any:
        """Retrieve a value from the cache.

        Args:
            key: The cache key to look up.

        Returns:
            Any: The cached value, or ``None`` if missing or expired.
        """
        ...

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in the cache with an optional TTL.

        Args:
            key: The cache key.
            value: The value to cache (any Python object).
            ttl: Time-to-live in seconds. If None, uses ``CacheConfig.default_ttl``.
        """
        ...

    def delete(self, key: str) -> None:
        """Remove an entry from the cache.

        Idempotent — deleting a non-existent key succeeds silently.

        Args:
            key: The cache key to remove.
        """
        ...

    def exists(self, key: str) -> bool:
        """Check if a key exists and has not expired.

        TTL-aware: returns ``False`` for expired entries even if they
        have not been evicted yet.

        Args:
            key: The cache key to check.

        Returns:
            bool: ``True`` if the key exists and is not expired.
        """
        ...

    def clear(self) -> None:
        """Remove ALL entries from the cache immediately.

        Observability: Emits ``cenf.cache.clear_total`` counter.
        """
        ...

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        """Get a value from cache or compute and cache it.

        Implements XFetch stampede mitigation: when a key is close to
        expiry, probabilistically recompute early to prevent thundering herd.

        Args:
            key: The cache key.
            factory: A callable that produces the value when not cached.
            ttl: Time-to-live in seconds for the cached value.

        Returns:
            Any: The cached or freshly computed value.

        Observability: Emits ``cenf.cache.hit_total`` and ``cenf.cache.miss_total``
            counters. Probabilistic early recompute emits
            ``cenf.cache.stampede_recompute_total``.
        """
        ...
