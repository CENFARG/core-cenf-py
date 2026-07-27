"""Unit tests for UpdateManager crypto helpers.

Tests cover:
- compute_shasum() SHA-256 + SHA-512 dual hash from file content
- verify_signature() Ed25519 verification with valid keys
- verify_signature() rejects invalid/tampered signatures

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core_infrastructure.update.helpers import compute_shasum, verify_signature


class TestComputeShasum:
    """Verify compute_shasum produces correct dual SHA-256/SHA-512 hashes."""

    def test_known_content_returns_dual_hash(self) -> None:
        """SHA-256 + SHA-512 delimited by colon for known input."""
        content = b"hello world\n"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            result = compute_shasum(tmp_path)
            # SHA-256 of b"hello world\n" (with newline)
            expected_sha256 = "a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447"
            # SHA-512 of b"hello world\n"
            expected_sha512 = (
                "b7f5117be2be3d6c7971226fa12f7943651c47e8b35e6a5b"
                "9c6b9db20fe19789560f14f058ba72defaeb5d0dd4de61d9"
                "ced955f89714c41258d1c73e85ee5d63"
            )
            assert result == f"{expected_sha256}:{expected_sha512}", (
                f"Expected dual hash, got {result}"
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_empty_file_returns_dual_hash(self) -> None:
        """Empty file still produces valid SHAs with colon delimiter."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            tmp_path = Path(f.name)

        try:
            result = compute_shasum(tmp_path)
            sha256_part, sha512_part = result.split(":", maxsplit=1)
            assert len(sha256_part) == 64, "SHA-256 must be 64 hex chars"
            assert len(sha512_part) == 128, "SHA-512 must be 128 hex chars"
            assert all(c in "0123456789abcdef" for c in sha256_part)
            assert all(c in "0123456789abcdef" for c in sha512_part)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_large_content_produces_consistent_hash(self) -> None:
        """Repeated call on same file returns identical hash."""
        content = b"A" * 1024 * 1024  # 1 MB
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dat") as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            first = compute_shasum(tmp_path)
            second = compute_shasum(tmp_path)
            assert first == second, "Deterministic hash must be identical across calls"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_raises_on_nonexistent_file(self) -> None:
        """FileNotFoundError raised for missing path."""
        missing = Path("/tmp/does_not_exist_12345.bin")
        with pytest.raises(FileNotFoundError):
            compute_shasum(missing)


class TestVerifySignature:
    """Verify Ed25519 signature verification with cryptography library."""

    def test_valid_signature_returns_true(self) -> None:
        """verify_signature returns True when signature is valid."""
        data = b"important update artifact content"
        sig, pub_key = _sign_with_ed25519(data)
        assert verify_signature(data, sig, pub_key) is True

    def test_invalid_data_returns_false(self) -> None:
        """verify_signature returns False when data has been tampered."""
        data = b"original content"
        sig, pub_key = _sign_with_ed25519(data)
        tampered = b"tampered content"
        assert verify_signature(tampered, sig, pub_key) is False

    def test_invalid_signature_returns_false(self) -> None:
        """verify_signature returns False when signature bytes are garbage."""
        data = b"some data"
        _sig, pub_key = _sign_with_ed25519(data)
        fake_sig = b"\x00" * 64
        assert verify_signature(data, fake_sig, pub_key) is False

    def test_wrong_public_key_returns_false(self) -> None:
        """verify_signature returns False when using a different public key."""
        data = b"test data"
        sig, _pub_key = _sign_with_ed25519(data)
        _, wrong_pub_key = _generate_ed25519_keypair()
        assert verify_signature(data, sig, wrong_pub_key) is False


# ── Test helpers ──────────────────────────────────────────────────────────


def _generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Generate a fresh Ed25519 keypair.

    Returns:
        tuple[bytes, bytes]: (private_key_bytes, public_key_bytes)
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes_raw()
    public_bytes = private_key.public_key().public_bytes_raw()
    return private_bytes, public_bytes


def _sign_with_ed25519(data: bytes) -> tuple[bytes, bytes]:
    """Sign data with a fresh Ed25519 key.

    Returns:
        tuple[bytes, bytes]: (signature, public_key_bytes)
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.generate()
    signature = private_key.sign(data)
    public_bytes = private_key.public_key().public_bytes_raw()
    return signature, public_bytes
