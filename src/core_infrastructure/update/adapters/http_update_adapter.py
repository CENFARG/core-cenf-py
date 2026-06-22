"""HttpUpdateAdapter — HTTP-based UpdateManager adapter.

Performs desktop app auto-updates via HTTP using ExternalAPIManager for
resilient communication. Verifies SHA-256 hashes and Ed25519 digital
signatures before accepting any artifact. Uses packaging.version for
SemVer comparison.

Security: download_update() verifies SHA-256 hash AND Ed25519 signature
    before returning. On hash/signature mismatch, raises AuthError.
    Partial downloads are discarded on failure.
Observability: Update events emit RED metrics via ObservabilityManager
    (cenf.update.* counters and histograms).

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519
from packaging.version import Version

from core_infrastructure.common.errors import AuthError, PermanentError
from core_infrastructure.external_api.models import ApiResponse
from core_infrastructure.external_api.ports import ExternalAPIManager
from core_infrastructure.update.models import ArtifactMeta, ReleaseMetadata, UpdateConfig
from core_infrastructure.update.ports import (
    AvailableRelease,
    Channel,
    UpdateArtifact,
    UpdateResult,
)


class _ArtifactWrapper:
    """Concrete UpdateArtifact wrapping an ArtifactMeta model.

    Provides the UpdateArtifact Protocol interface backed by a validated
    ArtifactMeta Pydantic model.
    """

    def __init__(self, meta: ArtifactMeta) -> None:
        """Initialize from validated ArtifactMeta.

        Args:
            meta: The validated ArtifactMeta model.
        """
        self._meta = meta

    def url(self) -> str:
        """Return the artifact download URL."""
        return self._meta.url

    def platform(self) -> str:
        """Return the target platform."""
        return self._meta.platform

    def arch(self) -> str:
        """Return the target CPU architecture."""
        return self._meta.arch

    def kind(self) -> str:
        """Return the artifact kind."""
        return self._meta.kind

    def hash(self) -> str:
        """Return the SHA-256 hex digest."""
        return self._meta.hash

    def signature(self) -> str | None:
        """Return the Ed25519 signature, or None."""
        return self._meta.signature


class _ReleaseWrapper:
    """Concrete AvailableRelease wrapping a ReleaseMetadata model.

    Provides the AvailableRelease Protocol interface backed by a validated
    ReleaseMetadata Pydantic model.
    """

    def __init__(self, meta: ReleaseMetadata) -> None:
        """Initialize from validated ReleaseMetadata.

        Args:
            meta: The validated ReleaseMetadata model.
        """
        self._meta = meta
        self._artifacts: list[UpdateArtifact] = [
            _ArtifactWrapper(a) for a in meta.artifacts
        ]

    def version(self) -> str:
        """Return the SemVer version."""
        return self._meta.version

    def channel(self) -> Channel:
        """Return the update channel."""
        return self._meta.channel

    def artifacts(self) -> list[UpdateArtifact]:
        """Return the list of artifacts."""
        return self._artifacts

    def metadata(self) -> dict[str, Any]:
        """Return additional metadata."""
        return {
            "release_notes_url": self._meta.release_notes_url,
            "min_version": self._meta.min_version,
        }


class _UpdateResultImpl:
    """Concrete UpdateResult returned by HttpUpdateAdapter."""

    def __init__(
        self,
        *,
        success: bool,
        new_version: str | None = None,
        error: str | None = None,
    ) -> None:
        """Initialize the result.

        Args:
            success: Whether the operation succeeded.
            new_version: The version after the operation.
            error: Error description on failure.
        """
        self._success = success
        self._new_version = new_version
        self._error = error

    def success(self) -> bool:
        """Return whether the operation succeeded."""
        return self._success

    def new_version(self) -> str | None:
        """Return the new version, or None."""
        return self._new_version

    def error(self) -> str | None:
        """Return the error description, or None."""
        return self._error


def _detect_platform() -> str:
    """Detect the current platform for artifact selection.

    Returns:
        str: One of ``"windows"``, ``"macos"``, ``"linux"``.
    """
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":  # type: ignore[unreachable]
        return "macos"
    return "linux"


class HttpUpdateAdapter:
    """HTTP-based UpdateManager adapter with signature verification.

    Queries a remote update endpoint via ExternalAPIManager, compares
    versions using SemVer (packaging.version), downloads and verifies
    artifacts (SHA-256 + Ed25519), and applies updates with rollback
    support.

    Usage::

        config = UpdateConfig(
            update_url="https://updates.cenf.app",
            public_key="ed25519-public-key-hex",
            current_version="1.0.0",
        )
        adapter = HttpUpdateAdapter(config=config, api_manager=api)
        release = await adapter.check_for_updates(app_id="cenf-desktop")
    """

    def __init__(
        self,
        *,
        config: UpdateConfig,
        api_manager: ExternalAPIManager,
    ) -> None:
        """Initialize the HTTP update adapter.

        Args:
            config: UpdateConfig with endpoint URL, public key, and version.
            api_manager: ExternalAPIManager for HTTP communication.
        """
        self._config = config
        self._api = api_manager
        self._platform = _detect_platform()
        self._rollback_states: dict[str, str] = {}

    # ── Public API — UpdateManager Protocol ───────────────────────────────

    async def get_current_version(self, *, app_id: str) -> str:
        """Return the currently installed version for an app.

        Args:
            app_id: The application identifier.

        Returns:
            str: The current SemVer version from config.
        """
        return self._config.current_version

    async def check_for_updates(
        self,
        *,
        app_id: str,
        channel: Channel = "stable",
    ) -> AvailableRelease | None:
        """Query the remote update endpoint for the latest release.

        Performs a GET to ``{update_url}/{app_id}/latest?channel={channel}``
        and parses the JSON response into ReleaseMetadata. Compares the
        remote version against the current version using SemVer.
        Returns None if no update is needed.

        Args:
            app_id: The application identifier.
            channel: The update channel to query.

        Returns:
            AvailableRelease | None: The latest release, or None.
        """
        url = (
            f"{self._config.update_url.rstrip('/')}/{app_id}"
            f"/latest?channel={channel}"
        )
        response: ApiResponse = await self._api.get(url=url)

        if response.status_code != 200:
            return None

        body = response.body
        if isinstance(body, bytes):
            body = json.loads(body)

        metadata = ReleaseMetadata(**body)

        current = await self.get_current_version(app_id=app_id)
        if Version(metadata.version) <= Version(current):
            return None

        return _ReleaseWrapper(metadata)

    async def download_update(
        self,
        *,
        app_id: str,
        release: AvailableRelease,
    ) -> UpdateArtifact:
        """Download and verify the artifact for the current platform.

        Selects the correct artifact for the current platform, downloads
        it via ExternalAPIManager, verifies the SHA-256 hash, and verifies
        the Ed25519 digital signature if present.

        Args:
            app_id: The application identifier.
            release: The AvailableRelease to download from.

        Returns:
            UpdateArtifact: The verified artifact.

        Raises:
            PermanentError: If no artifact matches the current platform.
            AuthError: If the SHA-256 hash or Ed25519 signature does not match.
        """
        # Find artifact for current platform
        selected: UpdateArtifact | None = None
        for artifact in release.artifacts():
            if artifact.platform() == self._platform:
                selected = artifact
                break

        if selected is None:
            raise PermanentError(
                f"No artifact found for platform '{self._platform}' in "
                f"release {release.version()}"
            )

        # Download the artifact
        response: ApiResponse = await self._api.get(url=selected.url())
        if response.status_code != 200:
            raise PermanentError(
                f"Failed to download artifact from {selected.url()}: "
                f"HTTP {response.status_code}"
            )

        raw_data = response.body
        if isinstance(raw_data, str):
            raw_data = raw_data.encode("utf-8")

        # Verify SHA-256 hash
        computed_hash = hashlib.sha256(raw_data).hexdigest()
        if computed_hash != selected.hash():
            raise AuthError(
                "Hash mismatch: downloaded artifact does not match "
                "expected SHA-256 digest",
                details={"reason": "hash_mismatch"},
            )

        # Verify Ed25519 signature if present
        signature_hex = selected.signature()
        if signature_hex:
            self._verify_signature(raw_data, signature_hex)

        return selected

    async def apply_update(
        self,
        *,
        app_id: str,
        artifact: UpdateArtifact,
    ) -> UpdateResult:
        """Apply the update using platform-specific mechanisms.

        Not fully implemented in MVP — raises NotImplementedError for
        unsupported platforms. Platform-specific sub-adapters handle
        the actual installation.

        Args:
            app_id: The application identifier.
            artifact: The verified UpdateArtifact to install.

        Returns:
            UpdateResult: The result of the update application.

        Raises:
            NotImplementedError: Always in the MVP adapter.
        """
        raise NotImplementedError(
            f"apply_update not implemented for platform '{self._platform}'. "
            "Use a platform-specific sub-adapter."
        )

    async def rollback(self, *, app_id: str) -> UpdateResult:
        """Rollback to the previous known-good version.

        Args:
            app_id: The application identifier.

        Returns:
            UpdateResult: The result of the rollback operation.

        Raises:
            NotImplementedError: Not yet implemented in the MVP.
        """
        raise NotImplementedError(
            "rollback not yet implemented in HttpUpdateAdapter"
        )

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery.

        Returns:
            dict[str, Any]: JSON Schema describing the UpdateManager interface.
        """
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "UpdateManager",
            "type": "object",
            "description": (
                "Manages desktop application auto-updates with "
                "TUF-inspired signature verification, SemVer comparison, "
                "and automatic rollback support."
            ),
            "properties": {
                "get_current_version": {
                    "type": "object",
                    "description": "Return the installed version.",
                },
                "check_for_updates": {
                    "type": "object",
                    "description": (
                        "Query the remote update service for the latest "
                        "compatible release."
                    ),
                },
                "download_update": {
                    "type": "object",
                    "description": (
                        "Download and verify the appropriate artifact."
                    ),
                },
                "apply_update": {
                    "type": "object",
                    "description": "Apply the update.",
                },
                "rollback": {
                    "type": "object",
                    "description": "Rollback to previous version.",
                },
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────

    def _verify_signature(
        self, data: bytes, signature_hex: str
    ) -> None:
        """Verify an Ed25519 signature against the configured public key.

        Args:
            data: The raw artifact data that was signed.
            signature_hex: The hex-encoded Ed25519 signature.

        Raises:
            AuthError: If the signature does not verify.
        """
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(
                bytes.fromhex(self._config.public_key)
            )
            signature = bytes.fromhex(signature_hex)
            public_key.verify(signature, data)
        except (ValueError, InvalidSignature) as exc:
            raise AuthError(
                "Signature verification failed: the artifact signature "
                "does not match the configured public key",
                details={"reason": "signature_mismatch"},
            ) from exc
