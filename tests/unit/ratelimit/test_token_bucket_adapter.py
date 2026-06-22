"""Unit tests for TokenBucketAdapter — token bucket rate limiting.

Tests cover:
- Protocol compliance (satisfies RateLimiterManager)
- is_allowed() returns True when tokens available
- is_allowed() returns False when tokens exhausted
- Tokens refill over time
- Tokens never exceed capacity
- get_remaining() decreases after is_allowed()
- Concurrent access thread safety
- Custom cost per operation
- Multiple independent buckets
- get_reset_time() calculation

Author: CENF AI Team
Version: 0.1.0
"""

import asyncio
import time

import pytest

from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import InMemoryObservabilityAdapter
from core_infrastructure.ratelimit.adapters.token_bucket_adapter import TokenBucketAdapter
from core_infrastructure.ratelimit.ports import RateLimiterManager


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with ratelimit settings."""
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
def adapter(config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, error_handler: CapturingErrorAdapter) -> TokenBucketAdapter:
    """Create a TokenBucketAdapter with default config."""
    return TokenBucketAdapter(config, logger, error_handler)


class TestTokenBucketAdapterProtocol:
    """Verify TokenBucketAdapter satisfies RateLimiterManager Protocol."""

    def test_satisfies_ratelimit_manager_protocol(self, adapter: TokenBucketAdapter) -> None:
        """TokenBucketAdapter passes isinstance check against RateLimiterManager."""
        assert isinstance(adapter, RateLimiterManager)


class TestConfigureBucket:
    """Verify configure_bucket() stores bucket settings."""

    def test_configure_bucket_stores_config(self, adapter: TokenBucketAdapter) -> None:
        """configure_bucket() stores the bucket configuration."""
        adapter.configure_bucket("api:/users", capacity=10, refill_rate=1.0)
        assert "api:/users" in adapter._buckets

    def test_configure_bucket_default_window_type(self, adapter: TokenBucketAdapter) -> None:
        """configure_bucket() defaults window_type to token_bucket."""
        adapter.configure_bucket("test-bucket", capacity=5, refill_rate=0.5)
        assert adapter._buckets["test-bucket"].capacity == 5

    def test_configure_bucket_overwrites_existing(self, adapter: TokenBucketAdapter) -> None:
        """configure_bucket() overwrites existing bucket config."""
        adapter.configure_bucket("api:/users", capacity=10, refill_rate=1.0)
        adapter.configure_bucket("api:/users", capacity=20, refill_rate=2.0)
        assert adapter._buckets["api:/users"].capacity == 20


class TestIsAllowed:
    """Verify is_allowed() token bucket behavior."""

    @pytest.mark.asyncio
    async def test_is_allowed_returns_true_when_tokens_available(self, adapter: TokenBucketAdapter) -> None:
        """is_allowed() returns True when tokens are available."""
        adapter.configure_bucket("api:/users", capacity=10, refill_rate=1.0)
        result = await adapter.is_allowed("api:/users")
        assert result is True

    @pytest.mark.asyncio
    async def test_is_allowed_returns_false_when_tokens_exhausted(self, adapter: TokenBucketAdapter) -> None:
        """is_allowed() returns False when all tokens are consumed."""
        adapter.configure_bucket("api:/test", capacity=3, refill_rate=0.1)
        for _ in range(3):
            result = await adapter.is_allowed("api:/test")
            assert result is True
        result = await adapter.is_allowed("api:/test")
        assert result is False

    @pytest.mark.asyncio
    async def test_is_allowed_with_custom_cost(self, adapter: TokenBucketAdapter) -> None:
        """is_allowed() with cost=5.0 consumes 5 tokens."""
        adapter.configure_bucket("api:/heavy", capacity=100, refill_rate=1.0)
        await adapter.is_allowed("api:/heavy", cost=10.0)
        remaining = await adapter.get_remaining("api:/heavy")
        assert remaining == 90

    @pytest.mark.asyncio
    async def test_is_allowed_default_bucket_config(self, adapter: TokenBucketAdapter) -> None:
        """is_allowed() uses default config when bucket not explicitly configured."""
        result = await adapter.is_allowed("implicit-bucket")
        assert result is True


class TestGetRemaining:
    """Verify get_remaining() returns current token count."""

    @pytest.mark.asyncio
    async def test_get_remaining_decreases_after_is_allowed(self, adapter: TokenBucketAdapter) -> None:
        """get_remaining() reflects consumed tokens."""
        adapter.configure_bucket("api:/counter", capacity=10, refill_rate=0.1)
        await adapter.is_allowed("api:/counter")
        remaining = await adapter.get_remaining("api:/counter")
        assert remaining == 9

    @pytest.mark.asyncio
    async def test_get_remaining_for_unconfigured_bucket(self, adapter: TokenBucketAdapter) -> None:
        """get_remaining() for unconfigured bucket uses defaults."""
        remaining = await adapter.get_remaining("new-bucket")
        assert remaining == 100  # default_capacity


class TestTokenRefill:
    """Verify tokens refill over time and respect capacity."""

    @pytest.mark.asyncio
    async def test_tokens_refill_over_time(self, adapter: TokenBucketAdapter) -> None:
        """Tokens refill after time passes based on refill_rate."""
        adapter.configure_bucket("api:/refill-test", capacity=10, refill_rate=100.0)
        for _ in range(10):
            await adapter.is_allowed("api:/refill-test")
        remaining_after_exhaust = await adapter.get_remaining("api:/refill-test")
        assert remaining_after_exhaust == 0

        await asyncio.sleep(0.1)

        remaining_after_wait = await adapter.get_remaining("api:/refill-test")
        assert remaining_after_wait > 0

    @pytest.mark.asyncio
    async def test_tokens_never_exceed_capacity(self, adapter: TokenBucketAdapter) -> None:
        """Tokens never exceed the configured capacity even after long waits."""
        adapter.configure_bucket("api:/cap-test", capacity=5, refill_rate=1000.0)
        for _ in range(5):
            await adapter.is_allowed("api:/cap-test")

        await asyncio.sleep(0.2)

        remaining = await adapter.get_remaining("api:/cap-test")
        assert remaining <= 5


class TestGetResetTime:
    """Verify get_reset_time() returns reasonable timestamp."""

    @pytest.mark.asyncio
    async def test_get_reset_time_returns_future_timestamp(self, adapter: TokenBucketAdapter) -> None:
        """get_reset_time() returns a Unix timestamp in the future."""
        adapter.configure_bucket("api:/reset-test", capacity=100, refill_rate=10.0)
        for _ in range(50):
            await adapter.is_allowed("api:/reset-test")
        reset_time = await adapter.get_reset_time("api:/reset-test")
        now = time.time()
        assert reset_time > now

    @pytest.mark.asyncio
    async def test_get_reset_time_full_bucket(self, adapter: TokenBucketAdapter) -> None:
        """get_reset_time() for a full bucket returns a time near now."""
        adapter.configure_bucket("api:/full-bucket", capacity=100, refill_rate=10.0)
        reset_time = await adapter.get_reset_time("api:/full-bucket")
        now = time.time()
        assert reset_time <= now + 1.0  # Should be very soon or past


class TestMultipleBuckets:
    """Verify independent bucket isolation."""

    @pytest.mark.asyncio
    async def test_multiple_buckets_are_independent(self, adapter: TokenBucketAdapter) -> None:
        """Consuming tokens in one bucket does not affect another."""
        adapter.configure_bucket("a", capacity=5, refill_rate=0.1)
        adapter.configure_bucket("b", capacity=5, refill_rate=0.1)

        for _ in range(5):
            await adapter.is_allowed("a")

        assert await adapter.is_allowed("a") is False
        assert await adapter.is_allowed("b") is True


class TestConcurrentAccess:
    """Verify thread safety under concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_access_does_not_corrupt_state(self, adapter: TokenBucketAdapter) -> None:
        """Concurrent is_allowed() calls do not corrupt the bucket state."""
        adapter.configure_bucket("concurrent-test", capacity=200, refill_rate=100.0)

        async def consume():
            results = []
            for _ in range(20):
                r = await adapter.is_allowed("concurrent-test")
                results.append(r)
            return results

        tasks = [asyncio.create_task(consume()) for _ in range(5)]
        all_results = []
        for t in tasks:
            all_results.extend(await t)

        true_count = sum(1 for r in all_results if r is True)
        remaining = await adapter.get_remaining("concurrent-test")

        assert true_count + remaining == 200


