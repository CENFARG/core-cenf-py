"""UpdateManager Protocol — the contract every update adapter must satisfy.

Defines the desktop auto-update interface consumed by all infrastructure
managers that need to discover, verify, and apply application updates.
Supports TUF-inspired signature verification, SemVer version comparison,
and automatic rollback to previous known-good versions.

Security: download_update() MUST verify SHA-256 hash AND digital signature
    before returning an artifact. apply_update() MUST support rollback.
Observability: Update events emit RED metrics via ObservabilityManager.
@ai-directive: Use UpdateManager to discover and apply desktop app updates.
    Always verify signatures and hashes before installing. Never install
    unverified artifacts.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Protocol, runtime_checkable

Channel = Literal["stable", "beta", "canary"]
"""Valid update channels: stable, beta, and canary."""


@runtime_checkable
class UpdateArtifact(Protocol):
    """A downloadable update package for a specific platform.

    Describes a single update artifact with its download URL, target
    platform, architecture, package kind, SHA-256 hash, and optional
    digital signature.

    Security:
        hash() MUST return a 64-character SHA-256 hex digest.
        signature() returns the Ed25519 signature or None if unsigned.
    """

    def url(self) -> str:
        """Return the download URL for this artifact.

        Returns:
            str: The full URL to download the artifact.
        """
        ...

    def platform(self) -> str:
        """Return the target platform.

        Returns:
            str: One of ``"windows"``, ``"macos"``, ``"linux"``.
        """
        ...

    def arch(self) -> str:
        """Return the target CPU architecture.

        Returns:
            str: One of ``"x64"``, ``"arm64"``.
        """
        ...

    def kind(self) -> str:
        """Return the artifact kind.

        Returns:
            str: One of ``"installer"``, ``"archive"``, ``"delta"``.
        """
        ...

    def hash(self) -> str:
        """Return the SHA-256 hex digest of the artifact.

        Returns:
            str: A 64-character lowercase hex string.
        """
        ...

    def signature(self) -> str | None:
        """Return the Ed25519 signature, or None if unsigned.

        Returns:
            str | None: The base64-encoded Ed25519 signature, or None.
        """
        ...


@runtime_checkable
class AvailableRelease(Protocol):
    """Metadata describing an available update release.

    Represents a single release with its SemVer version, update channel,
    list of platform-specific artifacts, and additional metadata.

    Attributes:
        version: SemVer version string (e.g., ``"1.1.0"``).
        channel: Update channel (stable, beta, canary).
        artifacts: List of platform-specific UpdateArtifacts.
        metadata: Additional release metadata as a mapping.
    """

    def version(self) -> str:
        """Return the SemVer version of this release.

        Returns:
            str: The version string (e.g., ``"1.1.0"``).
        """
        ...

    def channel(self) -> Channel:
        """Return the update channel for this release.

        Returns:
            Channel: One of ``"stable"``, ``"beta"``, ``"canary"``.
        """
        ...

    def artifacts(self) -> list[UpdateArtifact]:
        """Return the list of artifacts for this release.

        Returns:
            list[UpdateArtifact]: Platform-specific artifacts.
        """
        ...

    def metadata(self) -> Mapping[str, Any]:
        """Return additional release metadata.

        Returns:
            Mapping[str, Any]: Additional metadata key-value pairs.
        """
        ...


@runtime_checkable
class UpdateResult(Protocol):
    """Result of an update application attempt.

    Represents the outcome of applying or rolling back an update,
    including success status, new version identifier, and error
    information for failures.

    Security:
        error() MUST NOT contain sensitive information (paths, keys).
    """

    def success(self) -> bool:
        """Return whether the update was applied successfully.

        Returns:
            bool: True if the update succeeded.
        """
        ...

    def new_version(self) -> str | None:
        """Return the version after the update, or None on failure.

        Returns:
            str | None: The new version string, or None.
        """
        ...

    def error(self) -> str | None:
        """Return an error description if the update failed.

        Returns:
            str | None: Human-readable error, or None on success.
        """
        ...


@runtime_checkable
class UpdateManager(Protocol):
    """Desktop auto-update contract with signature verification and rollback.

    All infrastructure managers that need to discover and apply desktop
    application updates consume this interface. Concrete adapters provide
    HTTP-based update checks (HttpUpdateAdapter) or dict-backed simulation
    (InMemoryUpdateAdapter for testing).

    Rules:
        - check_for_updates() queries remote endpoint and compares versions.
        - download_update() verifies SHA-256 hash AND Ed25519 signature.
        - apply_update() installs with automatic rollback on failure.
        - rollback() restores the previous known-good version.
        - get_json_schema() describes this contract for agent discovery.

    Security: NEVER download or install an artifact without full signature
        and hash verification. Always delete partial downloads on failure.

    @ai-directive: Always verify signatures and hashes before installing.
        Never install unverified artifacts. Use rollback() to recover from
        failed updates.
    """

    async def get_current_version(self, *, app_id: str) -> str:
        """Return the currently installed version for an app (SemVer).

        Args:
            app_id: The application identifier (e.g., ``"cenf-desktop"``).

        Returns:
            str: The current SemVer version string (e.g., ``"1.0.0"``).
        """
        ...

    async def check_for_updates(
        self,
        *,
        app_id: str,
        channel: Channel = "stable",
    ) -> AvailableRelease | None:
        """Query the remote update service for the latest compatible release.

        Compares the current version against the latest release in the
        specified channel. Returns None if no update is needed.

        Args:
            app_id: The application identifier.
            channel: The update channel to query (default: ``"stable"``).

        Returns:
            AvailableRelease | None: The latest available release, or
                None if current version is already up-to-date.

        Raises:
            TransientError: If the remote endpoint is unreachable.
        """
        ...

    async def download_update(
        self,
        *,
        app_id: str,
        release: AvailableRelease,
    ) -> UpdateArtifact:
        """Download and verify the appropriate artifact for the current platform.

        Selects the correct artifact for the current platform and architecture,
        downloads it, and verifies both the SHA-256 hash and Ed25519 digital
        signature before returning.

        Args:
            app_id: The application identifier.
            release: The AvailableRelease to download from.

        Returns:
            UpdateArtifact: The verified artifact ready for installation.

        Raises:
            AuthError: If the SHA-256 hash or Ed25519 signature does not match.
            PermanentError: If no artifact matches the current platform.
        """
        ...

    async def apply_update(
        self,
        *,
        app_id: str,
        artifact: UpdateArtifact,
    ) -> UpdateResult:
        """Apply the update using platform-specific mechanisms.

        Saves the current version as rollback state before installing.
        If the installation fails and rollback is enabled, automatically
        restores the previous version.

        Args:
            app_id: The application identifier.
            artifact: The verified UpdateArtifact to install.

        Returns:
            UpdateResult: The result of the update application, including
                success status and new version.
        """
        ...

    async def rollback(self, *, app_id: str) -> UpdateResult:
        """Rollback to the previous known-good version.

        Restores the previously installed version from rollback state.
        Verifies that the restored version matches the stored hash.

        Args:
            app_id: The application identifier.

        Returns:
            UpdateResult: The result of the rollback operation.

        Raises:
            PermanentError: If no rollback state exists for the app.
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery.

        Returns a JSON Schema that tools/agents can use to understand
        how to call the UpdateManager.

        Returns:
            dict[str, Any]: JSON Schema describing the UpdateManager
                interface (methods, parameters, return types).
        """
        ...
