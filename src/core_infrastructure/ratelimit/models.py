"""CENF RateLimiterManager models — RateLimitConfig, BucketState, RateLimitHeaders.

Defines the Pydantic models for RateLimiterManager configuration and data
transfer. BucketState tracks the internal token bucket state; RateLimitHeaders
provides the standard rate-limit response header fields.

Security: bucket_key is never included in serialized models — it is the key.
Observability: BucketState.tokens is a float for fractional token accounting.
@ai-directive: RateLimitHeaders maps to HTTP standard headers:
    X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time as _time

from pydantic import BaseModel, Field


class RateLimitConfig(BaseModel):
    """Configuration for RateLimiterManager adapters.

    Controls default capacity, refill rate, and backend selection.

    Attributes:
        default_capacity: Default max tokens per bucket (1-10000).
        default_refill_rate: Default tokens added per second (0.1-1000.0).
        redis_enabled: Whether Redis-backed distributed rate limiting is active.
    """

    default_capacity: int = Field(default=100, ge=1, le=10000, description="Default max tokens per bucket.")
    default_refill_rate: float = Field(default=10.0, ge=0.1, le=1000.0, description="Default tokens added per second.")
    redis_enabled: bool = Field(default=False, description="Whether Redis-backed distributed rate limiting is active.")


class BucketState(BaseModel):
    """Internal state of a single token bucket.

    Tracks the current token count, last refill timestamp, capacity,
    and refill rate for the token bucket algorithm.

    Attributes:
        tokens: Current token count (fractional, >= 0).
        last_refill: Unix timestamp of the last token refill.
        capacity: Maximum tokens the bucket can hold.
        refill_rate: Tokens added per second.
    """

    tokens: float = Field(..., ge=0, description="Current token count (>= 0).")
    last_refill: float = Field(default_factory=_time.time, description="Unix timestamp of last refill.")
    capacity: int = Field(..., ge=1, le=10000, description="Maximum tokens the bucket can hold.")
    refill_rate: float = Field(..., ge=0.1, le=1000.0, description="Tokens added per second.")


class RateLimitHeaders(BaseModel):
    """Standard rate limit response headers.

    Maps to HTTP response headers for informing clients about their
    rate limit status.

    Attributes:
        limit: Total capacity (X-RateLimit-Limit).
        remaining: Remaining tokens (X-RateLimit-Remaining).
        reset: Unix timestamp when the window resets (X-RateLimit-Reset).
        retry_after: Seconds until the client should retry (Retry-After).
    """

    limit: int = Field(ge=0, description="X-RateLimit-Limit — total capacity.")
    remaining: int = Field(ge=0, description="X-RateLimit-Remaining — tokens left.")
    reset: float = Field(description="X-RateLimit-Reset — Unix timestamp of reset.")
    retry_after: float | None = Field(default=None, ge=0, description="Retry-After — seconds until retry.")
