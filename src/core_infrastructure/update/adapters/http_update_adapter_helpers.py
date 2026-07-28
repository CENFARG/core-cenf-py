"""HttpUpdateAdapter helpers — platform detection, artifact selection, verification.

Extracted from ``http_update_adapter.py`` to comply with the 250-line CENF rule.
Contains platform detection, Ed25519 signature verification, SHA-256 hash
verification, artifact wrapper classes, and release wrapper classes.

What: Extracted helpers for HttpUpdateAdapter to reduce main module size.
Why: 250-line CENF rule compliance — pure refactoring, no behavior change.
Where: src/core_infrastructure/update/adapters/http_update_adapter_helpers.py

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from core_infrastructure.common.errors import AuthError
from core_infrastructure.update.models import ArtifactMeta, ReleaseMetadata
from core_infrastructure.update.ports import (
    Channel,
    UpdateArtifact,
)


class ArtifactWrapper:
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


class ReleaseWrapper:
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
            ArtifactWrapper(a) for a in meta.artifacts
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


class UpdateResultImpl:
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


def _camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case (e.g. ``"releaseNotesUrl"`` → ``"release_notes_url"``)."""
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def normalize_yaml_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize camelCase YAML keys to snake_case recursively (handles ``artifacts`` list).

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


def detect_platform() -> str:
    """Detect the current platform for artifact selection.

    Returns:
        str: One of ``"windows"``, ``"macos"``, ``"linux"``.
    """
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":  # type: ignore[unreachable]
        return "macos"
    return "linux"


def verify_hash(data: bytes, expected_hash: str) -> None:
    """Verify SHA-256 hash of downloaded data.

    Args:
        data: The raw downloaded artifact bytes.
        expected_hash: The expected SHA-256 hex digest.

    Raises:
        AuthError: If the hash does not match.
    """
    computed_hash = hashlib.sha256(data).hexdigest()
    if computed_hash != expected_hash:
        raise AuthError(
            "Hash mismatch: downloaded artifact does not match "
            "expected SHA-256 digest",
            details={"reason": "hash_mismatch"},
        )


def verify_signature(
    data: bytes, signature_hex: str, public_key_hex: str
) -> None:
    """Verify an Ed25519 signature against the configured public key.

    Args:
        data: The raw artifact data that was signed.
        signature_hex: The hex-encoded Ed25519 signature.
        public_key_hex: The hex-encoded Ed25519 public key.

    Raises:
        AuthError: If the signature does not verify.
    """
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(public_key_hex)
        )
        signature = bytes.fromhex(signature_hex)
        public_key.verify(signature, data)
    except (ValueError, InvalidSignature) as exc:
        raise AuthError(
            "Signature verification failed: the artifact signature "
            "does not match the configured public key",
            details={"reason": "signature_mismatch"},
        ) from exc


def _resolve_app_paths(
    data_dir: Path, app_id: str
) -> tuple[Path, Path, Path]:
    """Resolve install path, backup path, and app directory for an app.

    Args:
        data_dir: Root data directory for update state.
        app_id: The application identifier.

    Returns:
        tuple[Path, Path, Path]: ``(app_dir, install_path, backup_path)``.
    """
    app_dir = data_dir / app_id
    return app_dir, app_dir / "current.bin", app_dir / "backup.bin"


def _save_rollback_state(
    rollback_states: dict[str, dict[str, str | bool]],
    app_id: str,
    previous_version: str,
    previous_hash: str,
) -> None:
    """Persist rollback state before applying an update.

    Args:
        rollback_states: The adapter's rollback state dictionary.
        app_id: The application identifier.
        previous_version: The currently installed version.
        previous_hash: SHA-256 hash of the current artifact.
    """
    rollback_states[app_id] = {
        "previous_version": previous_version,
        "previous_hash": previous_hash,
        "rollback_available": True,
    }


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
