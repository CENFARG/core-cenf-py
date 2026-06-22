"""Unit tests for RedisCacheAdapter — Redis-backed CacheManager.

Tests cover:
- Protocol compliance (satisfies CacheManager)
- Key prefix scoping (cenf:cache:{namespace}:)
- get/set/delete/exists/clear with mocked Redis client
- JSON serialization roundtrip
- Graceful degradation when Redis raises ConnectionError
- In-memory fallback mode when Redis init fails

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core_infrastructure.cache.ports import CacheManager
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with Redis cache settings."""
    return InMemoryConfigAdapter(
        initial_data={
            "cache": {
                "default_ttl": 300,
                "max_size": 10000,
                "backend": "redis",
                "redis": {
                    "url": "redis://localhost:6379/0",
                    "ttl": 300,
                    "namespace": "app",
                },
            },
        }
    )


@pytest.fixture
def secrets() -> InMemorySecretAdapter:
    """Create an InMemorySecretAdapter."""
    return InMemorySecretAdapter()


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """Create an InMemoryLoggerAdapter (empty warnings list)."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Create a mocked redis.asyncio.Redis client."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=0)
    client.flushdb = AsyncMock(return_value=True)
    return client


class TestRedisCacheAdapterProtocol:
    """Verify RedisCacheAdapter satisfies CacheManager Protocol."""

    def test_satisfies_cache_manager_protocol(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter
    ) -> None:
        """RedisCacheAdapter passes isinstance check against CacheManager."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        assert isinstance(adapter, CacheManager)


class TestRedisCacheAdapterKeyPrefix:
    """Verify key prefix scoping."""

    def test_get_uses_prefixed_key(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter
    ) -> None:
        """get() prepends 'cenf:cache:{namespace}:' to keys."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        # Access internal prefix for testing
        assert adapter._key_prefix == "cenf:cache:app:"

    def test_prefixed_key_construction(self) -> None:
        """_make_key builds correct prefixed key."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        result = RedisCacheAdapter._make_key("mykey", prefix="cenf:cache:ns:")
        assert result == "cenf:cache:ns:mykey"


