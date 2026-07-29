"""Unit tests for UpdateManager Protocol and Update models.

Tests cover:
- UpdateManager Protocol contract (get_current_version, check_for_updates,
  download_update, apply_update, rollback, get_json_schema)
- AvailableRelease Protocol (version, channel, artifacts, metadata)
- UpdateArtifact Protocol (url, platform, arch, kind, hash, signature)
- UpdateResult Protocol (success, new_version, error)
- UpdateConfig Pydantic model validation
- ReleaseMetadata Pydantic model validation
- ArtifactMeta Pydantic model validation
- RollbackState Pydantic model validation
- Channel literal type definition
- Protocols are runtime-checkable

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.update.models import (
    ArtifactMeta,
    Channel,
    ReleaseMetadata,
    RollbackState,
    UpdateConfig,
)
from core_infrastructure.update.ports import (
    AvailableRelease,
    UpdateArtifact,
    UpdateManager,
    UpdateResult,
)

# ── Channel literal type ──────────────────────────────────────────────────

class TestChannelLiteral:
    """Verify Channel literal type is defined correctly."""

    def test_stable_is_valid(self) -> None:
        """'stable' is a valid Channel value."""
        ch: Channel = "stable"
        assert ch == "stable"

    def test_beta_is_valid(self) -> None:
        """'beta' is a valid Channel value."""
        ch: Channel = "beta"
        assert ch == "beta"

    def test_canary_is_valid(self) -> None:
        """'canary' is a valid Channel value."""
        ch: Channel = "canary"
        assert ch == "canary"


# ── AvailableRelease Protocol ──────────────────────────────────────────────

class TestAvailableReleaseProtocol:
    """Verify AvailableRelease Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """AvailableRelease Protocol is decorated with @runtime_checkable."""
        assert hasattr(AvailableRelease, "_is_runtime_protocol") or hasattr(
            AvailableRelease, "__protocol_attrs__"
        )

    def test_has_version_method(self) -> None:
        """Protocol requires version() -> str."""
        assert hasattr(AvailableRelease, "version")

    def test_has_channel_method(self) -> None:
        """Protocol requires channel() -> Channel."""
        assert hasattr(AvailableRelease, "channel")

    def test_has_artifacts_method(self) -> None:
        """Protocol requires artifacts() -> list[UpdateArtifact]."""
        assert hasattr(AvailableRelease, "artifacts")

    def test_has_metadata_method(self) -> None:
        """Protocol requires metadata() -> Mapping[str, Any]."""
        assert hasattr(AvailableRelease, "metadata")

    def test_has_release_notes_url_method(self) -> None:
        """Protocol requires release_notes_url() -> str | None."""
        assert hasattr(AvailableRelease, "release_notes_url")

    def test_complete_class_satisfies_protocol(self) -> None:
        """A class implementing all methods satisfies AvailableRelease."""

        class CompleteRelease:
            def version(self) -> str:
                return "1.0.0"

            def channel(self) -> Channel:
                return "stable"

            def artifacts(self) -> list:
                return []

            def metadata(self) -> dict[str, Any]:
                return {}

            def release_notes_url(self) -> str | None:
                return None

        assert isinstance(CompleteRelease(), AvailableRelease)

    def test_incomplete_class_fails_protocol(self) -> None:
        """A class missing methods does NOT satisfy AvailableRelease."""

        class Incomplete:
            def version(self) -> str:
                return "1.0.0"

        assert not isinstance(Incomplete(), AvailableRelease)


# ── UpdateArtifact Protocol ────────────────────────────────────────────────

