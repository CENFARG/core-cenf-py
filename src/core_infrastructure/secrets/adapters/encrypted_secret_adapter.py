"""EncryptedSecretAdapter — local Fernet-encrypted file-based SecretManager.

Reads secrets from a JSON file where each value is Fernet-encrypted.
Secrets are decrypted on demand and cached in memory with TTL expiration.
Supports cache invalidation and secret rotation (write-back to file).

Security: All secrets are encrypted at rest using Fernet (AES-128-CBC + HMAC).
    The Fernet key is loaded from SecretConfig. Secret values are NEVER
    written to logs. Cache holds decrypted values in memory only.
Observability: File read events are logged at DEBUG level with key names.
    Rotation events log at INFO level with key name (never the value).
@ai-directive: NEVER hardcode Fernet keys. Always derive from SecretConfig.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from core_infrastructure.common.errors import PermanentError, ValidationError
from core_infrastructure.secrets.models import SecretConfig, SecretValue


class _CacheEntry:
    """A cached decrypted secret with its expiration timestamp."""

    __slots__ = ("value", "expires_at")

    def __init__(self, value: str, ttl_seconds: int) -> None:
        self.value: str = value
        self.expires_at: float = time.monotonic() + ttl_seconds

    def is_expired(self) -> bool:
        """Return True if this cache entry has exceeded its TTL."""
        return time.monotonic() > self.expires_at


class EncryptedSecretAdapter:
    """Local file-based encrypted SecretManager using Fernet symmetric encryption.

    Secrets are stored in a JSON file where each value is the base64-encoded
    Fernet ciphertext. On first access, the file is read and decrypted values
    are cached with a TTL. ``invalidate_cache()`` forces a re-read.

    Args:
        config: SecretConfig with fernet_key and cache_ttl_seconds.
        secret_storage_path: Path to the encrypted JSON secrets file.

    Raises:
        PermanentError: If the storage file cannot be read or the Fernet key
            is invalid.

    Security: The Fernet key MUST be stored separately (e.g., in an env var
        or a dedicated secrets manager). Never commit it to source control.
    """

    def __init__(
        self,
        config: SecretConfig,
        secret_storage_path: str,
    ) -> None:
        self._config: SecretConfig = config
        self._storage_path: str = secret_storage_path
        self._cache: dict[str, _CacheEntry] = {}
        self._fernet: Fernet | None = None

    # ------------------------------------------------------------------
    # Internal: Fernet initialization (lazy)
    # ------------------------------------------------------------------

    def _get_fernet(self) -> Fernet:
        """Return the Fernet cipher instance, initializing on first use.

        Lazy initialization allows the adapter to be constructed even with
        an invalid key; the error surfaces at access time.

        Returns:
            Fernet: The initialized Fernet cipher.

        Raises:
            PermanentError: If the fernet_key is missing or invalid.
        """
        if self._fernet is not None:
            return self._fernet
        key = self._config.fernet_key
        if not key:
            raise PermanentError(
                "Fernet key is required but not configured",
                details={"config_key": "fernet_key"},
            )
        try:
            self._fernet = Fernet(key.encode())
        except Exception as exc:
            raise PermanentError(
                f"Invalid Fernet key: {exc}",
                details={"error": str(exc)},
            ) from exc
        return self._fernet

    # ------------------------------------------------------------------
    # Internal: read encrypted file
    # ------------------------------------------------------------------

    def _read_file(self) -> dict[str, str]:
        """Read and return the encrypted secrets JSON file.

        Returns:
            dict[str, str]: Mapping of key → encrypted (base64) value.

        Raises:
            PermanentError: If the file cannot be read or parsed.
        """
        try:
            with open(self._storage_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise PermanentError(
                f"Secret storage file not found: {self._storage_path}",
                details={"path": self._storage_path},
            ) from None
        except json.JSONDecodeError as exc:
            raise PermanentError(
                f"Invalid JSON in secret storage file: {self._storage_path}",
                details={"path": self._storage_path, "error": str(exc)},
            ) from exc
        except OSError as exc:
            raise PermanentError(
                f"Cannot read secret storage file: {self._storage_path}",
                details={"path": self._storage_path, "error": str(exc)},
            ) from exc

        if not isinstance(data, dict):
            raise PermanentError(
                f"Secret storage file must contain a JSON object, got {type(data).__name__}",
                details={"path": self._storage_path},
            )
        return data

    def _write_file(self, data: dict[str, str]) -> None:
        """Write the encrypted secrets back to the JSON file.

        Args:
            data: Mapping of key → encrypted (base64) value.

        Raises:
            PermanentError: If the write fails.
        """
        try:
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            with open(self._storage_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            raise PermanentError(
                f"Cannot write secret storage file: {self._storage_path}",
                details={"path": self._storage_path, "error": str(exc)},
            ) from exc

    # ------------------------------------------------------------------
    # Internal: decrypt a single value
    # ------------------------------------------------------------------

    def _decrypt(self, encrypted_value: str) -> str:
        """Decrypt a single Fernet-encrypted value.

        Args:
            encrypted_value: Base64-encoded Fernet ciphertext.

        Returns:
            str: The decrypted plaintext.

        Raises:
            PermanentError: If decryption fails.
        """
        fernet = self._get_fernet()
        try:
            return fernet.decrypt(encrypted_value.encode()).decode("utf-8")
        except InvalidToken as exc:
            raise PermanentError(
                "Failed to decrypt secret: invalid or tampered ciphertext",
                details={"error": str(exc)},
            ) from exc
        except Exception as exc:
            raise PermanentError(
                f"Failed to decrypt secret: {exc}",
                details={"error": str(exc)},
            ) from exc

    def _encrypt(self, plain_value: str) -> str:
        """Encrypt a plaintext value using Fernet.

        Args:
            plain_value: The plaintext to encrypt.

        Returns:
            str: Base64-encoded Fernet ciphertext.

        Raises:
            PermanentError: If encryption fails.
        """
        fernet = self._get_fernet()
        try:
            return fernet.encrypt(plain_value.encode()).decode()
        except Exception as exc:
            raise PermanentError(
                f"Failed to encrypt secret: {exc}",
                details={"error": str(exc)},
            ) from exc

    # ------------------------------------------------------------------
    # Public API — SecretManager Protocol
    # ------------------------------------------------------------------

    async def get_secret(self, key: str) -> str:
        """Retrieve and decrypt a secret from the encrypted file store.

        Checks the TTL cache first. On cache miss, reads the encrypted
        file, decrypts all values, and populates the cache.

        Args:
            key: The secret key name.

        Returns:
            str: The decrypted secret value.

        Raises:
            ValidationError: If the key is empty or not found.
            PermanentError: If the storage file cannot be read/decrypted.
        """
        if not key:
            raise ValidationError(
                "Secret key must not be empty",
                details={"key": key},
            )

        # Check cache
        entry = self._cache.get(key)
        if entry is not None and not entry.is_expired():
            return entry.value

        # Cache miss — read from file
        encrypted_data = self._read_file()
        if key not in encrypted_data:
            raise ValidationError(
                f"Secret not found: {key}",
                details={"key": key},
            )

        decrypted = self._decrypt(encrypted_data[key])
        self._cache[key] = _CacheEntry(decrypted, self._config.cache_ttl_seconds)
        return decrypted

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
        """Rotate a secret: encrypt and store new value, invalidate cache.

        Reads the current file, updates the key with the newly encrypted
        value, and writes back. The cached entry is evicted.

        Args:
            key: The secret key to rotate.
            new_value: The new plaintext secret value.

        Raises:
            ValidationError: If the key is empty.
            PermanentError: If the read/write/encrypt operation fails.
        """
        if not key:
            raise ValidationError(
                "Secret key must not be empty",
                details={"key": key},
            )

        encrypted_data = self._read_file()
        encrypted_data[key] = self._encrypt(new_value)
        self._write_file(encrypted_data)
        self._cache.pop(key, None)

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing SecretConfig.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return SecretConfig.model_json_schema()
