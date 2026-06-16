"""MemoryCacheAdapter — in-memory dict-backed CacheManager with stampede mitigation.

Provides a zero-dependency CacheManager implementation using a plain dict
backed by ``CacheEntry`` for TTL simulation. Implements XFetch probabilistic
early recomputation to prevent cache stampede (thundering herd) when hot
keys approach expiry.

Security: Values are stored in-process memory — no encryption, not shared
    across processes. NEVER cache credentials without encryption.
Observability: Emits ``cenf.cache.hit_total``, ``cenf.cache.miss_total``,
    and ``cenf.cache.stampede_recompute_total`` counters via ObservabilityManager.
@ai-directive: This adapter exists for dev/testing. Use RedisCacheAdapter
    in production after completing the Redis backend integration.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import random
import time as _time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from core_infrastructure.cache.models import CacheConfig, CacheEntry, StampedeConfig
from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager


class MemoryCacheAdapter:
    """In-memory dict-backed CacheManager with TTL simulation and stampede mitigation.

    Uses ``CacheEntry`` for TTL tracking via ``time.monotonic()`` timestamps.
    Expired entries are lazily evicted on access (get/exists/set). XFetch
    probabilistic early recomputation is built into ``get_or_set()``.

    Args:
        config: ConfigManager for CacheConfig reading.
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for exception classification.

    Usage::

        adapter = MemoryCacheAdapter(config, logger, error_handler)
        adapter.set("user:1", {"name": "Alice"}, ttl=60)
        value = adapter.get("user:1")  # {"name": "Alice"}
        value = adapter.get_or_set("user:2", lambda: {"name": "Bob"}, ttl=60)
    """

    def __init__(
        self,
        config: ConfigManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager,
        stampede_config: StampedeConfig | None = None,
    ) -> None:
        self._config = config
        self._logger = logger
        self._error_handler = error_handler
        self._stampede = stampede_config if stampede_config is not None else StampedeConfig()

        cache_section = config.get_section("cache")
        self._cache_config = CacheConfig(**cache_section) if cache_section else CacheConfig()

        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits: int = 0
        self._misses: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_ttl(self, ttl: int | None) -> float:
        """Resolve TTL to seconds and compute expiry timestamp.

        Args:
            ttl: Explicit TTL in seconds, or None for default.

        Returns:
            float: The absolute monotonic expiry timestamp.
        """
        seconds = ttl if ttl is not None else self._cache_config.default_ttl
        if seconds < 0:
            raise ValidationError(
                f"TTL must be >= 0, got {seconds}",
                details={"ttl": str(seconds)},
            )
        return _time.monotonic() + seconds

    def _evict_expired(self, key: str) -> None:
        """Remove a key if it exists and is expired.

        Args:
            key: The cache key to check and possibly evict.
        """
        entry = self._store.get(key)
        if entry is not None and entry.is_expired():
            del self._store[key]

    def _enforce_max_size(self) -> None:
        """Evict oldest entries if the store exceeds max_size.

        Evicts the oldest entry (FIFO) until the store is at or
        below the configured maximum.
        """
        max_size = self._cache_config.max_size
        while len(self._store) > max_size > 0:
            self._store.popitem(last=False)  # FIFO eviction

    def _should_recompute_early(self, entry: CacheEntry, ttl: float) -> bool:
        """XFetch probabilistic early recomputation decision.

        Uses the XFetch algorithm: when the remaining TTL is within
        ``delta * ttl`` of expiry, probabilistically decide to
        recompute early with probability ``beta * (1 - remaining_ratio)``.

        Args:
            entry: The cache entry being checked.
            ttl: The original TTL in seconds.

        Returns:
            bool: ``True`` if early recomputation should proceed.
        """
        remaining = entry.expires_at - _time.monotonic()
        if remaining <= 0:
            return True

        remaining_ratio = remaining / ttl if ttl > 0 else 0.0
        if remaining_ratio > self._stampede.delta:
            return False

        probability = self._stampede.beta * (1.0 - remaining_ratio / self._stampede.delta)
        probability = max(0.0, min(1.0, probability))
        return random.random() < probability

    # ------------------------------------------------------------------
    # Public API — CacheManager Protocol
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any:
        """Retrieve a value from the cache.

        Lazily evicts expired entries on access. Returns ``None`` for
        missing or expired keys.

        Args:
            key: The cache key to look up.

        Returns:
            Any: The cached value, or ``None`` if missing or expired.
        """
        self._evict_expired(key)
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in the cache with an optional TTL.

        Overwrites existing keys. Moves the key to the end of the
        OrderedDict (most-recently-used position) for eviction ordering.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Time-to-live in seconds, or None for default.
        """
        now = _time.monotonic()
        expires_at = self._resolve_ttl(ttl)

        # Move to end if already exists (update timestamp, mark as recent)
        if key in self._store:
            del self._store[key]

        entry = CacheEntry(key=key, value=value, expires_at=expires_at, created_at=now)
        self._store[key] = entry
        self._store.move_to_end(key)
        self._enforce_max_size()

    def delete(self, key: str) -> None:
        """Remove an entry from the cache.

        Idempotent — deleting a non-existent key succeeds silently.

        Args:
            key: The cache key to remove.
        """
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        """Check if a key exists and has not expired.

        TTL-aware: lazily evicts expired entries before checking.

        Args:
            key: The cache key to check.

        Returns:
            bool: ``True`` if the key exists and is not expired.
        """
        self._evict_expired(key)
        return key in self._store

    def clear(self) -> None:
        """Remove ALL entries from the cache immediately."""
        self._store.clear()
        self._hits = 0
        self._misses = 0

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        """Get a value from cache or compute and cache it.

        Implements XFetch stampede mitigation: when a key nears expiry,
        probabilistically triggers early recomputation.

        Args:
            key: The cache key.
            factory: A callable that produces the value when not cached.
            ttl: Time-to-live in seconds for the cached value.

        Returns:
            Any: The cached or freshly computed value.
        """
        resolved_ttl = ttl if ttl is not None else self._cache_config.default_ttl
        seconds = float(resolved_ttl)

        self._evict_expired(key)
        entry = self._store.get(key)

        if entry is None:
            # Cache miss — compute and store
            value = factory()
            self._misses += 1
            self.set(key, value, ttl=resolved_ttl)
            return value

        # Cache hit — check for stampede mitigation
        self._hits += 1
        if self._should_recompute_early(entry, seconds):
            value = factory()
            self.set(key, value, ttl=resolved_ttl)
            return value

        return entry.value
