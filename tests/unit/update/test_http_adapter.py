"""Unit tests for HttpUpdateAdapter — HTTP-based update manager.

Tests cover:
- check_for_updates() fetches and parses release metadata from HTTP endpoint
- check_for_updates() returns None when no update is available
- SemVer comparison using packaging.version
- download_update() downloads and verifies SHA-256 hash
- download_update() raises AuthError on hash mismatch
- download_update() raises AuthError on signature mismatch (Ed25519)
- apply_update() raises PermanentError for unsupported platforms
- rollback() raises PermanentError (not implemented in MVP)
- apply_update() can be mocked via platform-specific sub-adapter
- Channel filtering (stable, beta, canary)
- get_json_schema() returns a dict
- get_current_version() returns from config

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import hashlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from core_infrastructure.common.errors import AuthError, PermanentError
from core_infrastructure.external_api.models import ApiResponse
from core_infrastructure.update.models import UpdateConfig
from core_infrastructure.update.ports import (
    Channel,
    UpdateArtifact,
    UpdateManager,
)


def _current_platform() -> str:
    """Return the current platform string matching adapter conventions."""
    if sys.platform == "win32":
        return "windows"
    elif sys.platform == "darwin":
        return "macos"
    return "linux"


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_ed25519_keypair() -> tuple[ed25519.Ed25519PrivateKey, str]:
    """Generate an Ed25519 keypair for testing.

    Returns:
        (private_key, public_key_hex): The keypair.
    """
    private = ed25519.Ed25519PrivateKey.generate()
    public_bytes = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return private, public_bytes.hex()


def _sign_data(private_key: ed25519.Ed25519PrivateKey, data: bytes) -> str:
    """Sign data with Ed25519 private key, return hex-encoded signature.

    Args:
        private_key: The Ed25519 private key.
        data: The data to sign.

    Returns:
        str: Hex-encoded signature.
    """
    return private_key.sign(data).hex()


def _compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of data.

    Args:
        data: The data to hash.

    Returns:
        str: Hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(data).hexdigest()


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def ed25519_keypair() -> tuple[ed25519.Ed25519PrivateKey, str]:
    """Ed25519 keypair for signature tests."""
    return _make_ed25519_keypair()


@pytest.fixture
def config(ed25519_keypair: tuple[ed25519.Ed25519PrivateKey, str]) -> UpdateConfig:
    """UpdateConfig with a test Ed25519 public key."""
    _, public_hex = ed25519_keypair
    return UpdateConfig(
        update_url="https://updates.example.com",
        public_key=public_hex,
        current_version="1.0.0",
    )


@pytest.fixture
def mock_api() -> MagicMock:
    """Mock ExternalAPIManager."""
    api = MagicMock()
    api.get = AsyncMock()
    api.request = AsyncMock()
    return api


@pytest.fixture
def adapter(config: UpdateConfig, mock_api: MagicMock):
    """Create an HttpUpdateAdapter with mocked ExternalAPIManager."""
    from core_infrastructure.update.adapters.http_update_adapter import (
        HttpUpdateAdapter,
    )

    return HttpUpdateAdapter(config=config, api_manager=mock_api)


# ── get_current_version ─────────────────────────────────────────────────────

class TestGetCurrentVersion:
    """Tests for get_current_version()."""

    @pytest.mark.asyncio
    async def test_returns_configured_version(self, adapter) -> None:
        """get_current_version returns version from config."""
        version = await adapter.get_current_version(app_id="test-app")
        assert version == "1.0.0"


# ── check_for_updates ───────────────────────────────────────────────────────

class TestCheckForUpdates:
    """Tests for check_for_updates()."""

    @pytest.mark.asyncio
    async def test_returns_release_when_update_available(
        self, adapter, mock_api, ed25519_keypair
    ) -> None:
        """check_for_updates returns AvailableRelease when newer version exists."""
        _, _public_hex = ed25519_keypair
        metadata = {
            "version": "1.1.0",
            "channel": "stable",
            "release_notes_url": "https://example.com/notes/1.1.0",
            "artifacts": [
                {
                    "url": "https://example.com/cenf-1.1.0.exe",
                    "platform": _current_platform(),
                    "arch": "x64",
                    "kind": "installer",
                    "hash": "a" * 64,
                    "signature": None,
                    "size_bytes": 1048576,
                }
            ],
        }
        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body=metadata,
        )

        result = await adapter.check_for_updates(
            app_id="test-app", channel="stable"
        )
        assert result is not None
        assert result.version() == "1.1.0"
        assert result.channel() == "stable"

    @pytest.mark.asyncio
    async def test_returns_none_when_same_version(
        self, adapter, mock_api
    ) -> None:
        """check_for_updates returns None when current >= latest."""
        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body={
                "version": "1.0.0",
                "channel": "stable",
                "release_notes_url": "https://example.com/notes/1.0.0",
            },
        )

        result = await adapter.check_for_updates(
            app_id="test-app", channel="stable"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_api_returns_error(
        self, adapter, mock_api
    ) -> None:
        """check_for_updates returns None when API returns non-200."""
        mock_api.get.return_value = ApiResponse(status_code=404, body={})

        result = await adapter.check_for_updates(
            app_id="test-app", channel="stable"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_channel_in_query_string(
        self, adapter, mock_api
    ) -> None:
        """check_for_updates passes channel as query parameter."""
        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body={
                "version": "1.2.0-beta",
                "channel": "beta",
                "release_notes_url": "https://example.com/notes",
            },
        )

        await adapter.check_for_updates(app_id="test-app", channel="beta")

        call_args = mock_api.get.call_args
        url = call_args.kwargs.get("url", "")
        assert "channel=beta" in url

    @pytest.mark.asyncio
    async def test_includes_app_id_in_url(
        self, adapter, mock_api
    ) -> None:
        """check_for_updates includes app_id in the request URL."""
        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body={
                "version": "1.0.0",
                "channel": "stable",
                "release_notes_url": "https://example.com/notes",
            },
        )

        await adapter.check_for_updates(app_id="cenf-desktop", channel="stable")

        call_args = mock_api.get.call_args
        url = call_args.kwargs.get("url", "")
        assert "cenf-desktop" in url


# ── download_update ─────────────────────────────────────────────────────────

class TestDownloadUpdate:
    """Tests for download_update()."""

    @pytest.mark.asyncio
    async def test_downloads_and_verifies_hash(
        self, adapter, mock_api
    ) -> None:
        """download_update verifies SHA-256 hash of downloaded artifact."""
        artifact_data = b"fake-binary-content"
        expected_hash = _compute_sha256(artifact_data)

        from core_infrastructure.update.adapters.http_update_adapter_helpers import (
            ArtifactWrapper as _ArtifactWrapper,
        )

        class _ReleaseWrapper:
            def version(self) -> str:
                return "1.1.0"

            def channel(self) -> Channel:
                return "beta"

            def release_notes_url(self) -> str | None:
                return None

            def artifacts(self) -> list:
                return [
                    _ArtifactWrapper(
                        ArtifactMeta.from_dict({
                            "url": "https://example.com/cenf-1.1.0.exe",
                            "platform": _current_platform(),
                            "arch": "x64",
                            "kind": "installer",
                            "hash": expected_hash,
                            "size_bytes": 1048576,
                        })
                    )
                ]

            def metadata(self) -> dict:
                return {}

        release = _ReleaseWrapper()

        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body=artifact_data,
        )

        artifact = await adapter.download_update(
            app_id="test-app", release=release
        )
        assert artifact.hash() == expected_hash
        assert artifact.url() == "https://example.com/cenf-1.1.0.exe"

    @pytest.mark.asyncio
    async def test_raises_auth_error_on_hash_mismatch(
        self, adapter, mock_api
    ) -> None:
        """download_update raises AuthError when SHA-256 hash does not match."""
        from core_infrastructure.update.adapters.http_update_adapter_helpers import (
            ArtifactWrapper as _ArtifactWrapper,
        )

        class _ReleaseWrapper:
            def version(self) -> str:
                return "1.1.0"

            def channel(self) -> Channel:
                return "beta"

            def release_notes_url(self) -> str | None:
                return None

            def artifacts(self) -> list:
                return [
                    _ArtifactWrapper(
                        ArtifactMeta.from_dict({
                            "url": "https://example.com/cenf-1.1.0.exe",
                            "platform": _current_platform(),
                            "arch": "x64",
                            "kind": "installer",
                            "hash": "b" * 64,  # wrong hash
                            "size_bytes": 1048576,
                        })
                    )
                ]

            def metadata(self) -> dict:
                return {}

        release = _ReleaseWrapper()
        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body=b"fake-binary-content",
        )

        with pytest.raises(AuthError, match=r"[Hh]ash"):
            await adapter.download_update(app_id="test-app", release=release)

    @pytest.mark.asyncio
    async def test_verifies_ed25519_signature(
        self, adapter, mock_api, ed25519_keypair
    ) -> None:
        """download_update verifies Ed25519 signature when present."""
        priv_key, _ = ed25519_keypair
        artifact_data = b"fake-binary-content"
        expected_hash = _compute_sha256(artifact_data)
        signature = _sign_data(priv_key, artifact_data)

        from core_infrastructure.update.adapters.http_update_adapter_helpers import (
            ArtifactWrapper as _ArtifactWrapper,
        )

        class _ReleaseWrapper:
            def version(self) -> str:
                return "1.1.0"

            def channel(self) -> Channel:
                return "stable"

            def release_notes_url(self) -> str | None:
                return None

            def artifacts(self) -> list:
                return [
                    _ArtifactWrapper(
                        ArtifactMeta.from_dict({
                            "url": "https://example.com/cenf-1.1.0.exe",
                            "platform": _current_platform(),
                            "arch": "x64",
                            "kind": "installer",
                            "hash": expected_hash,
                            "signature": signature,
                            "size_bytes": 1048576,
                        })
                    )
                ]

            def metadata(self) -> dict:
                return {}

        release = _ReleaseWrapper()
        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body=artifact_data,
        )

        artifact = await adapter.download_update(
            app_id="test-app", release=release
        )
        assert artifact.hash() == expected_hash

    @pytest.mark.asyncio
    async def test_raises_auth_error_on_signature_mismatch(
        self, adapter, mock_api, ed25519_keypair
    ) -> None:
        """download_update raises AuthError when Ed25519 signature does not verify."""
        _, _public_hex = ed25519_keypair
        # Generate a different key for the "attacker"
        wrong_priv, _ = _make_ed25519_keypair()
        artifact_data = b"fake-binary-content"
        expected_hash = _compute_sha256(artifact_data)
        tampered_sig = _sign_data(wrong_priv, artifact_data)

        from core_infrastructure.update.adapters.http_update_adapter_helpers import (
            ArtifactWrapper as _ArtifactWrapper,
        )

        class _ReleaseWrapper:
            def version(self) -> str:
                return "1.1.0"

            def channel(self) -> Channel:
                return "stable"

            def release_notes_url(self) -> str | None:
                return None

            def artifacts(self) -> list:
                return [
                    _ArtifactWrapper(
                        ArtifactMeta.from_dict({
                            "url": "https://example.com/cenf-1.1.0.exe",
                            "platform": _current_platform(),
                            "arch": "x64",
                            "kind": "installer",
                            "hash": expected_hash,
                            "signature": tampered_sig,
                            "size_bytes": 1048576,
                        })
                    )
                ]

            def metadata(self) -> dict:
                return {}

        release = _ReleaseWrapper()
        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body=artifact_data,
        )

        with pytest.raises(AuthError, match="signature"):
            await adapter.download_update(app_id="test-app", release=release)


# ── apply_update ────────────────────────────────────────────────────────────

class TestApplyUpdate:
    """Tests for apply_update()."""

    @pytest.mark.asyncio
    async def test_raises_permanent_error(self, adapter, ed25519_keypair) -> None:
        """apply_update raises PermanentError for unsupported platforms."""
        from unittest.mock import MagicMock

        artifact = MagicMock(spec=UpdateArtifact)

        with pytest.raises(PermanentError):
            await adapter.apply_update(app_id="test-app", artifact=artifact)


# ── rollback ─────────────────────────────────────────────────────────────────

class TestRollback:
    """Tests for rollback()."""

    @pytest.mark.asyncio
    async def test_raises_permanent_error(self, adapter) -> None:
        """rollback raises PermanentError (not implemented in MVP)."""
        with pytest.raises(PermanentError):
            await adapter.rollback(app_id="test-app")


# ── Protocol compliance ─────────────────────────────────────────────────────

class TestProtocolCompliance:
    """Verify the adapter satisfies the UpdateManager Protocol."""

    def test_adapter_satisfies_protocol(self, adapter) -> None:
        """HttpUpdateAdapter satisfies UpdateManager Protocol."""
        assert isinstance(adapter, UpdateManager)


# ── get_json_schema ─────────────────────────────────────────────────────────

class TestGetJsonSchema:
    """Tests for get_json_schema()."""

    def test_returns_dict(self, adapter) -> None:
        """get_json_schema returns a non-empty dict."""
        schema = adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0


# ── Ed25519 signature on stable channel ────────────────────────────────────

class TestEd25519SignatureVerification:
    """Tests for Ed25519 signature verification in download_update()."""

    @pytest.mark.asyncio
    async def test_rejects_unsigned_artifact_on_stable_channel(
        self, adapter, mock_api, ed25519_keypair
    ) -> None:
        """download_update raises AuthError when artifact on stable has no signature."""
        from core_infrastructure.update.adapters.http_update_adapter_helpers import (
            ArtifactWrapper as _ArtifactWrapper,
        )

        class _ReleaseWrapper:
            def version(self) -> str:
                return "1.1.0"

            def channel(self) -> Channel:
                return "stable"

            def release_notes_url(self) -> str | None:
                return None

            def artifacts(self) -> list:
                return [
                    _ArtifactWrapper(
                        ArtifactMeta.from_dict({
                            "url": "https://example.com/cenf-1.1.0.exe",
                            "platform": _current_platform(),
                            "arch": "x64",
                            "kind": "installer",
                            "hash": _compute_sha256(b"fake-data"),
                            "signature": None,
                            "size_bytes": 1048576,
                        })
                    )
                ]

            def metadata(self) -> dict:
                return {}

        release = _ReleaseWrapper()
        mock_api.get.return_value = ApiResponse(
            status_code=200,
            body=b"fake-data",
        )

        with pytest.raises(AuthError, match=r"(?i)unsigned artifact"):
            await adapter.download_update(app_id="test-app", release=release)


# ── Helper for constructing ArtifactMeta from dict ──────────────────────────

class ArtifactMeta:
    """Minimal dict-backed ArtifactMeta helper for test fixtures."""

    def __init__(self, data: dict) -> None:
        self._data = data

    @classmethod
    def from_dict(cls, data: dict) -> ArtifactMeta:
        """Create from a dict (test helper)."""
        return cls(data)

    @property
    def url(self) -> str:
        return self._data["url"]

    @property
    def platform(self) -> str:
        return self._data["platform"]

    @property
    def arch(self) -> str:
        return self._data["arch"]

    @property
    def kind(self) -> str:
        return self._data["kind"]

    @property
    def hash(self) -> str:
        return self._data["hash"]

    @property
    def signature(self) -> str | None:
        return self._data.get("signature")

    @property
    def size_bytes(self) -> int:
        return self._data.get("size_bytes", 1048576)
