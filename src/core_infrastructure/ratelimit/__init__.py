"""CENF RateLimiterManager — token bucket rate limiting abstraction.

Provides a Protocol-based interface for rate limiting operations using Token
Bucket and Sliding Window algorithms. TokenBucketAdapter implements the full
contract with asyncio.Lock thread safety; InMemoryRateLimitAdapter is a
dict-based test double that always allows or always denies.

Security: is_allowed() MUST be called BEFORE any rate-limited operation.
Observability: All check events emit RED metrics via ObservabilityManager.
@ai-directive: Bucket keys are arbitrary strings chosen by the consumer.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import InMemoryRateLimitAdapter
from core_infrastructure.ratelimit.adapters.token_bucket_adapter import TokenBucketAdapter
from core_infrastructure.ratelimit.models import BucketState, RateLimitConfig, RateLimitHeaders
from core_infrastructure.ratelimit.ports import RateLimiterManager

__all__ = [
    "BucketState",
    "InMemoryRateLimitAdapter",
    "RateLimitConfig",
    "RateLimitHeaders",
    "RateLimiterManager",
    "TokenBucketAdapter",
]
