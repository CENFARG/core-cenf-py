"""RateLimiterManager Protocol — unified rate limiting contract.

Defines the contract for rate limiting operations using Token Bucket and
Sliding Window algorithms. Protects endpoints, operations, and alert channels
from DoS and overload. Returns standard rate limit headers.

Security: is_allowed() MUST be called BEFORE any rate-limited operation.
Observability: All check events emit RED metrics via ObservabilityManager.
@ai-directive: Use is_allowed before any rate-limited operation. Bucket keys
    are arbitrary strings.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RateLimiterManager(Protocol):
    """Rate limiting contract for operations, endpoints, and alert channels.

    Provides Token Bucket and Sliding Window rate limiting algorithms.
    Bucket keys are arbitrary strings chosen by the consumer. The manager
    is framework-agnostic — does not couple to HTTP frameworks.

    Rules:
        - is_allowed() consumes tokens if the bucket has sufficient capacity.
        - get_remaining() is a read-only operation that does not consume tokens.
        - configure_bucket() sets up a bucket before first use.
        - get_reset_time() returns the Unix timestamp when the bucket refills.
    """

    async def is_allowed(self, bucket_key: str, cost: float = 1.0) -> bool:
        """Check if an operation is allowed under the rate limit.

        Consumes ``cost`` tokens from the bucket if sufficient tokens are
        available. Returns ``True`` if allowed, ``False`` if rate-limited.

        Args:
            bucket_key: Arbitrary string identifying the rate limit bucket.
            cost: Number of tokens to consume (default 1.0).

        Returns:
            bool: ``True`` if the operation is allowed (tokens were consumed),
                ``False`` if rate-limited (no tokens consumed).
        """
        ...

    async def get_remaining(self, bucket_key: str) -> int:
        """Get remaining tokens for a bucket.

        Read-only operation — does NOT consume tokens.

        Args:
            bucket_key: The bucket to query.

        Returns:
            int: Remaining token count (floored to int).
        """
        ...

    async def get_reset_time(self, bucket_key: str) -> float:
        """Get the Unix timestamp when the bucket will be full again.

        Args:
            bucket_key: The bucket to query.

        Returns:
            float: Unix timestamp when the bucket reaches full capacity.
        """
        ...

    def configure_bucket(self, bucket_key: str, capacity: int, refill_rate: float, window_type: str = "token_bucket") -> None:
        """Configure a rate limit bucket with capacity and refill rate.

        Must be called before ``is_allowed()`` for the given bucket_key.
        Overwrites existing configuration for the same key.

        Args:
            bucket_key: Arbitrary string identifying the bucket.
            capacity: Maximum number of tokens the bucket can hold.
            refill_rate: Tokens added per second.
            window_type: Algorithm — ``"token_bucket"`` or ``"sliding_window"``.
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: A valid JSON Schema object describing the
                RateLimitConfig model.
        """
        ...
