"""CENF SecretManager models — SecretRef, SecretValue, and SecretConfig.

Defines the Pydantic models for SecretManager configuration and data transfer.
SecretValue provides automatic __repr__ masking to prevent accidental
exposure of raw secrets in logs, error messages, and debug output.

Security: SecretValue.__repr__ is ALWAYS masked. The raw value is accessible
    ONLY via the .value attribute, which callers must handle responsibly.
Observability: SecretValue.get_masked() returns a safe-for-logs representation
    showing only the last 4 characters (configurable).
@ai-directive: NEVER bypass SecretValue.__repr__ masking. If you need to see
    the raw secret, use .value directly — but never in production logs.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SecretRef — reference to a secret by key and namespace
# ---------------------------------------------------------------------------


class SecretRef(BaseModel):
    """A lightweight reference to a secret by its key and namespace.

    Used when a manager needs to declare which secret it depends on without
    actually retrieving the value at construction time. The SecretManager
    resolves the reference to a SecretValue at access time.

    Attributes:
        key: The secret key name (e.g., ``"db_password"``).
        namespace: Optional namespace for multi-tenant secret isolation.
    """

    key: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="The secret key name to retrieve.",
    )
    namespace: str = Field(
        default="default",
        min_length=1,
        max_length=128,
        description="Optional namespace for secret scoping.",
    )


# ---------------------------------------------------------------------------
# SecretValue — wrapper that masks itself in __repr__
# ---------------------------------------------------------------------------


class SecretValue(BaseModel):
    """A secret value wrapper that ALWAYS masks itself in ``__repr__``.

    The raw secret is accessible via the ``.value`` attribute. Every other
    representation (``repr()``, ``str()`` in f-strings when not explicitly
    using ``.value``) shows a masked version.

    Security: ``__repr__`` replaces all characters with ``*`` except the
        last 4. This prevents accidental exposure in logs, tracebacks, and
        debug output. The raw value is NEVER included in ``__repr__``.

    Usage::

        sv = SecretValue(value="super-secret-token-12345")
        repr(sv)  # → "SecretValue(value='*****2345')"
        sv.value  # → "super-secret-token-12345"

    Observability: Use ``get_masked()`` for safe log inclusion.
    """

    value: str = Field(
        ...,
        description="The raw secret value. NEVER log or serialize this field.",
    )

    def __repr__(self) -> str:
        """Return a masked representation — NEVER exposes the raw secret.

        Returns:
            str: A string like ``"SecretValue(value='*****2345')"``.
        """
        masked = self.get_masked()
        return f"SecretValue(value={masked!r})"

    def __str__(self) -> str:
        """Return the masked representation (same as __repr__).

        Returns:
            str: Masked secret string.
        """
        return self.__repr__()

    def get_masked(self, visible_chars: int = 4) -> str:
        """Return a masked version of the secret value.

        Replaces all but the last ``visible_chars`` characters with ``*``.

        Args:
            visible_chars: Number of trailing characters to leave visible
                (default 4).

        Returns:
            str: The masked secret (e.g., ``"*****2345"``).

        Security: Safe for use in logs, error messages, and debug output.
        """
        if not self.value:
            return "<empty>"
        if len(self.value) <= visible_chars:
            return "*" * len(self.value)
        hidden = len(self.value) - visible_chars
        return "*" * hidden + self.value[-visible_chars:]


# ---------------------------------------------------------------------------
# SecretConfig — configuration for SecretManager adapters
# ---------------------------------------------------------------------------


class SecretConfig(BaseModel):
    """Configuration for SecretManager adapters.

    Controls the encryption algorithm, cache TTL, and backend selection
    for secret storage. All adapters consume this model to configure
    their behavior.

    Attributes:
        cache_ttl_seconds: How long secrets stay in cache before re-read
            (default 300 seconds / 5 minutes).
        fernet_key: Symmetric encryption key for local storage. Must be
            a valid Fernet key (base64-encoded 32-byte key).
        max_cache_size: Maximum number of cached secret entries.
        encryption_algorithm: Currently only ``"fernet"`` is supported.
    """

    cache_ttl_seconds: int = Field(
        default=300,
        ge=1,
        le=86400,
        description="TTL in seconds before cached secrets are re-read from storage.",
    )
    fernet_key: str = Field(
        default="",
        min_length=0,
        max_length=256,
        description="Fernet symmetric encryption key (base64-encoded). Required for EncryptedSecretAdapter.",
    )
    max_cache_size: int = Field(
        default=100,
        ge=10,
        le=10000,
        description="Maximum number of secret entries held in the in-memory cache.",
    )
    encryption_algorithm: str = Field(
        default="fernet",
        pattern=r"^fernet$",
        description="Encryption algorithm. Only 'fernet' is currently supported.",
    )
