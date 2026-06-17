"""InMemoryRateLimitAdapter — RateLimiterManager test double.

Provides a zero-dependency RateLimiterManager implementation for unit tests.
Two modes: ``always_allow`` (is_allowed() always returns True) and
``always_deny`` (is_allowed() always returns False). Useful for testing
consumers that depend on RateLimiterManager.

Security: No real rate limiting occurs — safe for CI without Redis.
Observability: Fully deterministic — no side effects, no logging.
@ai-directive: This adapter exists solely for testing. NEVER use it in
    production code paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time as _time
from typing import Any, Literal

Mode = Literal["always_allow", "always_deny"]


class InMemoryRateLimitAdapter:
    """RateLimiterManager test double with configurable behavior.

    Two modes of operation:
    - ``always_allow``: ``is_allowed()`` returns ``True`` for every call.
    - ``always_deny``: ``is_allowed()`` returns ``False`` for every call.

    Args:
        mode: ``"always_allow"`` or ``"always_deny"`` (default ``"always_allow"``).
    """

    def __init__(self, mode: Mode = "always_allow") -> None:
        self._mode: Mode = mode
        self._buckets: dict[str, dict[str, Any]] = {}

    async def is_allowed(self, bucket_key: str, cost: float = 1.0) -> bool:
        """Check if an operation is allowed.

        Args:
            bucket_key: The bucket key (ignored in test mode).
            cost: Cost of the operation (ignored in test mode).

        Returns:
            bool: ``True`` in always_allow mode, ``False`` in always_deny.
        """
        return self._mode == "always_allow"

    async def get_remaining(self, bucket_key: str) -> int:
        """Get remaining tokens for a bucket.

        Args:
            bucket_key: The bucket to query.

        Returns:
            int: The configured capacity in allow mode, 0 in deny mode.
        """
        if bucket_key in self._buckets:
            cap = self._buckets[bucket_key].get("capacity", 100)
            return cap if self._mode == "always_allow" else 0
        return 100 if self._mode == "always_allow" else 0

    async def get_reset_time(self, bucket_key: str) -> float:
        """Get the Unix timestamp when the bucket resets.

        Returns:
            float: Current time + 60s (arbitrary future timestamp).
        """
        return _time.time() + 60.0

    def configure_bucket(self, bucket_key: str, capacity: int, refill_rate: float, window_type: str = "token_bucket") -> None:
        """Configure a rate limit bucket (noop in test mode).

        Args:
            bucket_key: The bucket identifier.
            capacity: Maximum tokens.
            refill_rate: Refill rate.
            window_type: Algorithm type.
        """
        self._buckets[bucket_key] = {"capacity": capacity, "refill_rate": refill_rate}

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return a minimal JSON Schema stub.

        Returns:
            dict[str, Any]: Schema stub for agent discovery.
        """
        return {"type": "object", "description": "InMemoryRateLimitAdapter schema stub."}
