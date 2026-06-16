"""SecretManager Protocol — the contract every secret adapter must satisfy.

Defines the secure credential management interface consumed by infrastructure
managers that need secrets (AuthManager for signing keys, DatabaseManager
for connection strings, etc.). Adapters implement encrypted file storage
(EncryptedSecretAdapter) or in-memory dict (InMemorySecretAdapter for testing).

Security: get_secret() returns a str — callers are responsible for NOT
    logging or displaying the raw value. SecretValue masks itself in __repr__.
Observability: Every get_secret() call is logged at DEBUG level with key
    name and namespace (never the value).
@ai-directive: All secret adapters MUST mask secrets in __repr__ and logs.
    NEVER add a method that returns raw secrets without masking warnings.

Author: CENF AI Team
Version: 0.1.0
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SecretManager(Protocol):
    """Secure credential management contract for all infrastructure managers.

    All managers that need secrets (AuthManager, DatabaseManager, CacheManager,
    etc.) read secrets exclusively through this interface. Concrete adapters
    provide encrypted file storage or in-memory test doubles.

    Rules:
        - get_secret() is async — may read from file/network.
        - invalidate_cache() clears cached values immediately.
        - rotate_secret() writes new value and invalidates cache.
        - get_json_schema() enables LLM agent discovery.

    Security: NEVER log the return value of get_secret(). Use
        SecretValue.get_masked() for display purposes.

    @ai-directive: When adding a new method, update all adapter implementations
        AND ensure SecretValue.__repr__ masking covers any new return paths.
    """

    async def get_secret(self, key: str) -> str:
        """Retrieve a decrypted secret by its key.

        Args:
            key: The secret key name (e.g., ``"db_password"``).

        Returns:
            str: The decrypted secret value.

        Raises:
            ValidationError: If the key is not found or is empty.
            PermanentError: If the storage backend is corrupted/unreachable.

        Security: The returned string MUST NOT be logged or serialized
            without masking. Use ``SecretValue(value).get_masked()``.
        """
        ...

    def invalidate_cache(self, key: str | None = None) -> None:
        """Invalidate cached secret entries.

        Args:
            key: Specific key to invalidate, or ``None`` to invalidate all.

        Security: Called after secret rotation to ensure stale values
            are never returned. Must be safe to call concurrently.
        """
        ...

    async def rotate_secret(self, key: str, new_value: str) -> None:
        """Store a new value for the given key and invalidate its cache.

        Args:
            key: The secret key to rotate.
            new_value: The new secret value to store.

        Raises:
            PermanentError: If the write to backing storage fails.

        Security: The old value is immediately evicted from cache.
        """
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing SecretConfig.

        Used by LLM agents for tool discovery (AX — Agent Experience).

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        ...
