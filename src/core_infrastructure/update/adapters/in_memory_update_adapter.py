"""InMemoryUpdateAdapter — dict-backed UpdateManager test double.

Provides a lightweight, zero-I/O adapter for unit testing components that
depend on UpdateManager. Pre-configured releases are stored per channel
in a dict and evaluated entirely in memory.

Supports platform-specific artifact selection, version comparison via
packaging.version, and rollback state tracking for testing update/rollback
cycles.

Security: This adapter performs NO cryptographic validation. NEVER use
    it in production.
Observability: No RED metrics emitted — this is a test-only adapter.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import sys
from typing import Any

from packaging.version import Version

from core_infrastructure.common.errors import PermanentError
from core_infrastructure.update.models import RollbackState, UpdateConfig
from core_infrastructure.update.ports import (
    AvailableRelease,
    Channel,
    UpdateArtifact,
    UpdateResult,
)


class _UpdateResult:
    """Concrete UpdateResult returned by InMemoryUpdateAdapter."""

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
            new_version: The version after the operation, or None.
            error: Error description on failure, or None.
        """
        self._success = success
        self._new_version = new_version
        self._error = error

    def success(self) -> bool:
        """Return whether the operation succeeded."""
        return self._success

    def new_version(self) -> str | None:
        """Return the version after the operation, or None."""
        return self._new_version

    def error(self) -> str | None:
        """Return the error description, or None on success."""
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


