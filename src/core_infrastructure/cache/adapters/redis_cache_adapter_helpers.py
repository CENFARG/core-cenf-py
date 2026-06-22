"""RedisCacheAdapter helpers — serialization, connection, and key utilities.

Extracted from ``redis_cache_adapter.py`` to comply with the 250-line
CENF rule. Contains no business logic — only infrastructure concerns:
Redis connection lifecycle, JSON serialization/deserialization, key
prefix building, and event-loop-safe Redis coroutine execution.

What: Extracted helpers for RedisCacheAdapter to reduce main module size.
Why: 250-line CENF rule compliance — pure refactoring, no behavior change.
Where: src/core_infrastructure/cache/adapters/redis_cache_adapter_helpers.py

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Redis exception type name — avoids hard import at module level (optional dep)
# ---------------------------------------------------------------------------
_REDIS_CONNECTION_ERROR = "ConnectionError"


def serialize_value(value: Any) -> str:
    """Serialize a Python value to a JSON string for Redis storage.

    Args:
        value: Any JSON-serializable Python object.

    Returns:
        str: JSON-encoded string.
    """
    return json.dumps(value, default=str)


def deserialize_value(raw: Any) -> Any:
    """Deserialize a value retrieved from Redis.

    Handles bytes → str decoding and JSON deserialization.

    Args:
        raw: The raw value from Redis (bytes, str, or None).

    Returns:
        Any: The deserialized Python object, or None if raw is None.
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def make_key(key: str, *, prefix: str = "") -> str:
    """Build a prefixed cache key.

    Args:
        key: The raw cache key.
        prefix: The key prefix to prepend (e.g., ``"cenf:cache:app:"``).

    Returns:
        str: The fully prefixed key.
    """
    return f"{prefix}{key}"


async def connect_redis(url: str) -> Any:
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


def clear_redis_namespace(
    redis_client: Any,
    key_prefix: str,
    in_memory: dict[str, Any],
    *,
    logger: Any,
) -> None:
    """Remove ALL entries with the adapter's key prefix via SCAN+DELETE.

    Uses SCAN with ``{prefix}*`` pattern to find and DELETE only keys
    belonging to this adapter's namespace. Other keys in the database
    are never touched.

    Args:
        redis_client: The Redis client instance (or None for in-memory only).
        key_prefix: The key prefix for namespace scoping.
        in_memory: The in-memory fallback dict (mutated).
        logger: LoggerManager instance for error logging.
    """
    in_memory.clear()
    if redis_client is None:
        return

    async def _clear_async() -> None:
        pattern = f"{key_prefix}*"
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(
                cursor, match=pattern, count=100
            )
            if keys:
                await redis_client.delete(*keys)
            if cursor == 0:
                break

    run_redis_sync(
        redis_client,
        _clear_async,
        key_prefix=key_prefix,
        logger=logger,
    )


def run_redis_sync(
    redis_client: Any,
    factory: Callable[[], Any],
    *,
    key_prefix: str,
    logger: Any,
) -> Any:
    """Run a Redis coroutine factory, safe for both sync and async contexts.

    The factory is a zero-argument callable that produces a coroutine
    (e.g., ``lambda: redis_client.get(key)``). This ensures exceptions
    from mock-based tests are caught inside the try block.

    When called from sync code (no running event loop), uses ``asyncio.run()``.
    When called from inside an existing event loop (e.g., async web framework),
    runs the coroutine in a separate thread to avoid ``RuntimeError``.

    Args:
        redis_client: The Redis client instance.
        factory: A callable that returns a coroutine.
        key_prefix: The key prefix for error context.
        logger: LoggerManager instance for error logging.

    Returns:
        The coroutine's result.

    Raises:
        TransientError: If Redis is unreachable.
    """
    from core_infrastructure.common.errors import TransientError

    if redis_client is None:
        raise TransientError("Redis not available — adapter is in fallback mode")

    async def _runner() -> Any:
        return await factory()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run()
        try:
            return asyncio.run(_runner())
        except Exception as exc:
            if type(exc).__name__ == _REDIS_CONNECTION_ERROR:
                logger.error("Redis operation failed", exc=exc)
                raise TransientError(
                    f"Redis operation failed: {exc}",
                    details={"key_prefix": key_prefix},
                ) from exc
            raise
    else:
        # Inside an event loop — run in a separate thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, _runner())
            try:
                return future.result()
            except Exception as exc:
                if type(exc).__name__ == _REDIS_CONNECTION_ERROR:
                    logger.error("Redis operation failed", exc=exc)
                    raise TransientError(
                        f"Redis operation failed: {exc}",
                        details={"key_prefix": key_prefix},
                    ) from exc
                raise
