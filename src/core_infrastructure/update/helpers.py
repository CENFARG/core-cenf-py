"""Crypto helpers for UpdateManager adapters.

Provides shared cryptographic utilities used across all production update
adapters: dual SHA-256/SHA-512 hashing for artifact verification, and
Ed25519 signature verification for TUF-inspired update security.

Design (per openspec/changes/m20-adapters/design.md):
    - compute_shasum() returns "{sha256}:{sha512}" so the port contract
      (64-char SHA-256 via UpdateArtifact.hash()) and electron-updater
      (128-char SHA-512 via latest.yml) are both satisfied without
      protocol changes.
    - verify_signature() uses cryptography.hazmat — the designated
      CENF standard crypto backend.

Security:
    - Ed25519 signatures are verified with the public key bytes directly.
      Never accept a public key as raw string without hex decoding first.
    - compute_shasum() reads the entire file into memory. For very large
      artifacts (>500 MB), consider a streaming hash instead.

@ai-directive: Always verify Ed25519 signatures before applying updates.
    Never use a public key from an untrusted source.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def compute_shasum(filepath: Path) -> str:
    """Compute the SHA-256 and SHA-512 hex digests of a file.

    Reads the entire file in binary mode and computes both hashes
    simultaneously. Returns the digests colon-delimited::

        "{sha256_hex}:{sha512_hex}"

    Args:
        filepath: Absolute or relative path to the file.

    Returns:
        str: ``"<sha256>:<sha512>"`` — 64 hex chars, colon, 128 hex chars.

    Raises:
        FileNotFoundError: If the file does not exist.
        PermissionError: If the file cannot be read.
        IsADirectoryError: If the path points to a directory.

    Example:
        >>> compute_shasum(Path("/tmp/artifact.bin"))
        'a948...a447:b7f5...5d63'
    """
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()

    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(65536)  # 64 KB buffer
            if not chunk:
                break
            sha256.update(chunk)
            sha512.update(chunk)

    return f"{sha256.hexdigest()}:{sha512.hexdigest()}"


def verify_signature(
    data: bytes,
    signature: bytes,
    public_key: bytes,
) -> bool:
    """Verify an Ed25519 signature over the given data.

    Uses ``cryptography.hazmat`` Ed25519 public key primitive. Returns
    ``True`` if the signature is valid for the data under the given public
    key, ``False`` otherwise (including invalid key bytes or malformed
    signature).

    Args:
        data: The original data that was signed.
        signature: The Ed25519 signature (64 bytes).
        public_key: The Ed25519 public key (32 bytes).

    Returns:
        bool: ``True`` if the signature is valid, ``False`` otherwise.

    Example:
        >>> verify_signature(b"data", b"\\x00" * 64, b"\\x00" * 32)
        False
    """
    try:
        pub_key = Ed25519PublicKey.from_public_bytes(public_key)
        pub_key.verify(signature, data)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
