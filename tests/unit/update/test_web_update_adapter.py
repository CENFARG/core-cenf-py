"""Tests for WebUpdateAdapter — SPA/PWA force-refresh."""

import pytest
from core_infrastructure.update.adapters.web_update_adapter import WebUpdateAdapter


class MockHttpClient:
    def __init__(self, headers: dict | None = None, status: int = 200):
        self.headers = headers or {}
        self.status_code = status

    async def get(self, url: str):
        return self


@pytest.fixture
def adapter():
    return WebUpdateAdapter("test-app", "1.0.0")


class TestWebUpdateAdapter:
    async def test_get_current_version(self, adapter):
        assert await adapter.get_current_version() == "1.0.0"

    async def test_check_no_update_when_no_http(self, adapter):
        result = await adapter.check_for_updates()
        assert result is None

    async def test_check_update_when_version_differs(self):
        http = MockHttpClient(headers={"x-client-version": "2.0.0"})
        adapter = WebUpdateAdapter("test-app", "1.0.0", http_client=http)
        result = await adapter.check_for_updates()
        assert result is not None
        assert result.version() == "2.0.0"

    async def test_check_no_update_same_version(self):
        http = MockHttpClient(headers={"x-client-version": "1.0.0"})
        adapter = WebUpdateAdapter("test-app", "1.0.0", http_client=http)
        result = await adapter.check_for_updates()
        assert result is None

    async def test_apply_update_updates_version(self, adapter):
        from core_infrastructure.update.adapters.web_update_adapter import _WebArtifact
        result = await adapter.apply_update(artifact=_WebArtifact("2.0.0"))
        assert result.success()
        assert result.new_version() == "2.0.0"

    async def test_rollback_noop(self, adapter):
        result = await adapter.rollback()
        assert result.success()
