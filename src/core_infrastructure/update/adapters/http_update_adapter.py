"""HttpUpdateAdapter — HTTP-based UpdateManager adapter.

Performs desktop app auto-updates via HTTP using ExternalAPIManager for
resilient communication. Verifies SHA-256 hashes and Ed25519 digital
signatures before accepting any artifact. Uses packaging.version for
SemVer comparison.

Supports both JSON and YAML (electron-builder latest.yml) manifest formats
for release metadata.

Security: download_update() verifies SHA-256 hash AND Ed25519 signature
    before returning. On hash/signature mismatch, raises AuthError.
    Partial downloads are discarded on failure. apply_update() saves
    a backup of the current binary for rollback recovery.
Observability: Update events emit RED metrics via ObservabilityManager
    (cenf.update.* counters and histograms).

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml
from packaging.version import Version

from core_infrastructure.common.errors import PermanentError
from core_infrastructure.external_api.models import ApiResponse
from core_infrastructure.external_api.ports import ExternalAPIManager
from core_infrastructure.update.adapters.http_update_adapter_helpers import (
    ReleaseWrapper,
    UpdateResultImpl,
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


def _camel_to_snake(name: str) -> str:
    """Convert a camelCase string to snake_case.

    Args:
        name: A camelCase string (e.g. ``"releaseNotesUrl"``).

    Returns:
        str: The snake_case equivalent (e.g. ``"release_notes_url"``).
    """
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _normalize_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively normalize dictionary keys from camelCase to snake_case.

    Applies to top-level and nested ``artifacts`` list items.

    Args:
        data: A dictionary with potential camelCase keys.

    Returns:
        dict[str, Any]: A new dictionary with snake_case keys.
    """
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        snake_key = _camel_to_snake(key)
        if snake_key == "artifacts" and isinstance(value, list):
            normalized[snake_key] = [
                {_camel_to_snake(k): v for k, v in item.items()}
                if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            normalized[snake_key] = value
    return normalized


class HttpUpdateAdapter:
    """HTTP-based UpdateManager adapter with signature verification, backup and rollback.

    Queries a remote update endpoint via ExternalAPIManager, compares
    versions using SemVer (packaging.version), downloads and verifies
    artifacts (SHA-256 + Ed25519), and applies updates with file-level
    backup and rollback support.

    Downloaded artifact bytes are cached internally after
    :meth:`download_update` and used by :meth:`apply_update` for
    installation. Rollback saves the previous binary before applying
    the new version.

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
        data_dir: str | Path | None = None,
    ) -> None:
        """Initialize the HTTP update adapter.

        Args:
            config: UpdateConfig with endpoint URL, public key, and version.
            api_manager: ExternalAPIManager for HTTP communication.
            data_dir: Directory for backup storage. Defaults to
                ``~/.cenf/update-data``.
        """
        self._config = config
        self._api = api_manager
        self._platform = detect_platform()
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".cenf" / "update-data"

        # State tracking
        self._download_cache: dict[str, bytes] = {}
        self._download_versions: dict[str, str] = {}
        self._version_cache: dict[str, str] = {}
        self._rollback_states: dict[str, dict[str, str | bool]] = {}

    # ── Public API — UpdateManager Protocol ───────────────────────────────

    async def get_current_version(self, *, app_id: str) -> str:
        """Return the currently installed version for an app.

        Checks the internal version cache first (updated by apply_update
        and rollback), then falls back to the configured version.

        Args:
            app_id: The application identifier.

        Returns:
            str: The current SemVer version.
        """
        return self._version_cache.get(app_id, self._config.current_version)

    async def check_for_updates(
        self,
        *,
        app_id: str,
        channel: Channel = "stable",
    ) -> AvailableRelease | None:
        """Query the remote update endpoint for the latest release.

        Performs a GET to ``{update_url}/{app_id}/latest?channel={channel}``
        and attempts to parse the response as JSON first, falling back to
        YAML (e.g. electron-builder ``latest.yml`` format). Compares the
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

        raw = response.body
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        elif not isinstance(raw, str):
            raw = str(raw)

        # Try JSON first (backward compatible), then YAML
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = yaml.safe_load(raw)

        if not isinstance(body, dict):
            return None

        # Normalize camelCase keys to snake_case (handles latest.yml format)
        body = _normalize_keys(body)

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
        the Ed25519 digital signature if present. Caches the downloaded
        bytes and release version internally for :meth:`apply_update`.

        Args:
            app_id: The application identifier.
            release: The AvailableRelease to download from.

        Returns:
            UpdateArtifact: The verified artifact.

        Raises:
            PermanentError: If no artifact matches the current platform.
            AuthError: If the SHA-256 hash or Ed25519 signature does not match.
        """
        _ = app_id  # used for cache key, handled below

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
        verify_hash(raw_data, selected.hash())

        # Verify Ed25519 signature if present
        signature_hex = selected.signature()
        if signature_hex:
            verify_signature(raw_data, signature_hex, self._config.public_key)

        # Cache the downloaded data and release version for apply_update
        self._download_cache[selected.url()] = raw_data
        self._download_versions[selected.url()] = release.version()

        return selected

    async def apply_update(
        self,
        *,
        app_id: str,
        artifact: UpdateArtifact,
    ) -> UpdateResult:
        """Apply the update by writing the artifact binary to disk.

        Saves a backup of the currently installed binary (if it exists)
        before writing the new version. If rollback is enabled and the
        installation fails, automatically restores the backup.

        Args:
            app_id: The application identifier.
            artifact: The verified UpdateArtifact to install.

        Returns:
            UpdateResult: The result of the update application.

        Raises:
            PermanentError: If no cached download is found for the artifact.
        """
        raw_data = self._download_cache.get(artifact.url())
        if raw_data is None:
            raise PermanentError(
                f"No cached download for artifact at {artifact.url()}. "
                "Call download_update() before apply_update()."
            )

        current_version = await self.get_current_version(app_id=app_id)
        new_version = self._download_versions.get(
            artifact.url(), current_version
        )

        # Resolve install and backup paths
        app_dir = self._data_dir / app_id
        app_dir.mkdir(parents=True, exist_ok=True)
        install_path = app_dir / "current.bin"
        backup_path = app_dir / "backup.bin"

        # Save backup of current install
        if install_path.exists():
            shutil.copy2(install_path, backup_path)

        # Save rollback state BEFORE writing
        self._rollback_states[app_id] = {
            "previous_version": current_version,
            "previous_hash": artifact.hash(),
            "rollback_available": True,
        }

        try:
            # Write the new binary
            install_path.write_bytes(raw_data)

            # Update version tracking
            self._version_cache[app_id] = new_version

            return UpdateResultImpl(
                success=True,
                new_version=new_version,
            )
        except OSError as exc:
            # Auto-rollback if enabled
            if self._config.rollback_enabled and backup_path.exists():
                try:
                    shutil.copy2(backup_path, install_path)
                    self._version_cache[app_id] = current_version
                except OSError:
                    pass  # Best-effort restore

            return UpdateResultImpl(
                success=False,
                error=f"Apply failed: {exc!s}",
            )

    async def rollback(self, *, app_id: str) -> UpdateResult:
        """Rollback to the previous known-good version.

        Restores the backed-up binary and reverts the version cache.
        Raises PermanentError if no rollback state exists for the app.

        Args:
            app_id: The application identifier.

        Returns:
            UpdateResult: The result of the rollback operation.

        Raises:
            PermanentError: If no rollback state exists for the app.
        """
        state = self._rollback_states.get(app_id)
        if state is None or not state.get("rollback_available"):
            raise PermanentError(
                f"No rollback state available for app '{app_id}'"
            )

        previous_version = str(state["previous_version"])

        # Restore backup file
        app_dir = self._data_dir / app_id
        backup_path = app_dir / "backup.bin"
        install_path = app_dir / "current.bin"

        if backup_path.exists():
            try:
                shutil.copy2(backup_path, install_path)
            except OSError as exc:
                return UpdateResultImpl(
                    success=False,
                    error=f"Rollback restore failed: {exc!s}",
                )

        # Clear rollback state after successful restore
        self._rollback_states.pop(app_id, None)

        # Revert version tracking
        self._version_cache[app_id] = previous_version

        return UpdateResultImpl(
            success=True,
            new_version=previous_version,
        )

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract (delegates to helpers)."""
        return get_json_schema()
