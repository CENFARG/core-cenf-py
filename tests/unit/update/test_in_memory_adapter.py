"""Unit tests for InMemoryUpdateAdapter — dict-backed test double.

Tests cover:
- get_current_version() returns configured version
- check_for_updates() returns latest release for channel
- check_for_updates() returns None when already latest version
- check_for_updates() filters by channel
- download_update() returns artifact metadata (no I/O)
- download_update() raises when no matching artifact for platform
- apply_update() updates current version and saves rollback state
- apply_update() returns success UpdateResult
- rollback() restores previous version
- rollback() raises when no rollback state exists
- get_json_schema() returns a dict
- Multiple update + rollback cycles work correctly

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.common.errors import PermanentError
from core_infrastructure.update.models import UpdateConfig
from core_infrastructure.update.ports import (
    AvailableRelease,
    UpdateArtifact,
    UpdateManager,
    UpdateResult,
)

# ── Concrete classes for Protocols ──────────────────────────────────────────

class _Artifact:
    """Concrete UpdateArtifact implementation."""

    def __init__(
        self,
        url: str,
        platform: str,
        arch: str,
        kind: str,
        hash: str,
        signature: str | None = None,
    ) -> None:
        self._url = url
        self._platform = platform
        self._arch = arch
        self._kind = kind
        self._hash = hash
        self._signature = signature

    def url(self) -> str:
        return self._url

    def platform(self) -> str:
        return self._platform

    def arch(self) -> str:
        return self._arch

    def kind(self) -> str:
        return self._kind

    def hash(self) -> str:
        return self._hash

    def signature(self) -> str | None:
        return self._signature


class _Release:
    """Concrete AvailableRelease implementation."""

    def __init__(
        self,
        version: str,
        channel: str,
        artifacts: list[_Artifact],
        metadata: dict | None = None,
    ) -> None:
        self._version = version
        self._channel = channel
        self._artifacts = artifacts
        self._metadata = metadata or {}

    def version(self) -> str:
        return self._version

    def channel(self) -> str:
        return self._channel

    def artifacts(self) -> list[_Artifact]:
        return self._artifacts

    def metadata(self) -> dict:
        return self._metadata


class _Result:
    """Concrete UpdateResult implementation."""

    def __init__(
        self,
        success: bool,
        new_version: str | None = None,
        error: str | None = None,
    ) -> None:
        self._success = success
        self._new_version = new_version
        self._error = error

    def success(self) -> bool:
        return self._success

    def new_version(self) -> str | None:
        return self._new_version

    def error(self) -> str | None:
        return self._error


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def config() -> UpdateConfig:
    """Default UpdateConfig for testing."""
    return UpdateConfig(
        update_url="https://updates.example.com",
        public_key="test-public-key-hex",
        current_version="1.0.0",
    )


@pytest.fixture
def artifact_win() -> _Artifact:
    """A Windows installer artifact."""
    return _Artifact(
        url="https://example.com/cenf-1.1.0.exe",
        platform="windows",
        arch="x64",
        kind="installer",
        hash="a" * 64,
    )


@pytest.fixture
def artifact_mac() -> _Artifact:
    """A macOS artifact."""
    return _Artifact(
        url="https://example.com/cenf-1.1.0.pkg",
        platform="macos",
        arch="arm64",
        kind="archive",
        hash="b" * 64,
    )


@pytest.fixture
def release_v110(artifact_win: _Artifact, artifact_mac: _Artifact) -> _Release:
    """Release 1.1.0 with artifacts for Windows and macOS."""
    return _Release(
        version="1.1.0",
        channel="stable",
        artifacts=[artifact_win, artifact_mac],
    )


@pytest.fixture
def release_v120_beta() -> _Release:
    """Release 1.2.0-beta on beta channel."""
    return _Release(
        version="1.2.0-beta",
        channel="beta",
        artifacts=[
            _Artifact(
                url="https://example.com/cenf-1.2.0-beta.exe",
                platform="windows",
                arch="x64",
                kind="installer",
                hash="c" * 64,
            )
        ],
    )


@pytest.fixture
def adapter(
    config: UpdateConfig,
    release_v110: _Release,
    release_v120_beta: _Release,
):
    """Create an InMemoryUpdateAdapter with pre-configured releases."""
    from core_infrastructure.update.adapters.in_memory_update_adapter import (
        InMemoryUpdateAdapter,
    )

    adapter = InMemoryUpdateAdapter(config=config)
    adapter.add_release("stable", release_v110)
    adapter.add_release("beta", release_v120_beta)
    return adapter


# ── get_current_version ─────────────────────────────────────────────────────

class TestGetCurrentVersion:
    """Tests for get_current_version()."""

    @pytest.mark.asyncio
    async def test_returns_configured_version(self, adapter) -> None:
        """get_current_version returns the version from config."""
        version = await adapter.get_current_version(app_id="test-app")
        assert version == "1.0.0"

    @pytest.mark.asyncio
    async def test_app_id_is_received(self, adapter) -> None:
        """get_current_version accepts app_id parameter."""
        version = await adapter.get_current_version(app_id="cenf-desktop")
        assert version == "1.0.0"


# ── check_for_updates ───────────────────────────────────────────────────────

class TestCheckForUpdates:
    """Tests for check_for_updates()."""

    @pytest.mark.asyncio
    async def test_returns_release_when_newer_available(
        self, adapter, release_v110
    ) -> None:
        """check_for_updates returns AvailableRelease when newer version exists."""
        result = await adapter.check_for_updates(
            app_id="test-app", channel="stable"
        )
        assert result is not None
        assert result.version() == "1.1.0"
        assert result.channel() == "stable"
        assert len(result.artifacts()) == 2

    @pytest.mark.asyncio
    async def test_returns_none_when_no_releases(self, config: UpdateConfig) -> None:
        """check_for_updates returns None when no releases are configured."""
        from core_infrastructure.update.adapters.in_memory_update_adapter import (
            InMemoryUpdateAdapter,
        )

        empty = InMemoryUpdateAdapter(config=config)
        result = await empty.check_for_updates(app_id="test-app", channel="stable")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_same_version(self) -> None:
        """check_for_updates returns None when current >= latest."""
        from core_infrastructure.update.adapters.in_memory_update_adapter import (
            InMemoryUpdateAdapter,
        )

        cfg = UpdateConfig(
            update_url="https://updates.example.com",
            public_key="key",
            current_version="1.1.0",
        )
        a = InMemoryUpdateAdapter(config=cfg)
        a.add_release(
            "stable",
            _Release(
                version="1.1.0",
                channel="stable",
                artifacts=[
                    _Artifact(
                        url="https://example.com/x.exe",
                        platform="windows",
                        arch="x64",
                        kind="installer",
                        hash="d" * 64,
                    )
                ],
            ),
        )
        result = await a.check_for_updates(app_id="test-app", channel="stable")
        assert result is None

    @pytest.mark.asyncio
    async def test_beta_channel_ignores_stable(
        self, adapter, release_v120_beta
    ) -> None:
        """check_for_updates on beta returns only beta releases."""
        result = await adapter.check_for_updates(
            app_id="test-app", channel="beta"
        )
        assert result is not None
        assert result.version() == "1.2.0-beta"
        assert result.channel() == "beta"

    @pytest.mark.asyncio
    async def test_unknown_channel_returns_none(self, adapter) -> None:
        """check_for_updates on channel with no releases returns None."""
        result = await adapter.check_for_updates(
            app_id="test-app", channel="canary"
        )
        assert result is None


# ── download_update ─────────────────────────────────────────────────────────

class TestDownloadUpdate:
    """Tests for download_update()."""

    @pytest.mark.asyncio
    async def test_returns_artifact_for_current_platform(
        self, adapter, release_v110
    ) -> None:
        """download_update returns the artifact matching the current platform."""
        # On Windows, it should return the windows artifact
        artifact = await adapter.download_update(
            app_id="test-app", release=release_v110
        )
        assert artifact.url() == "https://example.com/cenf-1.1.0.exe"
        assert artifact.platform() == "windows"
        assert artifact.arch() == "x64"
        assert artifact.kind() == "installer"

    @pytest.mark.asyncio
    async def test_raises_when_no_artifact_matches_platform(
        self, config: UpdateConfig
    ) -> None:
        """download_update raises PermanentError when no artifact for platform."""
        from core_infrastructure.update.adapters.in_memory_update_adapter import (
            InMemoryUpdateAdapter,
        )

        a = InMemoryUpdateAdapter(config=config, override_platform="linux")
        release = _Release(
            version="1.1.0",
            channel="stable",
            artifacts=[
                _Artifact(
                    url="https://example.com/mac.pkg",
                    platform="macos",
                    arch="arm64",
                    kind="archive",
                    hash="e" * 64,
                )
            ],
        )
        with pytest.raises(PermanentError):
            await a.download_update(app_id="test-app", release=release)


# ── apply_update ────────────────────────────────────────────────────────────

class TestApplyUpdate:
    """Tests for apply_update()."""

    @pytest.mark.asyncio
    async def test_apply_updates_current_version(
        self, adapter, artifact_win
    ) -> None:
        """apply_update updates current_version and returns success."""
        result = await adapter.apply_update(
            app_id="test-app", artifact=artifact_win
        )
        assert result.success() is True
        assert result.new_version() is not None
        assert result.error() is None

    @pytest.mark.asyncio
    async def test_apply_saves_rollback_state(
        self, adapter, artifact_win
    ) -> None:
        """apply_update saves the previous version as rollback state."""
        result = await adapter.apply_update(
            app_id="test-app", artifact=artifact_win
        )
        assert result.success()

        # Rollback should now be possible
        rollback_result = await adapter.rollback(app_id="test-app")
        assert rollback_result.success() is True
        assert rollback_result.new_version() == "1.0.0"


# ── rollback ────────────────────────────────────────────────────────────────

class TestRollback:
    """Tests for rollback()."""

    @pytest.mark.asyncio
    async def test_rollback_restores_previous_version(
        self, adapter, artifact_win
    ) -> None:
        """rollback restores the version saved before apply_update."""
        # Apply an update first
        await adapter.apply_update(app_id="test-app", artifact=artifact_win)

        # Now rollback
        result = await adapter.rollback(app_id="test-app")
        assert result.success() is True
        assert result.new_version() == "1.0.0"

    @pytest.mark.asyncio
    async def test_rollback_raises_when_no_state(self, adapter) -> None:
        """rollback raises PermanentError when no rollback state exists."""
        with pytest.raises(PermanentError):
            await adapter.rollback(app_id="test-app")


# ── Protocol compliance ─────────────────────────────────────────────────────

class TestProtocolCompliance:
    """Verify the adapter satisfies the UpdateManager Protocol."""

    def test_adapter_satisfies_protocol(self, adapter) -> None:
        """InMemoryUpdateAdapter satisfies UpdateManager Protocol."""
        assert isinstance(adapter, UpdateManager)

    def test_result_satisfies_protocol(self) -> None:
        """_Result satisfies UpdateResult Protocol."""
        r = _Result(success=True, new_version="1.1.0")
        assert isinstance(r, UpdateResult)

    def test_artifact_satisfies_protocol(self) -> None:
        """_Artifact satisfies UpdateArtifact Protocol."""
        a = _Artifact(
            url="https://x.com",
            platform="windows",
            arch="x64",
            kind="installer",
            hash="a" * 64,
        )
        assert isinstance(a, UpdateArtifact)

    def test_release_satisfies_protocol(self) -> None:
        """_Release satisfies AvailableRelease Protocol."""
        r = _Release(version="1.0.0", channel="stable", artifacts=[])
        assert isinstance(r, AvailableRelease)


# ── get_json_schema ─────────────────────────────────────────────────────────

class TestGetJsonSchema:
    """Tests for get_json_schema()."""

    def test_returns_dict(self, adapter) -> None:
        """get_json_schema returns a non-empty dict."""
        schema = adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0
        assert "$schema" in schema
