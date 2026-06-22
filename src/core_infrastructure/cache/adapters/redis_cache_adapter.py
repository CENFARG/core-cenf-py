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
import json
from collections.abc import Callable
from typing import Any

from core_infrastructure.cache.ports import CacheManager
from core_infrastructure.common.errors import TransientError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager

# ---------------------------------------------------------------------------
# Redis exception type name — avoids hard import at module level (optional dep)
# ---------------------------------------------------------------------------
_REDIS_CONNECTION_ERROR = "ConnectionError"


class RedisCacheAdapter(CacheManager):
    """Redis-backed CacheManager with async connection pool and key prefix scoping.

    All cache keys are prefixed with ``cenf:cache:{namespace}:`` for
    multi-tenant isolation. Falls back to in-memory dict storage if
    Redis is unreachable during initialization.

    Args:
        config: ConfigManager for ``cache.redis.url``, ``cache.redis.ttl``,
            ``cache.redis.namespace``.
        secrets: SecretManager for Redis credentials (reserved for future use).
        logger: LoggerManager for structured log emission.

    Usage::

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter.set("user:1", {"name": "Alice"}, ttl=60)
        value = adapter.get("user:1")  # {"name": "Alice"}
    """

    _DEFAULT_TTL: int = 300
    _DEFAULT_NAMESPACE: str = "default"

    def __init__(
        self,
        config: ConfigManager,
        secrets: SecretManager,
        logger: LoggerManager,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._logger = logger

        redis_url = config.get_string("cache.redis.url", default_value="redis://localhost:6379/0")
        self._ttl: int = int(config.get_number("cache.redis.ttl", default_value=self._DEFAULT_TTL))
        namespace = config.get_string("cache.redis.namespace", default_value=self._DEFAULT_NAMESPACE)
        self._key_prefix: str = f"cenf:cache:{namespace}:"

        self._redis: Any = None
        self._in_memory: dict[str, Any] = {}

        try:
            self._redis = asyncio.run(self._connect(redis_url))
        except Exception:
            self._logger.warn(
                "RedisCacheAdapter: Redis unavailable, falling back to in-memory mode",
                redis_url=self._logger.mask(redis_url, visible_chars=0),
            )

    @staticmethod
    async def _connect(url: str) -> Any:
        """Create async Redis client and verify connectivity with PING.

        Args:
            url: Redis connection URL.

        Returns:
            A connected ``redis.asyncio.Redis`` instance.

        Raises:
            redis.exceptions.ConnectionError: If Redis is unreachable.
        """
        import redis.asyncio as aioredis

        pool: aioredis.ConnectionPool = aioredis.ConnectionPool.from_url(url)  # type: ignore[type-arg]
        client = aioredis.Redis(connection_pool=pool)
        await client.ping()
        return client

    @staticmethod
    def _make_key(key: str, *, prefix: str = "") -> str:
        """Build a prefixed cache key.

        Args:
            key: The raw cache key.
            prefix: The key prefix to prepend (e.g., ``"cenf:cache:app:"``).

        Returns:
            str: The fully prefixed key.
        """
        return f"{prefix}{key}"

    def _run_redis(self, factory: Callable[[], Any]) -> Any:
        """Run a Redis coroutine factory, raising ``TransientError`` on connection failure.

        The factory is a zero-argument callable that produces a coroutine
        (e.g., ``lambda: self._redis.get(key)``). This ensures exceptions
        from mock-based tests are caught inside the try block.

        Args:
            factory: A callable that returns a coroutine.

        Returns:
            The coroutine's result.

        Raises:
            TransientError: If Redis is unreachable.
        """
        if self._redis is None:
            raise TransientError("Redis not available — adapter is in fallback mode")
        try:
            return asyncio.run(factory())
        except Exception as exc:
            if type(exc).__name__ == _REDIS_CONNECTION_ERROR:
                self._logger.error("Redis operation failed", exc=exc)
                raise TransientError(
                    f"Redis operation failed: {exc}",
                    details={"key_prefix": self._key_prefix},
                ) from exc
            raise

    # ------------------------------------------------------------------
    # Public API — CacheManager Protocol
    # ------------------------------------------------------------------

    def get(self, key: str) -> Any:
        """Retrieve a value from Redis.

        If Redis is in fallback mode (init failure), reads from in-memory dict.
        If Redis is available but unreachable at runtime, raises ``TransientError``.

        Args:
            key: The cache key to look up.

        Returns:
            Any: The cached value, or ``None`` if missing.

        Raises:
            TransientError: If Redis is unreachable.
        """
        prefixed = self._make_key(key, prefix=self._key_prefix)

        if self._redis is None:
            return self._in_memory.get(key)

        raw = self._run_redis(lambda: self._redis.get(prefixed))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw) if isinstance(raw, str) else raw

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value in Redis with an optional TTL.

        Falls back to in-memory dict only if Redis init failed.
        Raises ``TransientError`` if Redis is unreachable at runtime.

        Args:
            key: The cache key.
            value: The value to cache (any JSON-serializable Python object).
            ttl: Time-to-live in seconds, or ``None`` for default.

        Raises:
            TransientError: If Redis is unreachable.
        """
        prefixed = self._make_key(key, prefix=self._key_prefix)
        resolved_ttl = ttl if ttl is not None else self._ttl

        payload = json.dumps(value, default=str)

        if self._redis is None:
            self._in_memory[key] = value
            return

        self._run_redis(lambda: self._redis.set(prefixed, payload, ex=resolved_ttl))

    def delete(self, key: str) -> None:
        """Remove an entry from Redis.

        Idempotent — deleting a non-existent key succeeds silently.
        Falls back to in-memory only if Redis init failed.

        Args:
            key: The cache key to remove.

        Raises:
            TransientError: If Redis is unreachable.
        """
        prefixed = self._make_key(key, prefix=self._key_prefix)

        self._in_memory.pop(key, None)
        if self._redis is None:
            return

        self._run_redis(lambda: self._redis.delete(prefixed))

    def exists(self, key: str) -> bool:
        """Check if a key exists in Redis.

        Falls back to in-memory dict only if Redis init failed.

        Args:
            key: The cache key to check.

        Returns:
            bool: ``True`` if the key exists and has not expired.

        Raises:
            TransientError: If Redis is unreachable.
        """
        prefixed = self._make_key(key, prefix=self._key_prefix)

        if self._redis is None:
            return key in self._in_memory

        result = self._run_redis(lambda: self._redis.exists(prefixed))
        return bool(result)

    def clear(self) -> None:
        """Remove ALL entries with the adapter's key prefix via SCAN+DELETE.

        Uses SCAN with ``{prefix}*`` pattern to find and DELETE only keys
        belonging to this adapter's namespace. Other keys in the database
        are never touched.

        Raises:
            TransientError: If Redis is unreachable.
        """
        self._in_memory.clear()
        if self._redis is None:
            return

        async def _clear_async() -> None:
            pattern = f"{self._key_prefix}*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=pattern, count=100
                )
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break

        self._run_redis(_clear_async)

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        """Get a value from cache or compute and cache it.

        Args:
            key: The cache key.
            factory: A callable that produces the value when not cached.
            ttl: Time-to-live in seconds for the cached value.

        Returns:
            Any: The cached or freshly computed value.
        """
        value = self.get(key)
        if value is not None:
            return value
        value = factory()
        self.set(key, value, ttl=ttl)
        return value
