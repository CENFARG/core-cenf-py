"""CENF SecretManager adapters — concrete implementations of SecretManager Protocol.

Exports:
- EncryptedSecretAdapter: Local file-based encrypted secret storage using Fernet.
- InMemorySecretAdapter: Dict-backed test double for TDD.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.secrets.adapters.encrypted_secret_adapter import (
    EncryptedSecretAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import (
    InMemorySecretAdapter,
)

__all__ = [
    "EncryptedSecretAdapter",
    "InMemorySecretAdapter",
]
