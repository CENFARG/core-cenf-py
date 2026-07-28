"""Tests for GitHubReleaseAdapter."""

import pytest
from core_infrastructure.update.adapters.github_release_adapter import GitHubReleaseAdapter


class MockGHResponse:
    def __init__(self, data: dict | None = None, status: int = 200):
        self._data = data or {"tag_name": "v2.0.0", "assets": []}
        self.status_code = status

    def json(self):
        return self._data

    async def get(self, url: str):
        return self


@pytest.fixture
def adapter():
    return GitHubReleaseAdapter("test-app", "org/repo", "1.0.0")


class TestGitHubReleaseAdapter:
    async def test_get_current_version(self, adapter):
        assert await adapter.get_current_version() == "1.0.0"

    async def test_check_no_update_when_no_http(self, adapter):
        result = await adapter.check_for_updates()
        assert result is None

    async def test_check_update_when_new_release(self):
        http = MockGHResponse({"tag_name": "v3.0.0", "assets": []})
        adapter = GitHubReleaseAdapter("test-app", "org/repo", "1.0.0", http_client=http)
        result = await adapter.check_for_updates()
        assert result is not None
        assert result.version() == "3.0.0"

    async def test_check_no_update_same_tag(self):
        http = MockGHResponse({"tag_name": "v1.0.0", "assets": []})
        adapter = GitHubReleaseAdapter("test-app", "org/repo", "1.0.0", http_client=http)
        result = await adapter.check_for_updates()
        assert result is None

    async def test_apply_update_updates_version(self, adapter):
        from core_infrastructure.update.adapters.github_release_adapter import _GHArtifact
        result = await adapter.apply_update(artifact=_GHArtifact("url", "v3.0.0"))
        assert result.success()

    async def test_rollback_returns_ok(self, adapter):
        result = await adapter.rollback()
        assert result.success()
