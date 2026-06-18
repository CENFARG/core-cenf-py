"""Unit tests for EncryptedSecretAdapter — local encrypted file SecretManager.

Tests cover:
- Protocol compliance
- get_secret decrypts stored values
- TTL caching behavior
- invalidate_cache clears entries
- rotate_secret encrypts and stores new values
- Missing or corrupted storage handled gracefully

Author: CENF AI Team
Version: 0.1.0
"""

import os
import tempfile

import pytest
from cryptography.fernet import Fernet

from core_infrastructure.secrets.adapters.encrypted_secret_adapter import (
    EncryptedSecretAdapter,
)
from core_infrastructure.secrets.models import SecretConfig
from core_infrastructure.secrets.ports import SecretManager


@pytest.fixture
def fernet_key() -> bytes:
    """Generate a fresh Fernet key for testing."""
    return Fernet.generate_key()


@pytest.fixture
def temp_secret_file(fernet_key: bytes) -> str:
    """Create a temporary encrypted secrets file with known values."""
    fernet = Fernet(fernet_key)
    data = {
        "db_password": fernet.encrypt(b"secure-db-password").decode(),
        "api_key": fernet.encrypt(b"sk-test-api-key-123").decode(),
    }
    import json

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(data, tmp)
    yield tmp.name
    os.unlink(tmp.name)


@pytest.fixture
def encrypted_adapter(temp_secret_file: str, fernet_key: bytes) -> EncryptedSecretAdapter:
    """Create an EncryptedSecretAdapter pointed at the temp file."""
    config = SecretConfig(
        cache_ttl_seconds=60,
        fernet_key=fernet_key.decode(),
    )
    return EncryptedSecretAdapter(
        config=config,
        secret_storage_path=temp_secret_file,
    )


class TestEncryptedSecretAdapterProtocol:
    """Verify EncryptedSecretAdapter satisfies SecretManager Protocol."""

    def test_satisfies_secret_manager_protocol(self, encrypted_adapter: EncryptedSecretAdapter) -> None:
        """EncryptedSecretAdapter passes isinstance check against SecretManager."""
        assert isinstance(encrypted_adapter, SecretManager)


class TestEncryptedSecretAdapterGetSecret:
    """Verify encrypted secret retrieval."""

    async def test_get_secret_decrypts_stored_value(
        self, encrypted_adapter: EncryptedSecretAdapter
    ) -> None:
        """get_secret reads and decrypts from the encrypted JSON file."""
        result = await encrypted_adapter.get_secret("db_password")
        assert result == "secure-db-password"

    async def test_get_secret_another_key(
        self, encrypted_adapter: EncryptedSecretAdapter
    ) -> None:
        """Multiple keys return their respective decrypted values."""
        result = await encrypted_adapter.get_secret("api_key")
        assert result == "sk-test-api-key-123"

    async def test_get_secret_missing_key_raises(
        self, encrypted_adapter: EncryptedSecretAdapter
    ) -> None:
        """Missing key raises ValidationError."""
        from core_infrastructure.common.errors import ValidationError

        with pytest.raises(ValidationError):
            await encrypted_adapter.get_secret("nonexistent")

    async def test_get_secret_empty_key_raises(
        self, encrypted_adapter: EncryptedSecretAdapter
    ) -> None:
        """Empty key raises ValidationError."""
        from core_infrastructure.common.errors import ValidationError

        with pytest.raises(ValidationError):
            await encrypted_adapter.get_secret("")


class TestEncryptedSecretAdapterCache:
    """Verify TTL caching behavior."""

    async def test_first_call_reads_file(self, encrypted_adapter: EncryptedSecretAdapter) -> None:
        """First call to get_secret reads and decrypts from file."""
        result = await encrypted_adapter.get_secret("db_password")
        assert result == "secure-db-password"

    async def test_cache_returns_same_value(self, encrypted_adapter: EncryptedSecretAdapter) -> None:
        """Subsequent calls return cached value without re-reading file."""
        # Two calls should return the same value
        first = await encrypted_adapter.get_secret("db_password")
        second = await encrypted_adapter.get_secret("db_password")
        assert first == second == "secure-db-password"

    async def test_invalidate_cache_clears_entry(
        self, encrypted_adapter: EncryptedSecretAdapter
    ) -> None:
        """invalidate_cache removes the cached entry."""
        # Cache the value
        await encrypted_adapter.get_secret("db_password")
        encrypted_adapter.invalidate_cache("db_password")

        # After invalidation, next call re-reads file (still works)
        result = await encrypted_adapter.get_secret("db_password")
        assert result == "secure-db-password"


class TestEncryptedSecretAdapterRotate:
    """Verify secret rotation."""

    async def test_rotate_secret_updates_and_can_retrieve(
        self, encrypted_adapter: EncryptedSecretAdapter
    ) -> None:
        """rotate_secret stores and retrieves the new value."""
        await encrypted_adapter.rotate_secret("api_key", "new-api-key-v2")
        result = await encrypted_adapter.get_secret("api_key")
        assert result == "new-api-key-v2"


class TestEncryptedSecretAdapterErrors:
    """Verify error handling for edge cases."""

    async def test_missing_file_raises_permanent_error(self, fernet_key: bytes) -> None:
        """Non-existent file raises PermanentError."""
        from core_infrastructure.common.errors import PermanentError

        config = SecretConfig(
            cache_ttl_seconds=60,
            fernet_key=fernet_key.decode(),
        )
        adapter = EncryptedSecretAdapter(
            config=config,
            secret_storage_path="/nonexistent/path/secrets.json",
        )
        with pytest.raises(PermanentError):
            await adapter.get_secret("any_key")

    async def test_invalid_fernet_key_raises(self, temp_secret_file: str) -> None:
        """Invalid Fernet key raises PermanentError."""
        from core_infrastructure.common.errors import PermanentError

        config = SecretConfig(
            cache_ttl_seconds=60,
            fernet_key="not-a-valid-fernet-key",
        )
        adapter = EncryptedSecretAdapter(
            config=config,
            secret_storage_path=temp_secret_file,
        )
        with pytest.raises(PermanentError):
            await adapter.get_secret("db_password")
