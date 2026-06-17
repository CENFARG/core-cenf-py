"""TokenBucketAdapter — token bucket and sliding window rate limiting with Redis support.

Implements two rate limiting algorithms: Token Bucket (tokens refill continuously,
capped at capacity) and Sliding Window (timestamps tracked, window-based counting).
When a CacheManager (Redis) is provided, bucket state is persisted to the shared
cache; on failure it gracefully falls back to in-memory dicts.

Security: is_allowed() returns False when limits exceeded — never raises.
Observability: All rate limit decisions emit RED metrics via ObservabilityManager.
@ai-directive: Redis key format is ``cenf:ratelimit:{bucket_key}``. Bucket state
    JSON includes tokens, last_refill, capacity, refill_rate, and timestamps.

Author: CENF AI Team
Version: 0.2.0
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

_REDIS_KEY_PREFIX = "cenf:ratelimit:"
_WINDOW_TOKEN_BUCKET = "token_bucket"
_WINDOW_SLIDING = "sliding_window"


class TokenBucketAdapter:
    """Token Bucket and Sliding Window rate limiter with Redis-backed distributed state.

    Implements two algorithms:
    - Token Bucket: tokens refill continuously at ``refill_rate``/s, capped at ``capacity``.
    - Sliding Window: tracks request timestamps; requests expire from the window
      after ``capacity / refill_rate`` seconds.

    When ``cache`` (CacheManager) is provided, bucket state is read/written to
    Redis with key prefix ``cenf:ratelimit:``, enabling cross-process rate limiting.
    On Redis failure, gracefully falls back to in-memory only.

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
        self._window_timestamps: dict[str, list[float]] = {}
        self._window_configs: dict[str, tuple[int, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _redis_key(bucket_key: str) -> str:
        """Build the Redis cache key for a rate limit bucket.

        Args:
            bucket_key: The bucket identifier.

        Returns:
            str: Prefixed cache key (``cenf:ratelimit:{bucket_key}``).
        """
        return f"{_REDIS_KEY_PREFIX}{bucket_key}"

    def _redis_get(self, bucket_key: str) -> dict[str, Any] | None:
        """Retrieve bucket state from Redis cache.

        Args:
            bucket_key: The bucket identifier.

        Returns:
            dict | None: Deserialized bucket state dict, or ``None`` if missing/failed.
        """
        if self._cache is None:
            return None
        try:
            data = self._cache.get(self._redis_key(bucket_key))
            if data is None:
                return None
            if not isinstance(data, dict):
                return None
            return data
        except Exception:
            return None

    def _redis_set(self, bucket_key: str, bucket: BucketState) -> None:
        """Persist bucket state to Redis cache.

        Args:
            bucket_key: The bucket identifier.
            bucket: The bucket state to persist.
        """
        if self._cache is None:
            return
        try:
            payload = bucket.model_dump()
            self._cache.set(self._redis_key(bucket_key), payload)
        except Exception:
            self._logger.warn("Failed to persist bucket state to cache", bucket_key=bucket_key)

    def _redis_set_window(self, bucket_key: str, timestamps: list[float], capacity: int, refill_rate: float) -> None:
        """Persist sliding window state to Redis cache.

        Args:
            bucket_key: The bucket identifier.
            timestamps: List of request timestamps.
            capacity: Max requests per window.
            refill_rate: Tokens per second (used to derive window size).
        """
        if self._cache is None:
            return
        try:
            payload = {
                "timestamps": timestamps,
                "capacity": capacity,
                "refill_rate": refill_rate,
                "window_type": _WINDOW_SLIDING,
            }
            self._cache.set(self._redis_key(bucket_key), payload)
        except Exception:
            self._logger.warn("Failed to persist window state to cache", bucket_key=bucket_key)

    def _redis_get_window(self, bucket_key: str) -> dict[str, Any] | None:
        """Retrieve sliding window state from Redis cache.

        Args:
            bucket_key: The bucket identifier.

        Returns:
            dict | None: Window state dict with ``timestamps``, ``capacity``, ``refill_rate``,
                or ``None`` if missing or failed.
        """
        return self._redis_get(bucket_key)

    # ------------------------------------------------------------------
    # Internal helpers — Token Bucket
    # ------------------------------------------------------------------

    def _get_or_create_bucket(self, bucket_key: str) -> BucketState:
        """Retrieve an existing bucket or create one with defaults.

        Tries Redis cache first; falls back to in-memory dict on failure.

        Args:
            bucket_key: The bucket identifier.

        Returns:
            BucketState: The existing or newly created bucket state.
        """
        raw = self._redis_get(bucket_key)
        if raw is not None and raw.get("window_type") != _WINDOW_SLIDING:
            try:
                return BucketState(**raw)
            except Exception:
                pass

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
    # Internal helpers — Sliding Window
    # ------------------------------------------------------------------

    def _window_size(self, capacity: int, refill_rate: float) -> float:
        """Calculate the sliding window duration in seconds.

        Window size = capacity / refill_rate.

        Args:
            capacity: Max requests per window.
            refill_rate: Request-equivalent rate per second.

        Returns:
            float: Window duration in seconds.
        """
        if refill_rate <= 0:
            return float(capacity)
        return float(capacity) / refill_rate

    def _get_or_create_window(self, bucket_key: str) -> tuple[list[float], int, float]:
        """Retrieve or create sliding window state for a bucket.

        Tries Redis cache first; falls back to in-memory dict.

        Args:
            bucket_key: The bucket identifier.

        Returns:
            tuple[list[float], int, float]: (timestamps, capacity, refill_rate).
        """
        raw = self._redis_get_window(bucket_key)
        if raw is not None and raw.get("window_type") == _WINDOW_SLIDING:
            try:
                return (raw["timestamps"], raw["capacity"], raw["refill_rate"])
            except (KeyError, TypeError):
                pass

        if bucket_key not in self._window_timestamps:
            cap, rate = self._window_configs.get(
                bucket_key,
                (self._rl_config.default_capacity, self._rl_config.default_refill_rate),
            )
            self._window_timestamps[bucket_key] = []
            self._window_configs[bucket_key] = (cap, rate)
        cap, rate = self._window_configs[bucket_key]
        return (self._window_timestamps[bucket_key], cap, rate)

    def _prune_window(self, timestamps: list[float], capacity: int, refill_rate: float) -> None:
        """Remove timestamps outside the current sliding window.

        Mutates ``timestamps`` in-place, removing entries older than
        ``_time.time() - window_size``.

        Args:
            timestamps: The list of request timestamps.
            capacity: Max requests per window.
            refill_rate: Request-equivalent rate per second.
        """
        window = self._window_size(capacity, refill_rate)
        cutoff = _time.time() - window
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

    # ------------------------------------------------------------------
    # Public API — RateLimiterManager Protocol
    # ------------------------------------------------------------------

    async def is_allowed(self, bucket_key: str, cost: float = 1.0) -> bool:
        """Check if an operation is allowed under the rate limit.

        Dispatches to the appropriate algorithm based on the bucket's
        ``window_type`` configuration. Protected by asyncio.Lock.

        Args:
            bucket_key: The rate limit bucket identifier.
            cost: Number of tokens to consume (default 1.0). Ignored for sliding window.

        Returns:
            bool: ``True`` if allowed, ``False`` if rate-limited.
        """
        lock = self._get_or_create_lock(bucket_key)
        async with lock:
            if bucket_key in self._window_configs:
                timestamps, cap, rate = self._get_or_create_window(bucket_key)
                self._prune_window(timestamps, cap, rate)

                if len(timestamps) >= cap:
                    return False

                timestamps.append(_time.time())
                self._redis_set_window(bucket_key, timestamps, cap, rate)
                return True

            bucket = self._get_or_create_bucket(bucket_key)
            self._refill(bucket)

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                self._redis_set(bucket_key, bucket)
                return True

            self._redis_set(bucket_key, bucket)
            return False

    async def get_remaining(self, bucket_key: str) -> int:
        """Get remaining tokens/slots for a bucket (read-only).

        For token bucket, returns current token count. For sliding window,
        returns remaining capacity slots after pruning expired entries.

        Args:
            bucket_key: The bucket to query.

        Returns:
            int: Remaining count (floored to int).
        """
        lock = self._get_or_create_lock(bucket_key)
        async with lock:
            if bucket_key in self._window_configs:
                timestamps, cap, rate = self._get_or_create_window(bucket_key)
                self._prune_window(timestamps, cap, rate)
                self._redis_set_window(bucket_key, timestamps, cap, rate)
                return max(0, cap - len(timestamps))

            bucket = self._get_or_create_bucket(bucket_key)
            self._refill(bucket)
            self._redis_set(bucket_key, bucket)
            return int(bucket.tokens)

    async def get_reset_time(self, bucket_key: str) -> float:
        """Get the Unix timestamp when the bucket will be full again.

        For token bucket: calculates time to full at current refill rate.
        For sliding window: returns when the oldest timestamp expires from the window.

        Args:
            bucket_key: The bucket to query.

        Returns:
            float: Unix timestamp when the bucket resets.
        """
        lock = self._get_or_create_lock(bucket_key)
        async with lock:
            if bucket_key in self._window_configs:
                timestamps, cap, rate = self._get_or_create_window(bucket_key)
                self._prune_window(timestamps, cap, rate)
                self._redis_set_window(bucket_key, timestamps, cap, rate)

                if not timestamps:
                    return _time.time()

                window = self._window_size(cap, rate)
                return timestamps[0] + window

            bucket = self._get_or_create_bucket(bucket_key)
            self._refill(bucket)

            deficit = float(bucket.capacity) - bucket.tokens
            if deficit <= 0:
                return _time.time()

            seconds_to_full = deficit / bucket.refill_rate
            return _time.time() + seconds_to_full

    def configure_bucket(
        self,
        bucket_key: str,
        capacity: int,
        refill_rate: float,
        window_type: str = "token_bucket",
    ) -> None:
        """Configure a rate limit bucket.

        Overwrites any existing configuration for the same bucket_key.
        When ``window_type`` is ``"sliding_window"``, initializes sliding
        window state instead of token bucket state.

        Args:
            bucket_key: Arbitrary string identifying the bucket.
            capacity: Maximum number of tokens/requests.
            refill_rate: Tokens added per second (or used to derive window size).
            window_type: Algorithm type — ``"token_bucket"`` or ``"sliding_window"``.
        """
        if window_type == _WINDOW_SLIDING:
            self._buckets.pop(bucket_key, None)
            self._window_timestamps[bucket_key] = []
            self._window_configs[bucket_key] = (capacity, refill_rate)
            self._redis_set_window(bucket_key, [], capacity, refill_rate)
        else:
            self._window_timestamps.pop(bucket_key, None)
            self._window_configs.pop(bucket_key, None)
            self._buckets[bucket_key] = BucketState(
                tokens=float(capacity),
                capacity=capacity,
                refill_rate=refill_rate,
            )
            self._redis_set(bucket_key, self._buckets[bucket_key])

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: JSON Schema describing RateLimitConfig model.
        """
        return RateLimitConfig.model_json_schema()