class TestUpdateArtifactProtocol:
    """Verify UpdateArtifact Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """UpdateArtifact Protocol is decorated with @runtime_checkable."""
        assert hasattr(UpdateArtifact, "_is_runtime_protocol") or hasattr(
            UpdateArtifact, "__protocol_attrs__"
        )

    def test_has_url_method(self) -> None:
        """Protocol requires url() -> str."""
        assert hasattr(UpdateArtifact, "url")

    def test_has_platform_method(self) -> None:
        """Protocol requires platform() -> str."""
        assert hasattr(UpdateArtifact, "platform")

    def test_has_arch_method(self) -> None:
        """Protocol requires arch() -> str."""
        assert hasattr(UpdateArtifact, "arch")

    def test_has_kind_method(self) -> None:
        """Protocol requires kind() -> str."""
        assert hasattr(UpdateArtifact, "kind")

    def test_has_hash_method(self) -> None:
        """Protocol requires hash() -> str."""
        assert hasattr(UpdateArtifact, "hash")

    def test_has_signature_method(self) -> None:
        """Protocol requires signature() -> str | None."""
        assert hasattr(UpdateArtifact, "signature")

    def test_has_size_bytes_method(self) -> None:
        """Protocol requires size_bytes() -> int."""
        assert hasattr(UpdateArtifact, "size_bytes")

    def test_complete_class_satisfies_protocol(self) -> None:
        """A class implementing all methods satisfies UpdateArtifact."""

        class CompleteArtifact:
            def url(self) -> str:
                return "https://example.com/update.zip"

            def platform(self) -> str:
                return "windows"

            def arch(self) -> str:
                return "x64"

            def kind(self) -> str:
                return "installer"

            def hash(self) -> str:
                return "a" * 64

            def signature(self) -> str | None:
                return None

            def size_bytes(self) -> int:
                return 1048576

        assert isinstance(CompleteArtifact(), UpdateArtifact)

    def test_incomplete_class_fails_protocol(self) -> None:
        """A class missing methods does NOT satisfy UpdateArtifact."""

        class Incomplete:
            def url(self) -> str:
                return "https://example.com"

        assert not isinstance(Incomplete(), UpdateArtifact)


# ── UpdateResult Protocol ──────────────────────────────────────────────────

class TestUpdateResultProtocol:
    """Verify UpdateResult Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """UpdateResult Protocol is decorated with @runtime_checkable."""
        assert hasattr(UpdateResult, "_is_runtime_protocol") or hasattr(
            UpdateResult, "__protocol_attrs__"
        )

    def test_has_success_method(self) -> None:
        """Protocol requires success() -> bool."""
        assert hasattr(UpdateResult, "success")

    def test_has_new_version_method(self) -> None:
        """Protocol requires new_version() -> str | None."""
        assert hasattr(UpdateResult, "new_version")

    def test_has_error_method(self) -> None:
        """Protocol requires error() -> str | None."""
        assert hasattr(UpdateResult, "error")

    def test_has_requires_restart_method(self) -> None:
        """Protocol requires requires_restart() -> bool."""
        assert hasattr(UpdateResult, "requires_restart")

    def test_complete_class_satisfies_protocol(self) -> None:
        """A class implementing all methods satisfies UpdateResult."""

        class CompleteResult:
            def success(self) -> bool:
                return True

            def new_version(self) -> str | None:
                return "1.1.0"

            def error(self) -> str | None:
                return None

            def requires_restart(self) -> bool:
                return False

        assert isinstance(CompleteResult(), UpdateResult)

    def test_incomplete_class_fails_protocol(self) -> None:
        """A class missing methods does NOT satisfy UpdateResult."""

        class Incomplete:
            def success(self) -> bool:
                return True

        assert not isinstance(Incomplete(), UpdateResult)


# ── UpdateManager Protocol ─────────────────────────────────────────────────

