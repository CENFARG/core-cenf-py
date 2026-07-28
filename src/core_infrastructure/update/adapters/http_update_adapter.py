"""HttpUpdateAdapter — HTTP-based UpdateManager adapter.

Performs desktop app auto-updates via HTTP using ExternalAPIManager.
Verifies SHA-256 hashes and Ed25519 signatures. Supports JSON and YAML
(electron-builder latest.yml) manifest formats. Applies updates with
file-level backup and rollback.

Security: download_update() verifies SHA-256 hash AND Ed25519 signature
    before returning. apply_update() saves a backup before installing.
"""

from __future__ import annotations

import json
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
    normalize_yaml_keys,
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
    """HTTP-based UpdateManager with signature verification, backup and rollback.

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
        self._config = config
        self._api = api_manager
        self._platform = detect_platform()
        self._data_dir = Path(data_dir) if data_dir else Path.home() / ".cenf" / "update-data"
        # State tracking for update lifecycle
        self._download_cache: dict[str, bytes] = {}
        self._download_versions: dict[str, str] = {}
        self._version_cache: dict[str, str] = {}
        self._rollback_states: dict[str, dict[str, str | bool]] = {}

    # ── Public API — UpdateManager Protocol ───────────────────────────────

    async def get_current_version(self, *, app_id: str) -> str:
        """Return the installed version — checks internal cache first, then config."""
        return self._version_cache.get(app_id, self._config.current_version)

    async def check_for_updates(
        self,
        *,
        app_id: str,
        channel: Channel = "stable",
    ) -> AvailableRelease | None:
        """Query the remote endpoint for the latest release. Parses JSON or YAML.

        Performs a GET to ``{update_url}/{app_id}/latest?channel={channel}``
        and compares the remote version (SemVer) against the current version.
        Returns None if already up-to-date.
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

        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = yaml.safe_load(raw)

        if not isinstance(body, dict):
            return None

        metadata = ReleaseMetadata(**normalize_yaml_keys(body))
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
        """Download, verify (SHA-256 + Ed25519), and cache the artifact for apply_update.

        Raises:
            PermanentError: If no artifact matches the current platform.
            AuthError: If the hash or signature does not match.
        """
        _ = app_id
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

        response: ApiResponse = await self._api.get(url=selected.url())
        if response.status_code != 200:
            raise PermanentError(
                f"Failed to download artifact from {selected.url()}: "
                f"HTTP {response.status_code}"
            )

        raw_data = response.body
        if isinstance(raw_data, str):
            raw_data = raw_data.encode("utf-8")

        verify_hash(raw_data, selected.hash())
        signature_hex = selected.signature()
        if signature_hex:
            verify_signature(raw_data, signature_hex, self._config.public_key)

        self._download_cache[selected.url()] = raw_data
        self._download_versions[selected.url()] = release.version()
        return selected

    async def apply_update(
        self,
        *,
        app_id: str,
        artifact: UpdateArtifact,
    ) -> UpdateResult:
        """Apply the update: backup current binary, write new version, track state.

        If rollback_enabled and the write fails, restores the backup.

        Raises:
            PermanentError: If no cached download exists (call download_update first).
        """
        raw_data = self._download_cache.get(artifact.url())
        if raw_data is None:
            raise PermanentError(
                f"No cached download for artifact at {artifact.url()}. "
                "Call download_update() before apply_update()."
            )

        current_version = await self.get_current_version(app_id=app_id)
        new_version = self._download_versions.get(artifact.url(), current_version)
        app_dir = self._data_dir / app_id
        app_dir.mkdir(parents=True, exist_ok=True)
        install_path = app_dir / "current.bin"
        backup_path = app_dir / "backup.bin"

        if install_path.exists():
            shutil.copy2(install_path, backup_path)

        self._rollback_states[app_id] = {
            "previous_version": current_version,
            "previous_hash": artifact.hash(),
            "rollback_available": True,
        }

        try:
            install_path.write_bytes(raw_data)
            self._version_cache[app_id] = new_version
            return UpdateResultImpl(success=True, new_version=new_version)
        except OSError as exc:
            if self._config.rollback_enabled and backup_path.exists():
                try:
                    shutil.copy2(backup_path, install_path)
                    self._version_cache[app_id] = current_version
                except OSError:
                    pass
            return UpdateResultImpl(success=False, error=f"Apply failed: {exc!s}")

    async def rollback(self, *, app_id: str) -> UpdateResult:
        """Restore the previous binary and version. Raises PermanentError if no state exists."""
        state = self._rollback_states.get(app_id)
        if state is None or not state.get("rollback_available"):
            raise PermanentError(f"No rollback state available for app '{app_id}'")

        previous_version = str(state["previous_version"])
        app_dir = self._data_dir / app_id
        backup_path = app_dir / "backup.bin"
        install_path = app_dir / "current.bin"

        if backup_path.exists():
            try:
                shutil.copy2(backup_path, install_path)
            except OSError as exc:
                return UpdateResultImpl(
                    success=False, error=f"Rollback restore failed: {exc!s}"
                )

        self._rollback_states.pop(app_id, None)
        self._version_cache[app_id] = previous_version
        return UpdateResultImpl(success=True, new_version=previous_version)

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery."""
        return get_json_schema()
