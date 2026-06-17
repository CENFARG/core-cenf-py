"""Unit tests for RateLimiterManager Protocol and models.

Tests cover:
- RateLimiterManager Protocol contract methods
- Protocol is runtime-checkable
- RateLimitConfig Pydantic model validation
- BucketState Pydantic model validation
- RateLimitHeaders Pydantic model validation

Author: CENF AI Team
Version: 0.1.0
"""

import time

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.ratelimit.models import BucketState, RateLimitConfig, RateLimitHeaders
from core_infrastructure.ratelimit.ports import RateLimiterManager


class TestRateLimiterManagerProtocol:
    """Verify RateLimiterManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """RateLimiterManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(RateLimiterManager, "_is_runtime_protocol")

    def test_has_is_allowed_method(self) -> None:
        """Protocol requires is_allowed(bucket_key, cost) -> bool."""
        assert hasattr(RateLimiterManager, "is_allowed")

    def test_has_get_remaining_method(self) -> None:
        """Protocol requires get_remaining(bucket_key) -> int."""
        assert hasattr(RateLimiterManager, "get_remaining")

    def test_has_get_reset_time_method(self) -> None:
        """Protocol requires get_reset_time(bucket_key) -> float."""
        assert hasattr(RateLimiterManager, "get_reset_time")

    def test_has_configure_bucket_method(self) -> None:
        """Protocol requires configure_bucket(bucket_key, capacity, refill_rate, window_type)."""
        assert hasattr(RateLimiterManager, "configure_bucket")

    def test_has_get_json_schema_static_method(self) -> None:
        """Protocol requires get_json_schema() static method."""
        assert hasattr(RateLimiterManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all RateLimiterManager methods satisfies the protocol."""

        class ValidRL:
            async def is_allowed(self, bucket_key: str, cost: float = 1.0) -> bool:
                ...

            async def get_remaining(self, bucket_key: str) -> int:
                ...

            async def get_reset_time(self, bucket_key: str) -> float:
                ...

            def configure_bucket(self, bucket_key: str, capacity: int, refill_rate: float, window_type: str = "token_bucket") -> None:
                ...

            @staticmethod
            def get_json_schema() -> dict[str, object]:
                ...

        assert isinstance(ValidRL(), RateLimiterManager)

    def test_class_missing_is_allowed_fails_protocol(self) -> None:
        """A class without is_allowed() does NOT satisfy RateLimiterManager."""

        class Incomplete:
            def configure_bucket(self, bucket_key: str, capacity: int, refill_rate: float) -> None:
                ...

        assert not isinstance(Incomplete(), RateLimiterManager)


class TestRateLimitConfigModel:
    """Verify RateLimitConfig Pydantic model validation."""

    def test_default_config(self) -> None:
        """RateLimitConfig creates with sensible defaults."""
        config = RateLimitConfig()
        assert config.default_capacity == 100
        assert config.default_refill_rate == 10.0
        assert config.redis_enabled is False

    def test_custom_config(self) -> None:
        """RateLimitConfig accepts custom values."""
        config = RateLimitConfig(default_capacity=50, default_refill_rate=5.0, redis_enabled=True)
        assert config.default_capacity == 50
        assert config.default_refill_rate == 5.0
        assert config.redis_enabled is True

    def test_capacity_below_one_fails(self) -> None:
        """default_capacity must be >= 1."""
        with pytest.raises(PydanticValidationError):
            RateLimitConfig(default_capacity=0)

    def test_capacity_above_max_fails(self) -> None:
        """default_capacity must be <= 10000."""
        with pytest.raises(PydanticValidationError):
            RateLimitConfig(default_capacity=10001)

    def test_refill_rate_below_min_fails(self) -> None:
        """default_refill_rate must be >= 0.1."""
        with pytest.raises(PydanticValidationError):
            RateLimitConfig(default_refill_rate=0.05)


class TestBucketStateModel:
    """Verify BucketState Pydantic model validation."""

    def test_bucket_state_creation(self) -> None:
        """BucketState stores tokens, timestamps, capacity, and refill_rate."""
        now = time.time()
        state = BucketState(
            tokens=50.0,
            last_refill=now,
            capacity=100,
            refill_rate=10.0,
        )
        assert state.tokens == 50.0
        assert state.capacity == 100
        assert state.refill_rate == 10.0

    def test_bucket_state_default_last_refill(self) -> None:
        """last_refill defaults to current time.time()."""
        state = BucketState(tokens=100.0, capacity=100, refill_rate=10.0)
        assert state.last_refill > 0

    def test_negative_tokens_fails(self) -> None:
        """tokens must be >= 0."""
        with pytest.raises(PydanticValidationError):
            BucketState(tokens=-1.0, capacity=100, refill_rate=10.0)

    def test_capacity_below_one_fails(self) -> None:
        """capacity must be >= 1."""
        with pytest.raises(PydanticValidationError):
            BucketState(tokens=50.0, capacity=0, refill_rate=10.0)


class TestRateLimitHeadersModel:
    """Verify RateLimitHeaders Pydantic model validation."""

    def test_rate_limit_headers_creation(self) -> None:
        """RateLimitHeaders stores standard rate limit response headers."""
        headers = RateLimitHeaders(
            limit=100,
            remaining=95,
            reset=time.time() + 60,
        )
        assert headers.limit == 100
        assert headers.remaining == 95
        assert headers.retry_after is None

    def test_rate_limit_headers_with_retry_after(self) -> None:
        """RateLimitHeaders supports optional retry_after."""
        headers = RateLimitHeaders(
            limit=10,
            remaining=0,
            reset=time.time() + 30,
            retry_after=30.0,
        )
        assert headers.retry_after == 30.0

    def test_negative_limit_fails(self) -> None:
        """limit must be >= 0."""
        with pytest.raises(PydanticValidationError):
            RateLimitHeaders(limit=-1, remaining=0, reset=time.time())

    def test_negative_remaining_fails(self) -> None:
        """remaining must be >= 0."""
        with pytest.raises(PydanticValidationError):
            RateLimitHeaders(limit=10, remaining=-1, reset=time.time())
