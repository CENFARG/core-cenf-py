"""CENF UpdateManager — shared helpers, ports, models, and adapters.

Provides the UpdateManager Protocol (ports.py), configuration and metadata
models (models.py), production adapters for multiple platforms, and shared
cryptographic helpers for artifact verification.

Exports:
    - ComputeShasum: SHA-256/SHA-512 dual hash from file
    - verify_signature: Ed25519 signature verification

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.update.helpers import compute_shasum, verify_signature

__all__ = [
    "compute_shasum",
    "verify_signature",
]