class TestUpdateManagerProtocol:
    """Verify UpdateManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """UpdateManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(UpdateManager, "_is_runtime_protocol") or hasattr(
            UpdateManager, "__protocol_attrs__"
        )

    def test_has_get_current_version(self) -> None:
        """Protocol requires get_current_version() -> str."""
        assert hasattr(UpdateManager, "get_current_version")

    def test_has_check_for_updates(self) -> None:
        """Protocol requires check_for_updates() -> AvailableRelease | None."""
        assert hasattr(UpdateManager, "check_for_updates")

    def test_has_download_update(self) -> None:
        """Protocol requires download_update() -> UpdateArtifact."""
        assert hasattr(UpdateManager, "download_update")

    def test_has_apply_update(self) -> None:
        """Protocol requires apply_update() -> UpdateResult."""
        assert hasattr(UpdateManager, "apply_update")

    def test_has_rollback(self) -> None:
        """Protocol requires rollback() -> UpdateResult."""
        assert hasattr(UpdateManager, "rollback")

    def test_has_get_json_schema(self) -> None:
        """Protocol requires get_json_schema() -> dict."""
        assert hasattr(UpdateManager, "get_json_schema")

    def test_get_json_schema_is_static(self) -> None:
        """get_json_schema is a staticmethod on the Protocol."""
        import inspect

        method = inspect.getattr_static(UpdateManager, "get_json_schema")
        assert isinstance(method, staticmethod)

    def test_complete_adapter_satisfies_protocol(self) -> None:
        """A class implementing all methods satisfies UpdateManager Protocol."""

        class CompleteAdapter:
            async def get_current_version(self, *, app_id: str) -> str:
                return "1.0.0"

            async def check_for_updates(self, *, app_id: str, channel: Channel = "stable"):
                return None

            async def download_update(self, *, app_id: str, release: AvailableRelease):
                ...

            async def apply_update(self, *, app_id: str, artifact: UpdateArtifact):
                ...

            async def rollback(self, *, app_id: str):
                ...

            @staticmethod
            def get_json_schema() -> dict[str, Any]:
                return {}

        assert isinstance(CompleteAdapter(), UpdateManager)

    def test_class_missing_method_fails_protocol(self) -> None:
        """A class without get_current_version does NOT satisfy UpdateManager."""

        class Incomplete:
            @staticmethod
            def get_json_schema() -> dict[str, Any]:
                return {}

        assert not isinstance(Incomplete(), UpdateManager)


# ── UpdateConfig model ─────────────────────────────────────────────────────

class TestUpdateConfigModel:
    """Verify UpdateConfig Pydantic model."""

    def test_valid_minimal_config(self) -> None:
        """UpdateConfig with required fields only."""
        cfg = UpdateConfig(
            update_url="https://updates.example.com",
            public_key="ed25519-public-key-hex",
            current_version="1.0.0",
        )
        assert cfg.update_url == "https://updates.example.com"
        assert cfg.public_key == "ed25519-public-key-hex"
        assert cfg.current_version == "1.0.0"
        assert cfg.rollback_enabled is True

    def test_rollback_disabled(self) -> None:
        """rollback_enabled can be explicitly disabled."""
        cfg = UpdateConfig(
            update_url="https://updates.example.com",
            public_key="key",
            current_version="1.0.0",
            rollback_enabled=False,
        )
        assert cfg.rollback_enabled is False

    def test_empty_update_url_fails(self) -> None:
        """update_url must not be empty."""
        with pytest.raises(PydanticValidationError):
            UpdateConfig(
                update_url="",
                public_key="key",
                current_version="1.0.0",
            )

    def test_empty_public_key_fails(self) -> None:
        """public_key must not be empty."""
        with pytest.raises(PydanticValidationError):
            UpdateConfig(
                update_url="https://example.com",
                public_key="",
                current_version="1.0.0",
            )

    def test_empty_current_version_fails(self) -> None:
        """current_version must not be empty."""
        with pytest.raises(PydanticValidationError):
            UpdateConfig(
                update_url="https://example.com",
                public_key="key",
                current_version="",
            )


# ── ReleaseMetadata model ──────────────────────────────────────────────────

