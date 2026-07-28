"""Tests for PipUpdateAdapter — CLI update via Git SHAs with pip install."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core_infrastructure.update.adapters.pip_update_adapter import PipUpdateAdapter
from core_infrastructure.update.ports import AvailableRelease, UpdateArtifact


@pytest.fixture
def state_file(tmp_path: Path) -> Path:
    return tmp_path / "update_state.json"


@pytest.fixture
def adapter(state_file: Path) -> PipUpdateAdapter:
    return PipUpdateAdapter(
        app_id="test-cli",
        repo_url="https://github.com/org/repo.git",
        state_file=state_file,
    )


class TestGetCurrentVersion:
    async def test_returns_default_when_no_state_file(self, adapter: PipUpdateAdapter):
        version = await adapter.get_current_version()
        assert version == "0.0.0"

    async def test_returns_current_sha_from_state_file(self, state_file: Path):
        state_file.write_text(json.dumps({
            "current_sha": "abc123def",
            "previous_stable_sha": "old456",
        }))
        adapter = PipUpdateAdapter("test-cli", "https://github.com/org/repo.git", state_file)
        version = await adapter.get_current_version()
        assert version == "abc123def"


class TestCheckForUpdates:
    @pytest.fixture
    def mock_head_sha(self) -> str:
        return "new789sha"

    async def test_returns_release_when_sha_differs(self, adapter: PipUpdateAdapter, mock_head_sha: str):
        adapter._fetch_head_sha = AsyncMock(return_value=mock_head_sha)
        adapter._current_sha = "abc123def"
        release = await adapter.check_for_updates()
        assert release is not None
        assert release.version() == mock_head_sha[:7]

    async def test_returns_none_when_same_sha(self, adapter: PipUpdateAdapter):
        adapter._fetch_head_sha = AsyncMock(return_value="abc123def")
        adapter._current_sha = "abc123def"
        release = await adapter.check_for_updates()
        assert release is None

    async def test_raises_on_api_failure(self, adapter: PipUpdateAdapter):
        adapter._fetch_head_sha = AsyncMock(side_effect=Exception("Network error"))
        from core_infrastructure.common.errors import TransientError
        with pytest.raises(TransientError):
            await adapter.check_for_updates()


class TestDownloadUpdate:
    async def test_returns_artifact_on_success(self, adapter: PipUpdateAdapter):
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"Success", b""))
            mock_subprocess.return_value = mock_proc

            release = _make_release("new789sha")
            artifact = await adapter.download_update(release=release)
            assert artifact is not None
            assert artifact.platform() == "python-cli"

    async def test_raises_on_pip_failure(self, adapter: PipUpdateAdapter):
        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(b"", b"pip error"))
            mock_subprocess.return_value = mock_proc

            release = _make_release("failsha")
            from core_infrastructure.common.errors import TransientError
            with pytest.raises(TransientError):
                await adapter.download_update(release=release)


class TestApplyUpdate:
    async def test_updates_state_file_on_success(self, state_file: Path, adapter: PipUpdateAdapter):
        state_file.write_text(json.dumps({"current_sha": "oldsha", "previous_stable_sha": "older"}))
        adapter._current_sha = "oldsha"
        adapter._previous_stable_sha = "older"

        artifact = _make_artifact("new789sha")
        result = await adapter.apply_update(artifact=artifact)
        assert result.success()
        assert result.new_version() == "new789sha"[:7]
        data = json.loads(state_file.read_text())
        assert data["current_sha"] == "new789sha"
        assert data["previous_stable_sha"] == "oldsha"


class TestRollback:
    async def test_rolls_back_to_previous_sha(self, state_file: Path):
        state_file.write_text(json.dumps({
            "current_sha": "badsha",
            "previous_stable_sha": "goodsha",
        }))
        adapter = PipUpdateAdapter("test-cli", "https://github.com/org/repo.git", state_file)

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"OK", b""))
            mock_subprocess.return_value = mock_proc

            result = await adapter.rollback()
            assert result.success()

    async def test_raises_when_no_rollback_state(self, adapter: PipUpdateAdapter):
        from core_infrastructure.common.errors import PermanentError
        with pytest.raises(PermanentError):
            await adapter.rollback()


def _make_release(sha: str) -> AvailableRelease:
    from core_infrastructure.update.adapters.pip_update_adapter import _PipAvailableRelease
    return _PipAvailableRelease(version_str=sha[:7], sha=sha)


def _make_artifact(sha: str) -> UpdateArtifact:
    from core_infrastructure.update.adapters.pip_update_adapter import _PipUpdateArtifact
    return _PipUpdateArtifact(target_sha=sha)
