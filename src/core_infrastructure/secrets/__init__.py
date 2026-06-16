"""CENF SecretManager — secure credential management with encrypted storage.

Implements zero-trust secret management: all secrets are encrypted at rest
using Fernet symmetric encryption. Provides TTL-based caching with explicit
invalidation and rotation support. Never logs raw secret values.

Security: SecretValue.__repr__ is ALWAYS masked. Fernet keys are derived
    from SecretConfig and never hardcoded.
Observability: Secret access events are logged at DEBUG level (key name only,
    never the value). Cache misses trigger INFO logs.
@ai-directive: NEVER log raw secret values. Use SecretValue.get_masked()
    for any logging or display context.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.secrets.adapters.encrypted_secret_adapter import (
    EncryptedSecretAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import (
    InMemorySecretAdapter,
)
from core_infrastructure.secrets.models import SecretConfig, SecretRef, SecretValue
from core_infrastructure.secrets.ports import SecretManager

__all__ = [
    "EncryptedSecretAdapter",
    "InMemorySecretAdapter",
    "SecretConfig",
    "SecretManager",
    "SecretRef",
    "SecretValue",
]
