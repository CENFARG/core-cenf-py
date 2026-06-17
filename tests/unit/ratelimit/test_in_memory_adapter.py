"""Unit tests for InMemoryRateLimitAdapter — test double for rate limiting.

Tests cover:
- Protocol compliance (satisfies RateLimiterManager)
- always_allow mode: is_allowed() always returns True
- always_deny mode: is_allowed() always returns False
- configure_bucket and get_remaining work as expected
- get_reset_time() behavior
- get_json_schema() returns a dict

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import InMemoryRateLimitAdapter
from core_infrastructure.ratelimit.ports import RateLimiterManager


@pytest.fixture
def allow_adapter() -> InMemoryRateLimitAdapter:
    """Create an InMemoryRateLimitAdapter in always_allow mode."""
    return InMemoryRateLimitAdapter(mode="always_allow")


@pytest.fixture
def deny_adapter() -> InMemoryRateLimitAdapter:
    """Create an InMemoryRateLimitAdapter in always_deny mode."""
    return InMemoryRateLimitAdapter(mode="always_deny")


class TestInMemoryAdapterProtocol:
    """Verify InMemoryRateLimitAdapter satisfies RateLimiterManager Protocol."""

    def test_satisfies_ratelimit_manager_protocol(self, allow_adapter: InMemoryRateLimitAdapter) -> None:
        """InMemoryRateLimitAdapter passes isinstance check against RateLimiterManager."""
        assert isinstance(allow_adapter, RateLimiterManager)


class TestAlwaysAllowMode:
    """Verify always_allow mode behavior."""

    @pytest.mark.asyncio
    async def test_is_allowed_always_returns_true(self, allow_adapter: InMemoryRateLimitAdapter) -> None:
        """is_allowed() always returns True in always_allow mode."""
        for _ in range(100):
            assert await allow_adapter.is_allowed("any-bucket") is True

    @pytest.mark.asyncio
    async def test_get_remaining_returns_capacity(self, allow_adapter: InMemoryRateLimitAdapter) -> None:
        """get_remaining() returns the configured capacity."""
        allow_adapter.configure_bucket("test", capacity=50, refill_rate=5.0)
        remaining = await allow_adapter.get_remaining("test")
        assert remaining == 50

    @pytest.mark.asyncio
    async def test_get_reset_time(self, allow_adapter: InMemoryRateLimitAdapter) -> None:
        """get_reset_time() returns a float timestamp."""
        reset = await allow_adapter.get_reset_time("test")
        assert isinstance(reset, float)

    def test_configure_bucket_is_noop(self, allow_adapter: InMemoryRateLimitAdapter) -> None:
        """configure_bucket() is a noop in the test adapter."""
        allow_adapter.configure_bucket("any", capacity=10, refill_rate=1.0)
        # Should not raise


class TestAlwaysDenyMode:
    """Verify always_deny mode behavior."""

    @pytest.mark.asyncio
    async def test_is_allowed_always_returns_false(self, deny_adapter: InMemoryRateLimitAdapter) -> None:
        """is_allowed() always returns False in always_deny mode."""
        for _ in range(10):
            assert await deny_adapter.is_allowed("any-bucket") is False

    @pytest.mark.asyncio
    async def test_get_remaining_returns_zero(self, deny_adapter: InMemoryRateLimitAdapter) -> None:
        """get_remaining() returns 0 in always_deny mode."""
        remaining = await deny_adapter.get_remaining("test")
        assert remaining == 0


class TestJsonSchema:
    """Verify get_json_schema() for the test adapter."""

    def test_get_json_schema_returns_dict(self, allow_adapter: InMemoryRateLimitAdapter) -> None:
        """get_json_schema() returns a dict."""
        schema = allow_adapter.get_json_schema()
        assert isinstance(schema, dict)