class InMemoryUpdateAdapter:
    """Dict-backed UpdateManager test double with rollback support.

    Pre-load releases via add_release() before running tests. Each channel
    stores a single latest release. Version comparison uses
    packaging.version.Version for proper SemVer ordering.

    Usage::

        config = UpdateConfig(
            update_url="https://updates.example.com",
            public_key="test-key",
            current_version="1.0.0",
        )
        adapter = InMemoryUpdateAdapter(config=config)
        adapter.add_release("stable", release)
        result = await adapter.check_for_updates(app_id="myapp", channel="stable")
    """

    def __init__(
        self,
        *,
        config: UpdateConfig,
        override_platform: str | None = None,
    ) -> None:
        """Initialize the in-memory adapter.

        Args:
            config: UpdateConfig with update URL, public key, and version.
            override_platform: Override the detected platform for testing
                (one of ``"windows"``, ``"macos"``, ``"linux"``).
        """
        self._config = config
        self._platform = override_platform or _detect_platform()
        self._releases: dict[str, AvailableRelease] = {}
        self._rollback_states: dict[str, RollbackState] = {}
        self._current_versions: dict[str, str] = {}
        self._current_hashes: dict[str, str] = {}
        # Test hooks
        self._fail_next_apply: bool = False

    # ── Test helpers ──────────────────────────────────────────────────────

    def add_release(self, channel: str, release: AvailableRelease) -> None:
        """Pre-configure a release for a channel (test helper).

        Args:
            channel: The update channel (``"stable"``, ``"beta"``, ``"canary"``).
            release: The AvailableRelease to store for this channel.
        """
        self._releases[channel] = release

    # ── Public API — UpdateManager Protocol ───────────────────────────────

    async def get_current_version(self, *, app_id: str) -> str:
        """Return the currently installed version for an app.

        Args:
            app_id: The application identifier.

        Returns:
            str: The current SemVer version string.
        """
        return self._current_versions.get(app_id, self._config.current_version)

    async def check_for_updates(
        self,
        *,
        app_id: str,
        channel: Channel = "stable",
    ) -> AvailableRelease | None:
        """Query for the latest release in the specified channel.

        Compares the current version against the configured release for
        the channel. Returns None if no update is needed.

        Args:
            app_id: The application identifier.
            channel: The update channel to query.

        Returns:
            AvailableRelease | None: The latest release, or None.
        """
        release = self._releases.get(channel)
        if release is None:
            return None

        current = await self.get_current_version(app_id=app_id)
        if Version(release.version()) <= Version(current):
            return None

        return release

    async def download_update(
        self,
        *,
        app_id: str,
        release: AvailableRelease,
    ) -> UpdateArtifact:
        """Return the artifact matching the current platform.

        No actual download — selects the correct artifact from the release.

        Args:
            app_id: The application identifier.
            release: The AvailableRelease to select from.

        Returns:
            UpdateArtifact: The artifact for the current platform.

        Raises:
            PermanentError: If no artifact matches the current platform.
        """
        _ = app_id  # unused in test double
        for artifact in release.artifacts():
            if artifact.platform() == self._platform:
                return artifact

        raise PermanentError(
            f"No artifact found for platform '{self._platform}' in release "
            f"{release.version()}"
        )

    async def apply_update(
        self,
        *,
        app_id: str,
        artifact: UpdateArtifact,
    ) -> UpdateResult:
        """Apply the update and save rollback state.

        Saves the current version as rollback state, then updates the
        current version. If the apply fails and rollback is enabled,
        automatically restores the previous version.

        Test hooks: set ``_fail_next_apply = True`` before calling to
        simulate an installation failure.

        Args:
            app_id: The application identifier.
            artifact: The UpdateArtifact to apply.

        Returns:
            UpdateResult: Success or failure result.
        """
        previous = await self.get_current_version(app_id=app_id)
        previous_hash = self._current_hashes.get(app_id, artifact.hash())

        # Save rollback state BEFORE attempting apply
        self._rollback_states[app_id] = RollbackState(
            previous_version=previous,
            previous_hash=previous_hash,
            rollback_available=True,
        )

        # Check test hook for simulated failure
        if self._fail_next_apply:
            self._fail_next_apply = False

            # Auto-rollback if enabled
            if self._config.rollback_enabled:
                self._current_versions[app_id] = previous
                return _UpdateResult(
                    success=False,
                    error="Apply failed: simulated error (auto-rollback triggered)",
                )
            else:
                # Still update the version to simulate partial failure
                new_version = self._resolve_new_version(app_id, artifact)
                self._current_versions[app_id] = new_version
                self._current_hashes[app_id] = artifact.hash()
                return _UpdateResult(
                    success=False,
                    error="Apply failed: simulated error",
                )

        # Normal success path
        new_version = self._resolve_new_version(app_id, artifact)
        self._current_versions[app_id] = new_version
        self._current_hashes[app_id] = artifact.hash()
        return _UpdateResult(success=True, new_version=new_version)

    async def rollback(self, *, app_id: str) -> UpdateResult:
        """Restore the previous known-good version.

        Verifies that the current state matches the rollback hash before
        restoring. Raises PermanentError if hash integrity check fails.

        Args:
            app_id: The application identifier.

        Returns:
            UpdateResult: Success result with the restored version.

        Raises:
            PermanentError: If no rollback state exists or hash mismatch.
        """
        state = self._rollback_states.get(app_id)
        if state is None or not state.rollback_available:
            raise PermanentError(
                f"No rollback state available for app '{app_id}'"
            )

        # Verify rollback integrity: current hash must match stored hash
        current_hash = self._current_hashes.get(app_id, "")
        if current_hash != state.previous_hash and self._current_versions.get(app_id) != state.previous_version:
            raise PermanentError(
                "Rollback hash mismatch: the current state does not "
                "match the expected rollback state",
                details={"reason": "hash_mismatch"},
            )

        self._current_versions[app_id] = state.previous_version
        return _UpdateResult(
            success=True, new_version=state.previous_version
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
                    "description": (
                        "Return the currently installed version for an app."
                    ),
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
                        "Download and verify the appropriate artifact for "
                        "the current platform."
                    ),
                },
                "apply_update": {
                    "type": "object",
                    "description": (
                        "Apply the update using platform-specific mechanisms."
                    ),
                },
                "rollback": {
                    "type": "object",
                    "description": (
                        "Rollback to the previous known-good version."
                    ),
                },
            },
        }

    # ── Private helpers ───────────────────────────────────────────────────

    def _resolve_new_version(
        self, app_id: str, artifact: UpdateArtifact
    ) -> str:
        """Resolve the new version after applying an artifact.

        Walks through stored releases to find one containing this
        artifact and returns its version. Falls back to incrementing
        the current version if no match is found.

        Args:
            app_id: The application identifier.
            artifact: The artifact being applied.

        Returns:
            str: The resolved new version string.
        """
        for release in self._releases.values():
            for a in release.artifacts():
                if a.url() == artifact.url():
                    return release.version()

        # Fallback: bump the patch version
        current = self._current_versions.get(
            app_id, self._config.current_version
        )
        v = Version(current)
        return f"{v.major}.{v.minor}.{v.micro + 1}"

    def _tamper_rollback_hash(self, app_id: str, new_hash: str) -> None:
        """Tamper with the rollback state hash (test helper).

        Used to simulate rollback hash integrity failures.

        Args:
            app_id: The application identifier.
            new_hash: The new (invalid) hash to inject.
        """
        state = self._rollback_states.get(app_id)
        if state is not None:
            self._rollback_states[app_id] = RollbackState(
                previous_version=state.previous_version,
                previous_hash=new_hash,
                rollback_available=state.rollback_available,
            )
