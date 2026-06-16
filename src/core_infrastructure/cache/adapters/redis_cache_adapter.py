"""RedisCacheAdapter — skeleton for Redis-backed CacheManager (future production use).

Provides the class structure and constructor for a Redis-based cache backend.
Redis is an optional dependency — this adapter is NOT implemented yet and
raises ``NotImplementedError`` on all methods.

Security: When implemented, Redis connection MUST use TLS and authentication
    via SecretManager. NEVER store raw Redis credentials in config.
Observability: When implemented, all operations emit ``cenf.cache.redis.*`` metrics.
@ai-directive: This is a SKELETON — do NOT use in production until the
    Redis backend is fully implemented and integration-tested.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager


class RedisCacheAdapter:
    """Skeleton for Redis-backed CacheManager.

    Raises ``NotImplementedError`` on all operations. Use this class as a
    structural placeholder — implement the Redis backend when the optional
    ``redis>=5.0`` dependency is available in production.

    Args:
        config: ConfigManager for Redis connection settings.
        secrets: SecretManager for Redis credentials.
        logger: LoggerManager for structured log emission.
    """

    def __init__(
        self,
        config: ConfigManager,
        secrets: SecretManager,
        logger: LoggerManager,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._logger = logger

    def get(self, key: str) -> Any:
        raise NotImplementedError("RedisCacheAdapter.get() is not implemented")

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        raise NotImplementedError("RedisCacheAdapter.set() is not implemented")

    def delete(self, key: str) -> None:
        raise NotImplementedError("RedisCacheAdapter.delete() is not implemented")

    def exists(self, key: str) -> bool:
        raise NotImplementedError("RedisCacheAdapter.exists() is not implemented")

    def clear(self) -> None:
        raise NotImplementedError("RedisCacheAdapter.clear() is not implemented")

    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: int | None = None) -> Any:
        raise NotImplementedError("RedisCacheAdapter.get_or_set() is not implemented")
