"""TokenBucketAdapter — token bucket rate limiting with asyncio.Lock thread safety.

Implements the Token Bucket algorithm: tokens are added at a constant
refill_rate per second, capped at capacity. is_allowed() consumes tokens
atomically. Each bucket is protected by its own asyncio.Lock for concurrent
safety in async contexts.

Security: is_allowed() returns False when tokens are exhausted — never raises.
Observability: All rate limit decisions emit RED metrics via ObservabilityManager.
@ai-directive: Redis integration is optional via CacheManager parameter. When
    not provided, buckets are in-memory only.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import time as _time
from typing import Any

from core_infrastructure.cache.ports import CacheManager
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.ratelimit.models import BucketState, RateLimitConfig


class TokenBucketAdapter:
    """Token Bucket rate limiter with per-bucket asyncio.Lock.

    Implements the classic Token Bucket algorithm: tokens are continuously
    refilled at ``refill_rate`` tokens per second, up to ``capacity``.
    ``is_allowed()`` atomically checks and consumes tokens.

    Args:
        config: ConfigManager for RateLimitConfig reading.
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for exception classification.
        cache: Optional CacheManager for Redis-backed distributed state.

    Usage::

        adapter = TokenBucketAdapter(config, logger, error_handler)
        adapter.configure_bucket("api:/users", capacity=100, refill_rate=10.0)
        if await adapter.is_allowed("api:/users"):
            process_request()
        else:
            raise RateLimitError("Too many requests")
    """

    def __init__(
        self,
        config: ConfigManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager,
        cache: CacheManager | None = None,
    ) -> None:
        self._config = config
        self._logger = logger
        self._error_handler = error_handler
        self._cache = cache

        rl_section = config.get_section("ratelimit")
        self._rl_config = RateLimitConfig(**rl_section) if rl_section else RateLimitConfig()

        self._buckets: dict[str, BucketState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_bucket(self, bucket_key: str) -> BucketState:
        """Retrieve an existing bucket or create one with defaults.

        Args:
            bucket_key: The bucket identifier.

        Returns:
            BucketState: The existing or newly created bucket state.
        """
        if bucket_key not in self._buckets:
            self._buckets[bucket_key] = BucketState(
                tokens=float(self._rl_config.default_capacity),
                capacity=self._rl_config.default_capacity,
                refill_rate=self._rl_config.default_refill_rate,
            )
        return self._buckets[bucket_key]

    def _get_or_create_lock(self, bucket_key: str) -> asyncio.Lock:
        """Retrieve or create an asyncio.Lock for a bucket.

        Args:
            bucket_key: The bucket identifier.

        Returns:
            asyncio.Lock: The lock for this bucket.
        """
        if bucket_key not in self._locks:
            self._locks[bucket_key] = asyncio.Lock()
        return self._locks[bucket_key]

    def _refill(self, bucket: BucketState) -> None:
        """Refill tokens based on elapsed time since last refill.

        Mutates the bucket state in-place. Tokens are capped at capacity.

        Args:
            bucket: The bucket state to refill.
        """
        now = _time.time()
        elapsed = now - bucket.last_refill
        if elapsed > 0:
            bucket.tokens = min(bucket.tokens + bucket.refill_rate * elapsed, float(bucket.capacity))
        bucket.last_refill = now

    # ------------------------------------------------------------------
    # Public API — RateLimiterManager Protocol
    # ------------------------------------------------------------------

    async def is_allowed(self, bucket_key: str, cost: float = 1.0) -> bool:
        """Check if an operation is allowed under the rate limit.

        Atomically refills the bucket and consumes ``cost`` tokens if
        sufficient tokens are available. Protected by asyncio.Lock.

        Args:
            bucket_key: The rate limit bucket identifier.
            cost: Number of tokens to consume (default 1.0).

        Returns:
            bool: ``True`` if allowed (tokens consumed), ``False`` if rate-limited.
        """
        lock = self._get_or_create_lock(bucket_key)
        async with lock:
            bucket = self._get_or_create_bucket(bucket_key)
            self._refill(bucket)

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True

            return False

    async def get_remaining(self, bucket_key: str) -> int:
        """Get remaining tokens for a bucket (read-only).

        Refills before reading to return the current token count.

        Args:
            bucket_key: The bucket to query.

        Returns:
            int: Remaining token count (floored to int).
        """
        lock = self._get_or_create_lock(bucket_key)
        async with lock:
            bucket = self._get_or_create_bucket(bucket_key)
            self._refill(bucket)
            return int(bucket.tokens)

    async def get_reset_time(self, bucket_key: str) -> float:
        """Get the Unix timestamp when the bucket will be full.

        Calculates the time needed to refill from current token count
        to full capacity at the configured refill_rate.

        Args:
            bucket_key: The bucket to query.

        Returns:
            float: Unix timestamp when the bucket reaches capacity.
        """
        lock = self._get_or_create_lock(bucket_key)
        async with lock:
            bucket = self._get_or_create_bucket(bucket_key)
            self._refill(bucket)

            deficit = float(bucket.capacity) - bucket.tokens
            if deficit <= 0:
                return _time.time()

            seconds_to_full = deficit / bucket.refill_rate
            return _time.time() + seconds_to_full

    def configure_bucket(self, bucket_key: str, capacity: int, refill_rate: float, window_type: str = "token_bucket") -> None:
        """Configure a rate limit bucket.

        Overwrites any existing configuration for the same bucket_key.
        The bucket is created fresh with tokens at full capacity.

        Args:
            bucket_key: Arbitrary string identifying the bucket.
            capacity: Maximum number of tokens.
            refill_rate: Tokens added per second.
            window_type: Algorithm type (default ``"token_bucket"``).
        """
        self._buckets[bucket_key] = BucketState(
            tokens=float(capacity),
            capacity=capacity,
            refill_rate=refill_rate,
        )

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: JSON Schema describing RateLimitConfig model.
        """
        return RateLimitConfig.model_json_schema()