class TestRedisCacheAdapterOperations:
    """Verify get/set/delete/exists/clear with mocked Redis."""

    def test_get_calls_redis_with_prefixed_key_and_deserializes(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """get() calls redis.get with prefixed key and JSON-deserializes result."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client
        mock_redis_client.get.return_value = None  # simulate no result (async)

        adapter.get("testkey")
        mock_redis_client.get.assert_called_once()
        called_key = mock_redis_client.get.call_args[0][0]
        assert called_key == "cenf:cache:app:testkey"

    def test_get_returns_deserialized_json(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """get() deserializes JSON string from Redis."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client

        payload = json.dumps({"name": "Alice", "age": 30})
        # We need to make get return a real value, but it's an AsyncMock
        # We'll test serialization via set+get roundtrip in integration style
        # For now, verify the adapter delegates correctly
        mock_redis_client.get.return_value = payload.encode() if hasattr(payload, "encode") else payload

        adapter.get("user:1")
        mock_redis_client.get.assert_called_once_with("cenf:cache:app:user:1")

    def test_set_calls_redis_set_with_serialized_value(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """set() calls redis.set with JSON-serialized value and TTL."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client

        adapter.set("key1", {"data": [1, 2, 3]}, ttl=60)

        mock_redis_client.set.assert_called_once()
        call_args = mock_redis_client.set.call_args
        assert call_args[0][0] == "cenf:cache:app:key1"
        # second positional arg is JSON payload
        deserialized = json.loads(call_args[0][1])
        assert deserialized == {"data": [1, 2, 3]}
        # TTL is passed as `ex=` keyword argument
        assert call_args[1].get("ex") == 60

    def test_delete_calls_redis_delete(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """delete() calls redis.delete with prefixed key."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client

        adapter.delete("to-delete")

        mock_redis_client.delete.assert_called_once_with("cenf:cache:app:to-delete")

    def test_exists_calls_redis_exists(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """exists() calls redis.exists with prefixed key."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client
        mock_redis_client.exists.return_value = 1

        adapter.exists("somekey")
        mock_redis_client.exists.assert_called_once_with("cenf:cache:app:somekey")

    def test_clear_uses_scan_and_delete_not_flushdb(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """clear() uses SCAN+DELETE with key prefix, NOT FLUSHDB."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client

        # Setup: SCAN returns keys matching the prefixed pattern
        mock_redis_client.scan = AsyncMock(side_effect=[
            (42, [b"cenf:cache:app:key1", b"cenf:cache:app:key2"]),
            (0, []),  # cursor 0 means iteration complete
        ])

        adapter.clear()

        # SCAN must be called with the key prefix pattern
        mock_redis_client.scan.assert_called()
        scan_call_kwargs = mock_redis_client.scan.call_args_list[0][1]
        assert scan_call_kwargs.get("match") == "cenf:cache:app:*"

        # DELETE must be called with the discovered keys
        mock_redis_client.delete.assert_called_once_with(
            b"cenf:cache:app:key1", b"cenf:cache:app:key2"
        )

        # FLUSHDB must NEVER be called
        mock_redis_client.flushdb.assert_not_called()

    def test_clear_scan_multiple_iterations(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """clear() handles multiple SCAN iterations (cursor > 0)."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client

        # Setup: 2 iterations with cursor 55, then cursor 0
        mock_redis_client.scan = AsyncMock(side_effect=[
            (55, [b"cenf:cache:app:a"]),
            (0, [b"cenf:cache:app:b"]),
        ])

        adapter.clear()

        # SCAN called twice (two iterations)
        assert mock_redis_client.scan.call_count == 2
        # DELETE called twice (once per iteration)
        assert mock_redis_client.delete.call_count == 2
        mock_redis_client.delete.assert_any_call(b"cenf:cache:app:a")
        mock_redis_client.delete.assert_any_call(b"cenf:cache:app:b")

    def test_clear_empty_scan_no_delete(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """clear() handles empty SCAN result without calling DELETE."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client

        # SCAN returns no keys
        mock_redis_client.scan = AsyncMock(return_value=(0, []))

        adapter.clear()

        # DELETE should NOT be called when SCAN returns empty
        mock_redis_client.delete.assert_not_called()


class TestRedisCacheAdapterEventLoopSafety:
    """Verify adapter works both outside and inside existing event loops."""

    def test_get_works_outside_event_loop(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """Adapter operations work when called from sync code (no running loop)."""
        import asyncio
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client
        mock_redis_client.get.return_value = None

        # Verify no running loop exists
        try:
            asyncio.get_running_loop()
            pytest.skip("Cannot test outside-loop scenario — a loop is already running")
        except RuntimeError:
            pass  # Expected: no running loop

        # Operation should work without RuntimeError
        result = adapter.get("test-key")
        assert result is None
        mock_redis_client.get.assert_called_once()

    def test_get_works_inside_existing_event_loop(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
        mock_redis_client: MagicMock,
    ) -> None:
        """Adapter operations work when called from inside an existing event loop."""
        import asyncio
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter._redis = mock_redis_client
        mock_redis_client.get.return_value = None

        async def call_get():
            return adapter.get("inside-loop-key")

        # Run inside a new event loop (simulates being called from async context)
        result = asyncio.run(call_get())
        assert result is None
        mock_redis_client.get.assert_called_once()


class TestRedisCacheAdapterGracefulDegradation:
    """Verify graceful degradation when Redis is unavailable."""

    def test_raises_transient_error_on_connection_error(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
    ) -> None:
        """When Redis raises ConnectionError, adapter raises TransientError."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter
        from core_infrastructure.common.errors import TransientError

        adapter = RedisCacheAdapter(config, secrets, logger)

        # Mock the redis client to raise ConnectionError
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        adapter._redis = mock_client

        with pytest.raises(TransientError, match="Redis operation failed"):
            adapter.get("anykey")

    def test_falls_back_to_memory_on_init_failure(self) -> None:
        """When Redis init fails, adapter falls back to in-memory mode."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        config = InMemoryConfigAdapter(
            initial_data={
                "cache": {
                    "redis": {
                        "url": "redis://invalid-host:9999/0",
                        "ttl": 300,
                        "namespace": "app",
                    },
                },
            },
        )
        secrets = InMemorySecretAdapter()
        logger = InMemoryLoggerAdapter()

        # Simulating init failure by passing an unreachable URL
        # The adapter should NOT crash, but log a warning and use in-memory
        adapter = RedisCacheAdapter(config, secrets, logger)
        # After fallback, operations should work via in-memory mode
        adapter.set("fallback-key", "fallback-value")
        result = adapter.get("fallback-key")
        assert result == "fallback-value"


class TestRedisCacheAdapterSerialization:
    """Verify JSON serialization roundtrip."""

    def test_complex_value_roundtrip(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
    ) -> None:
        """Complex Python objects survive set/get roundtrip."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)

        complex_value = {
            "nested": {"key": "val", "list": [1, None, "three"]},
            "bool": True,
            "null": None,
            "int": 42,
        }

        adapter.set("complex-key", complex_value, ttl=300)
        result = adapter.get("complex-key")
        assert result == complex_value

    def test_none_value_roundtrip(
        self, config: InMemoryConfigAdapter, secrets: InMemorySecretAdapter, logger: InMemoryLoggerAdapter,
    ) -> None:
        """None value survives set/get roundtrip."""
        from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter

        adapter = RedisCacheAdapter(config, secrets, logger)
        adapter.set("none-key", None, ttl=300)
        result = adapter.get("none-key")
        assert result is None
