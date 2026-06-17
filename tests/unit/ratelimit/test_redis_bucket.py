"""Unit tests for Redis-backed TokenBucketAdapter.

Tests cover:
- Bucket state persists across adapter instances (same Redis key via MemoryCacheAdapter)
- Atomic token decrement under concurrent access
- Graceful fallback when Redis (CacheManager) is unavailable

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.config.adapters.in_memory_config_adapter import (
    InMemoryConfigAdapter,
)
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import (
    InMemoryLoggerAdapter,
)
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.ratelimit.adapters.token_bucket_adapter import (
    TokenBucketAdapter,
)


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    return InMemoryConfigAdapter(
        initial_data={
            "ratelimit": {
                "default_capacity": 100,
                "default_refill_rate": 10.0,
                "redis_enabled": True,
            },
        },
    )


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    return InMemoryLoggerAdapter()


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    return InMemoryObservabilityAdapter()


@pytest.fixture
def error_handler(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
    observability: InMemoryObservabilityAdapter,
) -> CapturingErrorAdapter:
    return CapturingErrorAdapter(config, logger, observability)


@pytest.fixture
def cache_manager(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
    error_handler: CapturingErrorAdapter,
) -> MemoryCacheAdapter:
    return MemoryCacheAdapter(
        config=config,
        logger=logger,
        error_handler=error_handler,
    )


@pytest.fixture
def adapter_with_redis(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
    error_handler: CapturingErrorAdapter,
    cache_manager: MemoryCacheAdapter,
) -> TokenBucketAdapter:
    return TokenBucketAdapter(config, logger, error_handler, cache=cache_manager)


class TestRedisBucketPersistence:
    """Verify bucket state persists across adapter instances via shared cache."""

    @pytest.mark.asyncio
    async def test_bucket_state_persists_across_instances(
        self,
        config: InMemoryConfigAdapter,
        logger: InMemoryLoggerAdapter,
        error_handler: CapturingErrorAdapter,
        cache_manager: MemoryCacheAdapter,
    ) -> None:
        """After consuming tokens in one adapter, a second adapter sees the same state."""
        adapter1 = TokenBucketAdapter(config, logger, error_handler, cache=cache_manager)
        adapter2 = TokenBucketAdapter(config, logger, error_handler, cache=cache_manager)

        adapter1.configure_bucket("persist-test", capacity=10, refill_rate=0.1)

        # Consume 5 tokens from adapter1
        for _ in range(5):
            await adapter1.is_allowed("persist-test")

        # adapter2 should see the same consumed tokens via shared Redis key
        remaining = await adapter2.get_remaining("persist-test")
        assert remaining == 5

    @pytest.mark.asyncio
    async def test_redis_key_format(
        self,
        config: InMemoryConfigAdapter,
        logger: InMemoryLoggerAdapter,
        error_handler: CapturingErrorAdapter,
        cache_manager: MemoryCacheAdapter,
    ) -> None:
        """The cache key for a bucket follows cenf:ratelimit:{bucket_key} format."""
        adapter = TokenBucketAdapter(config, logger, error_handler, cache=cache_manager)
        adapter.configure_bucket("api:/verify-key", capacity=5, refill_rate=1.0)

        # The cache should contain the key with cenf:ratelimit: prefix
        assert cache_manager.exists("cenf:ratelimit:api:/verify-key") is True


class TestAtomicTokenDecrement:
    """Verify token decrement is atomic under concurrent access with Redis."""

    @pytest.mark.asyncio
    async def test_concurrent_decrement_with_redis(
        self,
        adapter_with_redis: TokenBucketAdapter,
    ) -> None:
        """Concurrent is_allowed calls against Redis do not corrupt state."""
        adapter_with_redis.configure_bucket("concurrent-redis", capacity=200, refill_rate=100.0)

        async def consume():
            results = []
            for _ in range(20):
                r = await adapter_with_redis.is_allowed("concurrent-redis")
                results.append(r)
            return results

        tasks = [asyncio.create_task(consume()) for _ in range(5)]
        all_results = []
        for t in tasks:
            all_results.extend(await t)

        true_count = sum(1 for r in all_results if r is True)
        remaining = await adapter_with_redis.get_remaining("concurrent-redis")

        assert true_count + remaining == 200


class TestGracefulFallback:
    """Verify fallback to in-memory when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_fallback_when_cache_fails(
        self,
        config: InMemoryConfigAdapter,
        logger: InMemoryLoggerAdapter,
        error_handler: CapturingErrorAdapter,
    ) -> None:
        """When CacheManager operations raise, adapter falls back to in-memory."""
        broken_cache = MagicMock()
        broken_cache.get.side_effect = RuntimeError("Redis connection refused")
        broken_cache.set.side_effect = RuntimeError("Redis connection refused")
        broken_cache.exists.side_effect = RuntimeError("Redis connection refused")

        adapter = TokenBucketAdapter(config, logger, error_handler, cache=broken_cache)
        adapter.configure_bucket("fallback-test", capacity=10, refill_rate=1.0)

        # Should NOT raise — falls back to in-memory
        result = await adapter.is_allowed("fallback-test")
        assert result is True

        remaining = await adapter.get_remaining("fallback-test")
        assert remaining == 9

    @pytest.mark.asyncio
    async def test_fallback_preserves_state_in_memory(
        self,
        config: InMemoryConfigAdapter,
        logger: InMemoryLoggerAdapter,
        error_handler: CapturingErrorAdapter,
    ) -> None:
        """After cache fails, subsequent operations use in-memory state correctly."""
        broken_cache = MagicMock()
        broken_cache.get.side_effect = RuntimeError("Redis down")
        broken_cache.set.side_effect = RuntimeError("Redis down")

        adapter = TokenBucketAdapter(config, logger, error_handler, cache=broken_cache)
        adapter.configure_bucket("mem-fallback", capacity=5, refill_rate=0.1)

        # Consume all tokens
        for _ in range(5):
            result = await adapter.is_allowed("mem-fallback")
            assert result is True

        # 6th call should be denied
        result = await adapter.is_allowed("mem-fallback")
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_unavailable_does_not_block_no_cache(
        self,
        config: InMemoryConfigAdapter,
        logger: InMemoryLoggerAdapter,
        error_handler: CapturingErrorAdapter,
    ) -> None:
        """Adapter works normally when no cache manager is provided at all."""
        adapter = TokenBucketAdapter(config, logger, error_handler)
        adapter.configure_bucket("no-cache-bucket", capacity=10, refill_rate=1.0)

        result = await adapter.is_allowed("no-cache-bucket")
        assert result is True
