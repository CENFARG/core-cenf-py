"""CENF CacheManager models — CacheConfig, CacheEntry, StampedeConfig.

Defines the Pydantic models for CacheManager configuration and data transfer.
CacheEntry tracks TTL via monotonic timestamps; StampedeConfig controls the
XFetch probabilistic early recomputation algorithm (beta/delta).

Security: CacheEntry.value is untyped (Any) — callers MUST NOT cache
    credentials, tokens, or PII without encryption.
Observability: CacheEntry expiry events emit at DEBUG level via LoggerManager.
@ai-directive: CacheEntry.expires_at uses time.monotonic(), not wall-clock
    time, to be immune to system clock jumps.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time as _time
from typing import Any, Literal

from pydantic import BaseModel, Field


class CacheEntry(BaseModel):
    """A single cache entry with TTL tracking via monotonic timestamps.

    Uses ``time.monotonic()`` for expiry tracking — immune to system clock
    adjustments. ``is_expired()`` compares the stored ``expires_at`` against
    the current monotonic time.

    Attributes:
        key: Cache key (string identifier).
        value: The cached Python object (Any).
        expires_at: Monotonic timestamp when this entry expires.
        created_at: Monotonic timestamp when this entry was created.
    """

    key: str = Field(..., min_length=1, max_length=512, description="Cache key.")
    value: Any = Field(default=None, description="Cached Python object.")
    expires_at: float = Field(
        default_factory=_time.monotonic,
        ge=0,
        description="Monotonic timestamp when this entry expires.",
    )
    created_at: float = Field(
        default_factory=_time.monotonic,
        ge=0,
        description="Monotonic timestamp when this entry was created.",
    )

    def is_expired(self) -> bool:
        """Check if this entry has expired.

        Compares ``expires_at`` against the current ``time.monotonic()`` value.

        Returns:
            bool: ``True`` if the entry has expired, ``False`` otherwise.
        """
        return _time.monotonic() >= self.expires_at


class StampedeConfig(BaseModel):
    """XFetch algorithm parameters for stampede mitigation.

    Controls the probabilistic early recomputation of cache entries that
    are close to expiry. When ``get_or_set()`` detects an entry approaching
    its TTL, the XFetch algorithm decides whether to recompute early to
    prevent a thundering herd.

    Attributes:
        beta: Controls how aggressively early recompute triggers.
            Higher values = more aggressive. Default 1.0 (standard).
        delta: Minimum recompute window as fraction of TTL.
            Default 0.5 means compute no earlier than 0.5 * TTL.
    """

    beta: float = Field(default=1.0, ge=0.0, description="XFetch beta parameter.")
    delta: float = Field(default=0.5, ge=0.0, description="XFetch delta parameter.")


class CacheConfig(BaseModel):
    """Configuration for CacheManager adapters.

    Controls default TTL, maximum cache size, and backend selection.
    ``max_size`` limit triggers LRU-like eviction in MemoryCacheAdapter.

    Attributes:
        default_ttl: Default time-to-live in seconds for cache entries.
        max_size: Maximum number of entries before eviction kicks in.
        backend: Cache backend — ``"memory"`` (dict) or ``"redis"``.
    """

    default_ttl: int = Field(default=300, ge=0, description="Default TTL in seconds.")
    max_size: int = Field(default=10000, ge=0, description="Maximum entries before eviction.")
    backend: Literal["memory", "redis"] = Field(default="memory", description="Cache backend.")
