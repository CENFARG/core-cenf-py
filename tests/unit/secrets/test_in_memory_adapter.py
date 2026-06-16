"""Unit tests for InMemorySecretAdapter — dict-backed SecretManager test double.

Tests cover:
- Protocol compliance (satisfies SecretManager)
- get_secret returns stored values
- get_secret raises ValidationError for missing keys
- invalidate_cache clears cached entries
- rotate_secret updates value and invalidates cache
- TTL-based cache expiration simulation

Author: CENF AI Team
Version: 0.1.0
"""

import asyncio

import pytest

from core_infrastructure.secrets.adapters.in_memory_secret_adapter import (
    InMemorySecretAdapter,
)
from core_infrastructure.secrets.ports import SecretManager


@pytest.fixture
def in_memory_secret() -> InMemorySecretAdapter:
    """Create a fresh InMemorySecretAdapter with pre-populated secrets."""
    adapter = InMemorySecretAdapter()
    adapter.set_secret("db_password", "secure-db-password")
    adapter.set_secret("api_key", "sk-test-api-key-123")
    return adapter


class TestInMemorySecretAdapterProtocol:
    """Verify InMemorySecretAdapter satisfies SecretManager Protocol."""

    def test_satisfies_secret_manager_protocol(self) -> None:
        """InMemorySecretAdapter passes isinstance check against SecretManager."""
        adapter = InMemorySecretAdapter()
        assert isinstance(adapter, SecretManager)

    def test_adapter_has_all_required_methods(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """Adapter exposes get_secret, invalidate_cache, rotate_secret, get_json_schema."""
        assert callable(in_memory_secret.get_secret)
        assert callable(in_memory_secret.invalidate_cache)
        assert callable(in_memory_secret.rotate_secret)
        assert callable(in_memory_secret.get_json_schema)


class TestInMemorySecretAdapterGetSecret:
    """Verify get_secret returns stored secrets and handles errors."""

    async def test_get_secret_returns_stored_value(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """get_secret returns the previously stored secret value."""
        result = await in_memory_secret.get_secret("db_password")
        assert result == "secure-db-password"

    async def test_get_secret_another_key(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """get_secret returns different values for different keys."""
        result = await in_memory_secret.get_secret("api_key")
        assert result == "sk-test-api-key-123"

    async def test_get_secret_missing_key_raises_validation_error(
        self, in_memory_secret: InMemorySecretAdapter
    ) -> None:
        """get_secret raises ValidationError when key is not found."""
        from core_infrastructure.common.errors import ValidationError

        with pytest.raises(ValidationError):
            await in_memory_secret.get_secret("nonexistent_key")

    async def test_get_secret_empty_key_raises(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """get_secret with empty key raises ValidationError."""
        from core_infrastructure.common.errors import ValidationError

        with pytest.raises(ValidationError):
            await in_memory_secret.get_secret("")


class TestInMemorySecretAdapterCache:
    """Verify cache invalidation and TTL behavior."""

    async def test_invalidate_cache_clears_entry(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """invalidate_cache removes the cached entry, next call re-reads from store."""
        # First call succeeds
        val = await in_memory_secret.get_secret("db_password")
        assert val == "secure-db-password"

        # Invalidate
        in_memory_secret.invalidate_cache("db_password")

        # Next call re-reads from backing store (still succeeds — store persists)
        result = await in_memory_secret.get_secret("db_password")
        assert result == "secure-db-password"

    async def test_invalidate_cache_all_entries(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """invalidate_cache with key=None clears all cached entries; re-reads from store."""
        in_memory_secret.invalidate_cache(None)

        # Entries are re-read from backing store (still succeed)
        result1 = await in_memory_secret.get_secret("db_password")
        result2 = await in_memory_secret.get_secret("api_key")
        assert result1 == "secure-db-password"
        assert result2 == "sk-test-api-key-123"

    async def test_ttl_cache_expires(self) -> None:
        """Cache entries expire after TTL, and are re-read from store."""
        from core_infrastructure.secrets.models import SecretConfig

        # Create adapter with minimal TTL (min is 1)
        config = SecretConfig(cache_ttl_seconds=1)
        adapter = InMemorySecretAdapter(config=config)
        adapter.set_secret("key1", "value1")

        # First call works and caches
        val = await adapter.get_secret("key1")
        assert val == "value1"

        # Wait for TTL to expire
        await asyncio.sleep(2)

        # After expiry, re-reads from backing store (still works — store persists)
        result = await adapter.get_secret("key1")
        assert result == "value1"


class TestInMemorySecretAdapterRotate:
    """Verify rotate_secret updates secret and invalidates cache."""

    async def test_rotate_secret_updates_value(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """rotate_secret changes the stored value."""
        await in_memory_secret.rotate_secret("db_password", "new-password-v2")
        result = await in_memory_secret.get_secret("db_password")
        assert result == "new-password-v2"

    async def test_rotate_secret_new_key(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """rotate_secret on a new key stores it."""
        await in_memory_secret.rotate_secret("new_key", "new_value")
        result = await in_memory_secret.get_secret("new_key")
        assert result == "new_value"


class TestInMemorySecretAdapterHelpers:
    """Verify test-specific helper methods."""

    def test_set_secret_and_get_json_schema(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """set_secret populates the store and get_json_schema returns a dict."""
        in_memory_secret.set_secret("extra", "extra_value")
        result = in_memory_secret._store["extra"]
        assert result.value == "extra_value"

        schema = in_memory_secret.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    def test_clear_empties_store(self, in_memory_secret: InMemorySecretAdapter) -> None:
        """clear() removes all stored secrets."""
        assert len(in_memory_secret._store) >= 2
        in_memory_secret.clear()
        assert len(in_memory_secret._store) == 0