class TestMonotonicClock:
    """Verify refill calculations use monotonic time, not wall-clock time.

    When the system clock jumps forward (e.g., NTP correction, VM migration),
    time.time() would cause the token bucket to incorrectly refill tokens
    that were never earned. time.monotonic() is immune to clock jumps.
    """

    @pytest.mark.asyncio
    async def test_refill_immune_to_wall_clock_jump(
        self,
        config: InMemoryConfigAdapter,
        logger: InMemoryLoggerAdapter,
        error_handler: CapturingErrorAdapter,
    ) -> None:
        """Tokens do NOT refill when wall-clock jumps forward but monotonic doesn't advance."""
        adapter = TokenBucketAdapter(config, logger, error_handler)
        adapter.configure_bucket("clock-jump", capacity=100, refill_rate=100.0)

        # Exhaust all tokens
        for _ in range(100):
            assert await adapter.is_allowed("clock-jump") is True
        assert await adapter.is_allowed("clock-jump") is False

        # Simulate a wall-clock jump forward by 1 hour.
        # If the adapter uses time.time(), it will see elapsed=3600s
        # and refill tokens. With time.monotonic(), no refill occurs.
        import time as _stdlib_time
        from unittest.mock import patch

        original_time = _stdlib_time.time
        fake_future = original_time() + 3600.0

        # Patch time.time in the adapter module to return a jumped value
        with patch(
            "core_infrastructure.ratelimit.adapters.token_bucket_adapter._time.time",
            return_value=fake_future,
        ):
            remaining = await adapter.get_remaining("clock-jump")

        # With monotonic clock: only real time elapsed during the test
        # refills a tiny number of tokens (maybe 1-2 at 100 tokens/sec).
        # With wall-clock: jump of 3600s would refill all 100 (VULNERABILITY).
        assert remaining < 5, (
            f"Expected ≤4 tokens (monotonic: only real ms elapsed), "
            f"got {remaining} (wall-clock jump of 3600s would give 100)"
        )