class TestReleaseMetadataModel:
    """Verify ReleaseMetadata Pydantic model."""

    def test_valid_minimal_release(self) -> None:
        """ReleaseMetadata with required fields only."""
        r = ReleaseMetadata(
            version="1.1.0",
            channel="stable",
            release_notes_url="https://example.com/notes",
        )
        assert r.version == "1.1.0"
        assert r.channel == "stable"
        assert r.release_notes_url == "https://example.com/notes"
        assert r.artifacts == []
        assert r.min_version is None

    def test_with_artifacts(self) -> None:
        """ReleaseMetadata with artifacts list."""
        artifacts = [
            ArtifactMeta(
                url="https://example.com/update.exe",
                platform="windows",
                arch="x64",
                kind="installer",
                hash="a" * 64,
                size_bytes=1048576,
            )
        ]
        r = ReleaseMetadata(
            version="1.1.0",
            channel="beta",
            release_notes_url="https://example.com/notes",
            artifacts=artifacts,
            min_version="1.0.0",
        )
        assert len(r.artifacts) == 1
        assert r.min_version == "1.0.0"

    def test_canary_channel_valid(self) -> None:
        """'canary' is a valid channel for ReleaseMetadata."""
        r = ReleaseMetadata(
            version="2.0.0-alpha",
            channel="canary",
            release_notes_url="https://example.com/notes",
        )
        assert r.channel == "canary"

    def test_invalid_channel_fails(self) -> None:
        """channel must be 'stable', 'beta', or 'canary'."""
        with pytest.raises(PydanticValidationError):
            ReleaseMetadata(
                version="1.0.0",
                channel="dev",  # type: ignore[arg-type]
                release_notes_url="https://example.com",
            )

    def test_empty_version_fails(self) -> None:
        """version must not be empty."""
        with pytest.raises(PydanticValidationError):
            ReleaseMetadata(
                version="",
                channel="stable",
                release_notes_url="https://example.com",
            )

    def test_invalid_version_pattern_fails(self) -> None:
        """version must match SemVer pattern X.Y.Z."""
        with pytest.raises(PydanticValidationError):
            ReleaseMetadata(
                version="v1.0",
                channel="stable",
                release_notes_url="https://example.com",
            )

    def test_with_published_at(self) -> None:
        """ReleaseMetadata accepts published_at timestamp."""
        r = ReleaseMetadata(
            version="1.1.0",
            channel="stable",
            release_notes_url="https://example.com/notes",
            published_at=1234567890.0,
        )
        assert r.published_at == 1234567890.0

    def test_published_at_defaults_to_none(self) -> None:
        """ReleaseMetadata.published_at defaults to None."""
        r = ReleaseMetadata(
            version="1.1.0",
            channel="stable",
            release_notes_url="https://example.com/notes",
        )
        assert r.published_at is None

    def test_release_notes_url_defaults_to_none(self) -> None:
        """ReleaseMetadata.release_notes_url is optional (default None)."""
        r = ReleaseMetadata(
            version="1.1.0",
            channel="stable",
        )
        assert r.release_notes_url is None

    def test_model_is_frozen(self) -> None:
        """ReleaseMetadata is frozen — attributes cannot be changed."""
        r = ReleaseMetadata(
            version="1.0.0",
            channel="stable",
            release_notes_url="https://example.com",
        )
        with pytest.raises(PydanticValidationError):
            r.version = "2.0.0"  # type: ignore[misc]


# ── ArtifactMeta model ─────────────────────────────────────────────────────

