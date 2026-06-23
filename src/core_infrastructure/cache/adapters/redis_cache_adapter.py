"""RedisCacheAdapter — production Redis-backed CacheManager with async connection pool.

Provides a Redis-backed CacheManager implementation using ``redis.asyncio``
with connection pooling, key prefix scoping, and graceful degradation to
in-memory mode when Redis is unreachable.

Security: Redis connection uses SecretManager for credentials. NEVER store
    raw Redis credentials in config.
Observability: All operations log at DEBUG level via LoggerManager.
@ai-directive: Public methods are sync (matching CacheManager Protocol).
    Internal bridging to async Redis uses ``asyncio.run()`` per call.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any

from core_infrastructure.cache.adapters.redis_cache_adapter_helpers import (
    clear_redis_namespace,
    connect_redis,
    deserialize_value,
    make_key,
    run_redis_sync,
    serialize_value,
)
from core_infrastructure.cache.ports import CacheManager
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager


class RedisCacheAdapter(CacheManager):
    """Redis-backed CacheManager with async connection pool and key prefix scoping.

    All cache keys are prefixed with ``cenf:cache:{namespace}:`` for
    multi-tenant isolation. Falls back to in-memory dict if Redis is
    unreachable during initialization.

    Usage::
        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter.set("user:1", {"name": "Alice"}, ttl=60)
        value = adapter.get("user:1")  # {"name": "Alice"}
    """

    _DEFAULT_TTL: int = 300
    _DEFAULT_NAMESPACE: str = "default"

    @staticmethod
    def _make_key(key: str, *, prefix: str = "") -> str:
        """Build a prefixed cache key (delegates to helpers.make_key)."""
        return make_key(key, prefix=prefix)

    def __init__(
        self,
        config: ConfigManager,
        secrets: SecretManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager | None = None,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._logger = logger
        self._error_handler = error_handler

        redis_url = config.get_string("cache.redis.url", default_value="redis://localhost:6379/0")
        self._ttl: int = int(config.get_number("cache.redis.ttl", default_value=self._DEFAULT_TTL))
        namespace = config.get_string("cache.redis.namespace", default_value=self._DEFAULT_NAMESPACE)
        self._key_prefix: str = f"cenf:cache:{namespace}:"

        self._redis: Any = None
        self._in_memory: dict[str, Any] = {}
        self._locks: dict[str, threading.Lock] = {}

        try:
            self._redis = asyncio.run(connect_redis(redis_url))
        except Exception:
            self._logger.warn(
                "RedisCacheAdapter: Redis unavailable, falling back to in-memory mode",
                redis_url=self._logger.mask(redis_url, visible_chars=0),
            )

        # Apply error handler decorator to public methods if available
        if self._error_handler is not None:
            self.get = self._error_handler.handle_errors()(self.get)  # type: ignore[method-assign]
            self.set = self._error_handler.handle_errors()(self.set)  # type: ignore[method-assign]
            self.delete = self._error_handler.handle_errors()(self.delete)  # type: ignore[method-assign]

    # ------------------------------------------------------------------
    # Public API — CacheManager Protocol
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any:
        """Retrieve a value from Redis or in-memory fallback."""
        prefixed = make_key(key, prefix=self._key_prefix)
        if self._redis is None:
            return self._in_memory.get(key)
        raw = run_redis_sync(
            self._redis, lambda: self._redis.get(prefixed),
            key_prefix=self._key_prefix, logger=self._logger,
        )
        return deserialize_value(raw)

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in Redis with optional TTL."""
        prefixed = make_key(key, prefix=self._key_prefix)
        resolved_ttl = ttl if ttl is not None else self._ttl
        payload = serialize_value(value)
        if self._redis is None:
            self._in_memory[key] = value
            return
        run_redis_sync(
            self._redis, lambda: self._redis.set(prefixed, payload, ex=resolved_ttl),
            key_prefix=self._key_prefix, logger=self._logger,
        )

    def delete(self, key: str) -> None:
        """Remove an entry from Redis. Idempotent."""
        prefixed = make_key(key, prefix=self._key_prefix)
        self._in_memory.pop(key, None)
        if self._redis is None:
            return
        run_redis_sync(
            self._redis, lambda: self._redis.delete(prefixed),
            key_prefix=self._key_prefix, logger=self._logger,
        )

    def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        prefixed = make_key(key, prefix=self._key_prefix)
        if self._redis is None:
            return key in self._in_memory
        result = run_redis_sync(
            self._redis, lambda: self._redis.exists(prefixed),
            key_prefix=self._key_prefix, logger=self._logger,
        )
        return bool(result)

    def clear(self) -> None:
        """Remove ALL entries with the adapter's key prefix via SCAN+DELETE (delegates to helpers)."""
        clear_redis_namespace(
            self._redis,
            self._key_prefix,
            self._in_memory,
            logger=self._logger,
        )

    def _get_lock(self, key: str) -> threading.Lock:
        """Get or create a mutex for a cache key to prevent stampede.

        Locks are created lazily and cached in ``self._locks``. Each key
        gets its own lock so different keys do not block each other.

        Args:
            key: The cache key (un-prefixed).

        Returns:
            threading.Lock: A mutex for this specific cache key.
        """
        if key not in self._locks:
            self._locks[key] = threading.Lock()
        return self._locks[key]

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        """Get a value from cache or compute and cache it.

        Protected by a per-key mutex to prevent thundering herd: only one
        caller computes the value while others wait and retrieve the cached
        result.

        Args:
            key: The cache key.
            factory: A callable that produces the value when not cached.
            ttl: Time-to-live in seconds for the cached value.

        Returns:
            Any: The cached or freshly computed value.
        """
        lock = self._get_lock(key)
        with lock:
            value = self.get(key)
            if value is not None:
                return value
            value = factory()
            self.set(key, value, ttl=ttl)
            return value
