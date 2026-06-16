"""CENF CacheManager — key-value cache abstraction with stampede mitigation.

Provides a Protocol-based interface for KV caching with TTL support and
XFetch stampede mitigation. InMemoryCacheAdapter implements the full
contract with probabilistic early recompute; RedisCacheAdapter is a
skeleton for future production use.

Security: Cache values are stored in-memory only — no persistence.
    NEVER cache credentials, tokens, or PII without encryption.
Observability: get_or_set() with XFetch emits ``cenf.cache.stampede_recompute_total``
    counter when probabilistic early recompute triggers.
@ai-directive: InMemoryCacheAdapter exists for dev/testing. Use
    RedisCacheAdapter in production after completing the Redis backend.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter
from core_infrastructure.cache.models import CacheConfig, CacheEntry, StampedeConfig
from core_infrastructure.cache.ports import CacheManager

__all__ = [
    "CacheConfig",
    "CacheEntry",
    "CacheManager",
    "MemoryCacheAdapter",
    "RedisCacheAdapter",
    "StampedeConfig",
]
