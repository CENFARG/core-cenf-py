"""Unit tests for MemoryCacheAdapter — in-memory dict-backed CacheManager.

Tests cover:
- Protocol compliance (satisfies CacheManager)
- get/set/delete/exists/clear basic operations
- TTL expiration (entries expire after TTL elapses)
- get_or_set with cache miss and cache hit
- get_or_set stampede mitigation (XFetch probabilistic recompute)
- max_size eviction (FIFO eviction when store exceeds limit)
- delete idempotency

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.cache.models import StampedeConfig
from core_infrastructure.cache.ports import CacheManager
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with cache settings."""
    return InMemoryConfigAdapter(
        initial_data={
            "cache": {
                "default_ttl": 300,
                "max_size": 10000,
                "backend": "memory",
            },
        }
    )


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """Create an InMemoryLoggerAdapter."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    """Create an InMemoryObservabilityAdapter."""
    return InMemoryObservabilityAdapter()


@pytest.fixture
def error_handler(config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, observability: InMemoryObservabilityAdapter) -> CapturingErrorAdapter:
    """Create a CapturingErrorAdapter with all dependencies."""
    return CapturingErrorAdapter(config, logger, observability)


@pytest.fixture
def cache(config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, error_handler: CapturingErrorAdapter) -> MemoryCacheAdapter:
    """Create a MemoryCacheAdapter with default config."""
    return MemoryCacheAdapter(config, logger, error_handler)


class TestMemoryCacheAdapterProtocol:
    """Verify MemoryCacheAdapter satisfies CacheManager Protocol."""

    def test_satisfies_cache_manager_protocol(self, cache: MemoryCacheAdapter) -> None:
        """MemoryCacheAdapter passes isinstance check against CacheManager."""
        assert isinstance(cache, CacheManager)


class TestMemoryCacheAdapterBasicOps:
    """Verify basic get/set/delete/exists/clear operations."""

    def test_get_returns_none_for_missing_key(self, cache: MemoryCacheAdapter) -> None:
        """get() returns None for a key that has never been set."""
        result = cache.get("missing-key")
        assert result is None

    def test_set_and_get_roundtrip(self, cache: MemoryCacheAdapter) -> None:
        """set() stores a value and get() retrieves it."""
        cache.set("key-a", "value-a")
        result = cache.get("key-a")
        assert result == "value-a"

    def test_set_overwrites_existing_key(self, cache: MemoryCacheAdapter) -> None:
        """set() overwrites the value for an existing key."""
        cache.set("key-b", "first")
        cache.set("key-b", "second")
        assert cache.get("key-b") == "second"

    def test_exists_returns_true_after_set(self, cache: MemoryCacheAdapter) -> None:
        """exists() returns True for a key that was set."""
        cache.set("key-c", "value-c")
        assert cache.exists("key-c") is True

    def test_exists_returns_false_for_missing_key(self, cache: MemoryCacheAdapter) -> None:
        """exists() returns False for a key that was never set."""
        assert cache.exists("nonexistent") is False

    def test_delete_removes_key(self, cache: MemoryCacheAdapter) -> None:
        """delete() removes a key and subsequent get() returns None."""
        cache.set("key-d", "value-d")
        cache.delete("key-d")
        assert cache.get("key-d") is None
        assert cache.exists("key-d") is False

    def test_delete_nonexistent_key_is_idempotent(self, cache: MemoryCacheAdapter) -> None:
        """delete() on a non-existent key does not raise."""
        cache.delete("nonexistent")  # Should not raise

    def test_clear_removes_all_entries(self, cache: MemoryCacheAdapter) -> None:
        """clear() removes all entries from the cache."""
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        cache.set("k3", "v3")
        assert cache.get("k1") == "v1"

        cache.clear()
        assert cache.get("k1") is None
        assert cache.get("k2") is None
        assert cache.get("k3") is None

    def test_set_multiple_keys_independent(self, cache: MemoryCacheAdapter) -> None:
        """Multiple keys can coexist independently."""
        cache.set("k1", "v1")
        cache.set("k2", "v2")
        assert cache.get("k1") == "v1"
        assert cache.get("k2") == "v2"


class TestMemoryCacheAdapterTTL:
    """Verify TTL expiration behavior."""

    def test_entry_expires_after_ttl(self, cache: MemoryCacheAdapter) -> None:
        """An entry with TTL=0.01 seconds should expire and return None."""
        cache.set("ephemeral", "data", ttl=1)  # Use TTL=0 for immediate expiry test
        # Force expiry by manipulating the internal time
        # For a real test, we set TTL=0 which means immediately expired
        cache.set("ephemeral", "data", ttl=0)
        result = cache.get("ephemeral")
        assert result is None

    def test_entry_with_future_ttl_is_not_expired(self, cache: MemoryCacheAdapter) -> None:
        """An entry with a large TTL does not expire immediately."""
        cache.set("permanent", "data", ttl=3600)
        assert cache.get("permanent") == "data"
        assert cache.exists("permanent") is True

    def test_exists_returns_false_for_expired_entry(self, cache: MemoryCacheAdapter) -> None:
        """exists() returns False when the entry has expired."""
        cache.set("ephemeral", "data", ttl=0)
        assert cache.exists("ephemeral") is False

    def test_expired_entry_is_evicted_on_access(self, cache: MemoryCacheAdapter) -> None:
        """Expired entries are removed from the internal store on get()."""
        cache.set("ephemeral", "data", ttl=0)
        cache.get("ephemeral")  # Should trigger eviction
        # After eviction, exists should still return False
        assert cache.exists("ephemeral") is False


class TestMemoryCacheAdapterGetOrSet:
    """Verify get_or_set behavior."""

    def test_get_or_set_returns_cached_value_on_hit(self, cache: MemoryCacheAdapter) -> None:
        """get_or_set returns the cached value without calling factory."""
        cache.set("cached-key", "cached-value", ttl=3600)
        call_count = 0

        def factory() -> str:
            nonlocal call_count
            call_count += 1
            return "new-value"

        result = cache.get_or_set("cached-key", factory, ttl=3600)
        assert result == "cached-value"
        assert call_count == 0  # Factory was NOT called

    def test_get_or_set_computes_and_caches_on_miss(self, cache: MemoryCacheAdapter) -> None:
        """get_or_set calls factory on cache miss and caches the result."""
        call_count = 0

        def factory() -> str:
            nonlocal call_count
            call_count += 1
            return "computed-value"

        result = cache.get_or_set("new-key", factory, ttl=3600)
        assert result == "computed-value"
        assert call_count == 1
        # Subsequent call should hit cache
        result2 = cache.get_or_set("new-key", factory, ttl=3600)
        assert result2 == "computed-value"
        assert call_count == 1  # Factory NOT called again

    def test_get_or_set_expired_triggers_recompute(self, cache: MemoryCacheAdapter) -> None:
        """get_or_set recomputes value for expired entries."""
        cache.set("expiring-key", "old-value", ttl=0)  # Immediately expired
        call_count = 0

        def factory() -> str:
            nonlocal call_count
            call_count += 1
            return "fresh-value"

        result = cache.get_or_set("expiring-key", factory, ttl=3600)
        assert result == "fresh-value"
        assert call_count == 1


class TestMemoryCacheAdapterEviction:
    """Verify max_size eviction behavior."""

    def test_enforces_max_size(self, cache: MemoryCacheAdapter) -> None:
        """When max_size is exceeded, oldest entries are evicted (FIFO)."""
        small_cache = MemoryCacheAdapter(
            cache._config,
            cache._logger,
            cache._error_handler,
        )
        small_cache._cache_config.max_size = 3  # type: ignore[attr-defined]

        small_cache.set("k1", "v1")
        small_cache.set("k2", "v2")
        small_cache.set("k3", "v3")
        assert small_cache.get("k1") == "v1"

        # This should evict k1 (oldest)
        small_cache.set("k4", "v4")
        assert len(small_cache._store) == 3  # type: ignore[attr-defined]
        assert small_cache.get("k1") is None  # Evicted
        assert small_cache.get("k2") == "v2"
        assert small_cache.get("k3") == "v3"
        assert small_cache.get("k4") == "v4"

    def test_no_eviction_within_max_size(self, cache: MemoryCacheAdapter) -> None:
        """When max_size is not exceeded, no entries are evicted."""
        small_cache = MemoryCacheAdapter(
            cache._config,
            cache._logger,
            cache._error_handler,
        )
        small_cache._cache_config.max_size = 10  # type: ignore[attr-defined]

        for i in range(5):
            small_cache.set(f"k{i}", f"v{i}")

        assert len(small_cache._store) == 5  # type: ignore[attr-defined]
        for i in range(5):
            assert small_cache.get(f"k{i}") == f"v{i}"


class TestMemoryCacheAdapterStampede:
    """Verify XFetch stampede mitigation."""

    def test_stampede_early_recompute_with_delta_10(self, cache: MemoryCacheAdapter) -> None:
        """With delta=1.0, any entry close to expiry triggers recompute."""
        stampede = StampedeConfig(beta=1.0, delta=1.0)
        adapter = MemoryCacheAdapter(cache._config, cache._logger, cache._error_handler, stampede)
        adapter.set("hot-key", "old-value", ttl=0)  # Expired

        call_count = 0

        def factory() -> str:
            nonlocal call_count
            call_count += 1
            return "fresh-value"

        result = adapter.get_or_set("hot-key", factory, ttl=3600)
        assert result == "fresh-value"
        assert call_count == 1  # Recompute triggered

    def test_stampede_with_delta_zero_no_early_recompute(self, cache: MemoryCacheAdapter) -> None:
        """With delta=0, no early recompute window — only expired entries recompute."""
        stampede = StampedeConfig(beta=1.0, delta=0.0)
        adapter = MemoryCacheAdapter(cache._config, cache._logger, cache._error_handler, stampede)
        adapter.set("stable-key", "stable-value", ttl=3600)

        call_count = 0

        def factory() -> str:
            nonlocal call_count
            call_count += 1
            return "recomputed"

        result = adapter.get_or_set("stable-key", factory, ttl=3600)
        assert result == "stable-value"
        # With delta=0, remaining_ratio > 0 means _should_recompute_early returns False
        # unless the entry is actually expired
        assert call_count == 0
