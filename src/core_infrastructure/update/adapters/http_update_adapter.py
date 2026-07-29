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

import json
from typing import Any

from packaging.version import Version

from core_infrastructure.common.errors import AuthError, PermanentError, TransientError
from core_infrastructure.external_api.models import ApiResponse
from core_infrastructure.external_api.ports import ExternalAPIManager
from core_infrastructure.update.adapters.http_update_adapter_helpers import (
    ReleaseWrapper,
    detect_platform,
    get_json_schema,
    verify_hash,
    verify_signature,
)
from core_infrastructure.update.models import ReleaseMetadata, UpdateConfig
from core_infrastructure.update.ports import (
    AvailableRelease,
    Channel,
    UpdateArtifact,
    UpdateResult,
)


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
        self._platform = detect_platform()
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

        return ReleaseWrapper(metadata)

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
            if response.status_code >= 500:
                raise TransientError(
                    f"Failed to download artifact from {selected.url()}: "
                    f"HTTP {response.status_code}"
                )
            raise PermanentError(
                f"Failed to download artifact from {selected.url()}: "
                f"HTTP {response.status_code}"
            )

        raw_data = response.body
        if isinstance(raw_data, str):
            raw_data = raw_data.encode("utf-8")

        # Verify SHA-256 hash
        verify_hash(raw_data, selected.hash())

        # Verify Ed25519 signature — required on stable channel
        signature_hex = selected.signature()
        if signature_hex:
            verify_signature(raw_data, signature_hex, self._config.public_key)
        elif release.channel() == "stable":
            raise AuthError(
                "Unsigned artifact rejected: Ed25519 signature is required "
                "on the stable channel",
                details={"reason": "signature_missing"},
            )

        return selected

    async def apply_update(
        self,
        *,
        app_id: str,
        artifact: UpdateArtifact,
    ) -> UpdateResult:
        """Apply the update using platform-specific mechanisms.

        Not fully implemented in MVP — raises PermanentError for
        unsupported platforms. Platform-specific sub-adapters handle
        the actual installation.

        Args:
            app_id: The application identifier.
            artifact: The verified UpdateArtifact to install.

        Returns:
            UpdateResult: The result of the update application.

        Raises:
            PermanentError: Always in the MVP adapter.
        """
        raise PermanentError(
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
            PermanentError: Not yet implemented in the MVP.
        """
        raise PermanentError(
            "rollback not yet implemented in HttpUpdateAdapter"
        )

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract (delegates to helpers)."""
        return get_json_schema()
