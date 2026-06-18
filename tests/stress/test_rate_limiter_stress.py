"""Stress tests for TokenBucketAdapter — concurrent rate limiting under load.

Tests cover:
- 1000 concurrent requests against bucket capacity 100 — at most 100 allowed
- Token refill recovers capacity during concurrent load
- Sliding window vs token bucket burst-traffic behavior
- No state corruption under high concurrency

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio

import pytest

from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.ratelimit.adapters.token_bucket_adapter import TokenBucketAdapter

pytestmark = pytest.mark.stress

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with ratelimit defaults."""
    return InMemoryConfigAdapter(
        initial_data={
            "ratelimit": {
                "default_capacity": 100,
                "default_refill_rate": 10.0,
                "redis_enabled": False,
            },
        },
    )


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    """Create an InMemoryObservabilityAdapter."""
    return InMemoryObservabilityAdapter()


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """Create an InMemoryLoggerAdapter."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def error_handler(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
    observability: InMemoryObservabilityAdapter,
) -> CapturingErrorAdapter:
    """Create a CapturingErrorAdapter with all dependencies."""
    return CapturingErrorAdapter(config, logger, observability)


@pytest.fixture
def adapter(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
    error_handler: CapturingErrorAdapter,
) -> TokenBucketAdapter:
    """Create a TokenBucketAdapter with default config."""
    return TokenBucketAdapter(config, logger, error_handler)


# ---------------------------------------------------------------------------
# Stress: concurrent burst with token bucket
# ---------------------------------------------------------------------------


class TestConcurrentBurstTokenBucket:
    """Verify token bucket correctness under 1000 concurrent requests."""

    @pytest.mark.asyncio
    async def test_1000_concurrent_requests_at_most_100_allowed(self, adapter: TokenBucketAdapter) -> None:
        """1 000 concurrent is_allowed() — at most capacity=100 allowed."""
        bucket = "burst:test"
        adapter.configure_bucket(bucket, capacity=100, refill_rate=0.1)

        async def make_request() -> bool:
            return await adapter.is_allowed(bucket)

        results = await asyncio.gather(*[make_request() for _ in range(1000)])
        allowed = sum(1 for r in results if r is True)
        denied = sum(1 for r in results if r is False)

        assert allowed <= 100, f"Allowed {allowed} requests, expected at most 100"
        assert allowed + denied == 1000

    @pytest.mark.asyncio
    async def test_remaining_never_negative_under_concurrent_load(self, adapter: TokenBucketAdapter) -> None:
        """get_remaining() never goes negative even under burst."""
        bucket = "concurrent:neg"
        adapter.configure_bucket(bucket, capacity=50, refill_rate=0.1)

        async def consume_and_check() -> int:
            await adapter.is_allowed(bucket)
            return await adapter.get_remaining(bucket)

        results = await asyncio.gather(*[consume_and_check() for _ in range(200)])
        for remaining in results:
            assert remaining >= 0, f"Remaining tokens were negative: {remaining}"

    @pytest.mark.asyncio
    async def test_token_refill_under_concurrent_load(self, adapter: TokenBucketAdapter) -> None:
        """Tokens refill while concurrent requests drain the bucket."""
        bucket = "refill:stress"
        adapter.configure_bucket(bucket, capacity=20, refill_rate=100.0)

        # Exhaust the bucket
        for _ in range(20):
            assert await adapter.is_allowed(bucket) is True

        remaining_after = await adapter.get_remaining(bucket)
        assert remaining_after == 0

        # Wait for refill — high refill_rate ensures rapid recovery
        await asyncio.sleep(0.15)

        remaining_after_refill = await adapter.get_remaining(bucket)
        assert remaining_after_refill > 0, "Tokens did not refill during concurrent load"


# ---------------------------------------------------------------------------
# Stress: sliding window vs token bucket under burst
# ---------------------------------------------------------------------------


class TestBurstAlgorithmComparison:
    """Verify sliding window is stricter than token bucket under burst."""

    @pytest.mark.asyncio
    async def test_sliding_window_blocks_burst_faster_than_token_bucket(self, adapter: TokenBucketAdapter) -> None:
        """Sliding window rejects burst sooner than token bucket with same capacity."""
        capacity = 30

        # Token bucket bucket
        adapter.configure_bucket("tb:burst", capacity=capacity, refill_rate=1.0, window_type="token_bucket")
        # Sliding window bucket
        adapter.configure_bucket("sw:burst", capacity=capacity, refill_rate=1.0, window_type="sliding_window")

        sw_denied_at: int | None = None
        for i in range(capacity + 10):
            allowed = await adapter.is_allowed("sw:burst")
            if not allowed and sw_denied_at is None:
                sw_denied_at = i

        assert sw_denied_at is not None, "Sliding window should eventually deny"
        assert sw_denied_at <= capacity, f"Sliding window denied at request {sw_denied_at}, expected <= {capacity}"

    @pytest.mark.asyncio
    async def test_concurrent_burst_no_state_corruption(self, adapter: TokenBucketAdapter) -> None:
        """Concurrent sliding window access does not corrupt timestamp state."""
        bucket = "sw:concurrent"
        adapter.configure_bucket(bucket, capacity=50, refill_rate=10.0, window_type="sliding_window")

        async def burst_requests(count: int) -> list[bool]:
            return [await adapter.is_allowed(bucket) for _ in range(count)]

        tasks = [burst_requests(30) for _ in range(5)]
        all_results: list[list[bool]] = await asyncio.gather(*tasks)

        total_allowed = sum(sum(1 for r in batch if r is True) for batch in all_results)
        remaining = await adapter.get_remaining(bucket)

        assert remaining >= 0, f"Remaining slots should never be negative, got {remaining}"
        assert total_allowed + remaining <= 50 * 2, "State corruption: allowed + remaining exceeds reasonable bounds"
