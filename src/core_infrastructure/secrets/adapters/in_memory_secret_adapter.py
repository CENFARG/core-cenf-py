"""InMemorySecretAdapter — dict-backed SecretManager test double.

Provides a zero-dependency SecretManager implementation for unit tests.
All secrets are stored in a plain dict with TTL simulation. The adapter
satisfies the SecretManager Protocol and can be used as a drop-in
replacement in any test that needs a secret provider.

Security: Secrets stay in process memory only — no file I/O, no network.
Observability: Deterministic — always returns the same result for the
    same input. Ideal for TDD assertion cycles.
@ai-directive: This adapter exists solely for testing. NEVER use it in
    production code paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time
from typing import Any

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.secrets.models import SecretConfig, SecretValue


class _CacheEntry:
    """A cached secret with its expiration timestamp."""

    __slots__ = ("expires_at", "value")

    def __init__(self, value: SecretValue, ttl_seconds: int) -> None:
        self.value: SecretValue = value
        self.expires_at: float = time.monotonic() + ttl_seconds

    def is_expired(self) -> bool:
        """Return True if this cache entry has exceeded its TTL.

        Returns:
            bool: ``True`` if the entry has expired.
        """
        return time.monotonic() > self.expires_at


class InMemorySecretAdapter:
    """Dict-backed SecretManager for unit test assertions.

    All secrets are stored in a plain dict as ``SecretValue`` objects.
    TTL-based expiration is checked on every ``get_secret()`` call.
    Supports cache invalidation and rotation out of the box.

    Args:
        config: Optional SecretConfig for cache TTL and settings.
            If not provided, sensible defaults are used.

    Usage::

        adapter = InMemorySecretAdapter()
        adapter.set_secret("api_key", "sk-12345")
        value = await adapter.get_secret("api_key")
    """

    def __init__(self, config: SecretConfig | None = None) -> None:
        self._config: SecretConfig = config if config is not None else SecretConfig()
        self._store: dict[str, SecretValue] = {}
        self._cache: dict[str, _CacheEntry] = {}

    # ------------------------------------------------------------------
    # Public API — SecretManager Protocol
    # ------------------------------------------------------------------

    async def get_secret(self, key: str) -> str:
        """Retrieve a secret value from the in-memory store.

        Checks the TTL cache first; if the entry is present and not
        expired, returns the cached value. Otherwise, looks up the
        backing store.

        Args:
            key: The secret key to retrieve.

        Returns:
            str: The raw secret value.

        Raises:
            ValidationError: If the key is empty or not found.
        """
        if not key:
            raise ValidationError(
                "Secret key must not be empty",
                details={"key": key},
            )

        # Check cache first
        entry = self._cache.get(key)
        if entry is not None and not entry.is_expired():
            return entry.value.value

        # Cache miss — look up from store
        if key in self._store:
            sv = self._store[key]
            self._cache[key] = _CacheEntry(sv, self._config.cache_ttl_seconds)
            return sv.value

        raise ValidationError(
            f"Secret not found: {key}",
            details={"key": key},
        )

    def invalidate_cache(self, key: str | None = None) -> None:
        """Invalidate cached secret entries.

        Args:
            key: Specific key to invalidate, or ``None`` to clear all.
        """
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    async def rotate_secret(self, key: str, new_value: str) -> None:
        """Rotate a secret by storing a new value and invalidating cache.

        Args:
            key: The secret key to rotate.
            new_value: The new secret value to store.

        Raises:
            ValidationError: If the key is empty.
        """
        if not key:
            raise ValidationError(
                "Secret key must not be empty",
                details={"key": ""},
            )
        self._store[key] = SecretValue(value=new_value)
        self._cache.pop(key, None)

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing SecretConfig.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return SecretConfig.model_json_schema()

    # ------------------------------------------------------------------
    # Test-specific helpers (not part of SecretManager Protocol)
    # ------------------------------------------------------------------

    def set_secret(self, key: str, value: str) -> None:
        """Inject a secret value into the backing store for testing.

        This is a test-only method — not part of the SecretManager Protocol.
        Use it in test fixtures to pre-populate secrets.

        Args:
            key: The secret key name.
            value: The raw secret value to store.
        """
        self._store[key] = SecretValue(value=value)

    def clear(self) -> None:
        """Remove all secrets and cached entries.

        Security: Ensures no secret data leaks between test cases.
        """
        self._store.clear()
        self._cache.clear()
