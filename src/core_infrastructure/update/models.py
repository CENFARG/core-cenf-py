"""CENF UpdateManager models — UpdateConfig, ReleaseMetadata, ArtifactMeta, RollbackState.

Defines the Pydantic models for UpdateManager data transfer and configuration.
UpdateConfig controls the update endpoint, public key, and rollback settings.
ReleaseMetadata and ArtifactMeta validate remote release metadata.
RollbackState tracks previous version state for recovery.

Security: UpdateConfig.public_key is for Ed25519 signature verification.
    ArtifactMeta.hash must be at least 64 characters (SHA-256 hex).
Observability: Rollback events emit ``cenf.update.rollback_total``.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core_infrastructure.update.ports import Channel


class UpdateConfig(BaseModel):
    """Configuration for UpdateManager adapters.

    Controls the update endpoint URL, Ed25519 public key for signature
    verification, current installed version, and rollback behaviour.

    Attributes:
        update_url: Base URL of the update service endpoint.
        public_key: Ed25519 public key (hex-encoded) for signature verification.
        current_version: Currently installed SemVer version.
        rollback_enabled: Whether automatic rollback on failure is enabled.
    """

    update_url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="Base URL of the update service endpoint.",
    )
    public_key: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Ed25519 public key (hex-encoded) for signature verification.",
    )
    current_version: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Currently installed SemVer version.",
    )
    rollback_enabled: bool = Field(
        default=True,
        description="Whether automatic rollback on failure is enabled.",
    )


class ArtifactMeta(BaseModel):
    """Validated metadata for a single update artifact.

    Describes a downloadable artifact with its URL, target platform,
    CPU architecture, package kind, SHA-256 hash, and optional Ed25519
    signature.

    Attributes:
        url: Download URL for the artifact.
        platform: Target platform (windows, macos, linux).
        arch: Target CPU architecture (x64, arm64).
        kind: Artifact kind (installer, archive, delta).
        hash: SHA-256 hex digest (min 64 chars).
        signature: Ed25519 base64 signature, or None if unsigned.
    """

    model_config = {"extra": "forbid", "frozen": True}

    url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="Download URL for the artifact.",
    )
    platform: Literal["windows", "macos", "linux"] = Field(
        ...,
        description="Target platform.",
    )
    arch: Literal["x64", "arm64"] = Field(
        ...,
        description="Target CPU architecture.",
    )
    kind: Literal["installer", "archive", "delta"] = Field(
        ...,
        description="Artifact kind.",
    )
    hash: str = Field(
        ...,
        min_length=64,
        max_length=128,
        description="SHA-256 hex digest of the artifact.",
    )
    signature: str | None = Field(
        default=None,
        max_length=512,
        description="Ed25519 base64-encoded signature, or None if unsigned.",
    )
    size_bytes: int = Field(
        ...,
        gt=0,
        description="Size of the artifact in bytes.",
    )


class ReleaseMetadata(BaseModel):
    """Validated metadata for an update release.

    Describes a release version with its channel, release notes URL,
    list of artifacts, and minimum supported version for upgrades.

    Attributes:
        version: SemVer version string (e.g., ``"1.1.0"``).
        channel: Update channel (stable, beta, canary).
        release_notes_url: URL to release notes for this version.
        artifacts: List of ArtifactMeta for this release.
        min_version: Minimum version required to upgrade to this release.
    """

    model_config = {"extra": "forbid", "frozen": True}

    version: str = Field(
        ...,
        min_length=5,
        max_length=64,
        pattern=r"^\d+\.\d+\.\d+",
        description="SemVer version string (e.g., 1.1.0).",
    )
    channel: Channel = Field(
        ...,
        description="Update channel (stable, beta, canary).",
    )
    release_notes_url: str | None = Field(
        default=None,
        max_length=2048,
        description="URL to release notes for this version.",
    )
    artifacts: list[ArtifactMeta] = Field(
        default_factory=list,
        description="List of artifacts for this release.",
    )
    min_version: str | None = Field(
        default=None,
        pattern=r"^\d+\.\d+\.\d+",
        description="Minimum version required to upgrade to this release.",
    )
    published_at: float | None = Field(
        default=None,
        gt=0,
        description="Unix timestamp when this release was published.",
    )


class RollbackState(BaseModel):
    """State for rolling back to a previous known-good version.

    Stores the previously installed version, its verified SHA-256 hash,
    and whether rollback is available. Used by apply_update() to save
    state before installation and by rollback() to restore.

    Attributes:
        previous_version: The previously installed SemVer version.
        previous_hash: SHA-256 hex of the previous version's artifact.
        rollback_available: Whether rollback is currently possible.
    """

    model_config = {"extra": "forbid", "frozen": True}

    previous_version: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Previously installed SemVer version.",
    )
    previous_hash: str = Field(
        ...,
        min_length=64,
        max_length=128,
        description="SHA-256 hex of the previous version's artifact.",
    )
    rollback_available: bool = Field(
        default=True,
        description="Whether rollback is currently possible.",
    )