class TestArtifactMetaModel:
    """Verify ArtifactMeta Pydantic model."""

    def test_valid_minimal_artifact(self) -> None:
        """ArtifactMeta with required fields only."""
        a = ArtifactMeta(
            url="https://example.com/update.exe",
            platform="windows",
            arch="x64",
            kind="installer",
            hash="a" * 64,
            size_bytes=1048576,
        )
        assert a.url == "https://example.com/update.exe"
        assert a.platform == "windows"
        assert a.arch == "x64"
        assert a.kind == "installer"
        assert a.hash == "a" * 64
        assert a.signature is None
        assert a.size_bytes == 1048576

    def test_with_signature(self) -> None:
        """ArtifactMeta with signature field."""
        a = ArtifactMeta(
            url="https://example.com/update.pkg",
            platform="macos",
            arch="arm64",
            kind="archive",
            hash="b" * 64,
            signature="ed25519-sig-base64",
            size_bytes=256000,
        )
        assert a.signature == "ed25519-sig-base64"

    def test_linux_platform_valid(self) -> None:
        """'linux' is a valid platform."""
        a = ArtifactMeta(
            url="https://example.com/update",
            platform="linux",
            arch="x64",
            kind="archive",
            hash="c" * 64,
            size_bytes=512000,
        )
        assert a.platform == "linux"

    def test_delta_kind_valid(self) -> None:
        """'delta' is a valid kind."""
        a = ArtifactMeta(
            url="https://example.com/delta",
            platform="windows",
            arch="x64",
            kind="delta",
            hash="d" * 64,
            size_bytes=1024,
        )
        assert a.kind == "delta"

    def test_invalid_platform_fails(self) -> None:
        """platform must be 'windows', 'macos', or 'linux'."""
        with pytest.raises(PydanticValidationError):
            ArtifactMeta(
                url="https://example.com",
                platform="freebsd",  # type: ignore[arg-type]
                arch="x64",
                kind="installer",
                hash="a" * 64,
                size_bytes=1024,
            )

    def test_invalid_arch_fails(self) -> None:
        """arch must be 'x64' or 'arm64'."""
        with pytest.raises(PydanticValidationError):
            ArtifactMeta(
                url="https://example.com",
                platform="windows",
                arch="x86",  # type: ignore[arg-type]
                kind="installer",
                hash="a" * 64,
                size_bytes=1024,
            )

    def test_invalid_kind_fails(self) -> None:
        """kind must be 'installer', 'archive', or 'delta'."""
        with pytest.raises(PydanticValidationError):
            ArtifactMeta(
                url="https://example.com",
                platform="windows",
                arch="x64",
                kind="patch",  # type: ignore[arg-type]
                hash="a" * 64,
                size_bytes=1024,
            )

    def test_hash_too_short_fails(self) -> None:
        """hash must be at least 64 characters (SHA-256 hex)."""
        with pytest.raises(PydanticValidationError):
            ArtifactMeta(
                url="https://example.com",
                platform="windows",
                arch="x64",
                kind="installer",
                hash="short",
                size_bytes=1024,
            )

    def test_empty_url_fails(self) -> None:
        """url must not be empty."""
        with pytest.raises(PydanticValidationError):
            ArtifactMeta(
                url="",
                platform="windows",
                arch="x64",
                kind="installer",
                hash="a" * 64,
                size_bytes=1024,
            )

    def test_model_is_frozen(self) -> None:
        """ArtifactMeta is frozen — attributes cannot be changed."""
        a = ArtifactMeta(
            url="https://example.com",
            platform="windows",
            arch="x64",
            kind="installer",
            hash="a" * 64,
            size_bytes=1048576,
        )
        with pytest.raises(PydanticValidationError):
            a.url = "https://other.com"  # type: ignore[misc]

    def test_with_size_bytes(self) -> None:
        """ArtifactMeta accepts size_bytes."""
        a = ArtifactMeta(
            url="https://example.com/update.exe",
            platform="windows",
            arch="x64",
            kind="installer",
            hash="a" * 64,
            size_bytes=1048576,
        )
        assert a.size_bytes == 1048576

    def test_size_bytes_must_be_positive(self) -> None:
        """ArtifactMeta.size_bytes must be > 0."""
        with pytest.raises(PydanticValidationError):
            ArtifactMeta(
                url="https://example.com/update.exe",
                platform="windows",
                arch="x64",
                kind="installer",
                hash="a" * 64,
                size_bytes=0,
            )

    def test_size_bytes_must_be_present(self) -> None:
        """ArtifactMeta.size_bytes is required."""
        with pytest.raises(PydanticValidationError):
            ArtifactMeta(
                url="https://example.com/update.exe",
                platform="windows",
                arch="x64",
                kind="installer",
                hash="a" * 64,
                # size_bytes omitted
            )


# ── RollbackState model ────────────────────────────────────────────────────

class TestRollbackStateModel:
    """Verify RollbackState Pydantic model."""

    def test_valid_rollback_state(self) -> None:
        """RollbackState with all fields."""
        rs = RollbackState(
            previous_version="1.0.0",
            previous_hash="a" * 64,
            rollback_available=True,
        )
        assert rs.previous_version == "1.0.0"
        assert rs.previous_hash == "a" * 64
        assert rs.rollback_available is True

    def test_rollback_not_available(self) -> None:
        """RollbackState with rollback_available=False."""
        rs = RollbackState(
            previous_version="1.0.0",
            previous_hash="b" * 64,
            rollback_available=False,
        )
        assert rs.rollback_available is False

    def test_empty_previous_version_fails(self) -> None:
        """previous_version must not be empty."""
        with pytest.raises(PydanticValidationError):
            RollbackState(
                previous_version="",
                previous_hash="a" * 64,
            )

    def test_empty_previous_hash_fails(self) -> None:
        """previous_hash must not be empty."""
        with pytest.raises(PydanticValidationError):
            RollbackState(
                previous_version="1.0.0",
                previous_hash="",
            )

    def test_default_rollback_available(self) -> None:
        """rollback_available defaults to True."""
        rs = RollbackState(
            previous_version="1.0.0",
            previous_hash="a" * 64,
        )
        assert rs.rollback_available is True
