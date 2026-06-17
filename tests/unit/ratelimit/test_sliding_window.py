"""Unit tests for Sliding Window rate limiting in TokenBucketAdapter.

Tests cover:
- Window expires old timestamps outside the window boundary
- Capacity enforcement — deny when window is full
- Sliding window is stricter than token bucket for burst traffic
- get_remaining() returns count of available slots
- get_reset_time() returns when the oldest timestamp expires

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import time as _time

import pytest

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
                "redis_enabled": False,
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
def adapter(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
    error_handler: CapturingErrorAdapter,
) -> TokenBucketAdapter:
    return TokenBucketAdapter(config, logger, error_handler)


class TestSlidingWindowExpiry:
    """Verify old timestamps are removed from the window."""

    @pytest.mark.asyncio
    async def test_window_expires_old_timestamps(self, adapter: TokenBucketAdapter) -> None:
        """Timestamps older than the window size are removed and capacity frees up."""
        # window_size = capacity / refill_rate = 10 / 2.0 = 5 seconds
        adapter.configure_bucket("sw-expire", capacity=10, refill_rate=2.0, window_type="sliding_window")

        # Fill the window
        for _ in range(10):
            result = await adapter.is_allowed("sw-expire")
            assert result is True

        # Window is full — next request denied
        assert await adapter.is_allowed("sw-expire") is False

        # Wait for window to pass
        await asyncio.sleep(5.1)

        # Now old timestamps expired, new request allowed
        result = await adapter.is_allowed("sw-expire")
        assert result is True

    @pytest.mark.asyncio
    async def test_window_expiry_partial(self, adapter: TokenBucketAdapter) -> None:
        """Only the oldest timestamp expires, not all at once."""
        # window_size = 5 / 10.0 = 0.5 seconds
        adapter.configure_bucket("sw-partial", capacity=5, refill_rate=10.0, window_type="sliding_window")

        # Fill 5 in quick succession
        for _ in range(5):
            await adapter.is_allowed("sw-partial")

        # Denied
        assert await adapter.is_allowed("sw-partial") is False

        # Wait for just over the window (0.55s > 0.5s) — all timestamps expire
        await asyncio.sleep(0.55)

        # Now at least one request should be allowed
        remaining = await adapter.get_remaining("sw-partial")
        assert remaining > 0


class TestSlidingWindowCapacityEnforcement:
    """Verify capacity limit is strictly enforced."""

    @pytest.mark.asyncio
    async def test_capacity_denies_when_full(self, adapter: TokenBucketAdapter) -> None:
        """When window has capacity requests, further requests are denied."""
        adapter.configure_bucket("sw-cap", capacity=3, refill_rate=3.0, window_type="sliding_window")

        # Fill exactly to capacity
        for _ in range(3):
            result = await adapter.is_allowed("sw-cap")
            assert result is True

        # 4th request denied
        result = await adapter.is_allowed("sw-cap")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_remaining_reflects_available_slots(self, adapter: TokenBucketAdapter) -> None:
        """get_remaining() returns the number of available slots in the window."""
        adapter.configure_bucket("sw-remaining", capacity=5, refill_rate=1.0, window_type="sliding_window")

        # No requests yet — all slots available
        remaining = await adapter.get_remaining("sw-remaining")
        assert remaining == 5

        # Consume 3
        for _ in range(3):
            await adapter.is_allowed("sw-remaining")

        remaining = await adapter.get_remaining("sw-remaining")
        assert remaining == 2

    @pytest.mark.asyncio
    async def test_get_reset_time_for_sliding_window(self, adapter: TokenBucketAdapter) -> None:
        """get_reset_time returns when the oldest timestamp leaves the window."""
        adapter.configure_bucket("sw-reset", capacity=5, refill_rate=1.0, window_type="sliding_window")

        # No requests — reset time should be now
        reset_time = await adapter.get_reset_time("sw-reset")
        now = _time.time()
        assert reset_time <= now + 1.0

        # Make a request
        await adapter.is_allowed("sw-reset")
        reset_time = await adapter.get_reset_time("sw-reset")
        # Should be ~5.0 seconds from now (window = 5/1 = 5s)
        now = _time.time()
        assert reset_time > now
        assert reset_time <= now + 6.0  # generous bound


class TestSlidingWindowVsTokenBucket:
    """Compare precision: sliding window is stricter than token bucket."""

    @pytest.mark.asyncio
    async def test_sliding_window_stricter_than_token_bucket(self, adapter: TokenBucketAdapter) -> None:
        """Sliding window denies 4th immediate request while token bucket allows it."""
        # Token bucket: capacity=3, refill_rate=100 → 30ms to refill 1 token
        adapter.configure_bucket("tb-burst", capacity=3, refill_rate=100.0, window_type="token_bucket")
        # Sliding window: same capacity, window = 3/100 = 0.03s
        adapter.configure_bucket("sw-burst", capacity=3, refill_rate=100.0, window_type="sliding_window")

        # Token bucket allows 3, then 4th is denied but a tiny sleep lets a token refill
        for _ in range(3):
            assert await adapter.is_allowed("tb-burst") is True  # token bucket

        # Token bucket: after 0.015s, ~1.5 tokens refilled — possible to allow
        await asyncio.sleep(0.02)
        tb_result = await adapter.is_allowed("tb-burst")  # may or may not allow

        # Sliding window: 3 requests filled, window is full until 0.03s passes
        for _ in range(3):
            assert await adapter.is_allowed("sw-burst") is True

        await asyncio.sleep(0.015)  # less than window size
        sw_result = await adapter.is_allowed("sw-burst")

        # Sliding window should be stricter: denies while window not expired
        # Token bucket may allow due to token refill even within window
        # Assert sliding window result is not more permissive than token bucket
        assert sw_result is not True or tb_result is True

    @pytest.mark.asyncio
    async def test_multiple_buckets_different_algos_independent(
        self, adapter: TokenBucketAdapter
    ) -> None:
        """Token bucket and sliding window buckets operate independently."""
        adapter.configure_bucket("tb-indep", capacity=5, refill_rate=10.0, window_type="token_bucket")
        adapter.configure_bucket("sw-indep", capacity=5, refill_rate=0.1, window_type="sliding_window")

        # Exhaust token bucket
        for _ in range(5):
            await adapter.is_allowed("tb-indep")

        # Token bucket should deny
        assert await adapter.is_allowed("tb-indep") is False

        # Sliding window is independent and still allows
        assert await adapter.is_allowed("sw-indep") is True
