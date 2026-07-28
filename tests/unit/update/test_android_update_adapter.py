"""Tests for AndroidUpdateAdapter."""

import pytest
from core_infrastructure.common.errors import PermanentError
from core_infrastructure.update.adapters.android_update_adapter import AndroidUpdateAdapter


@pytest.fixture
def adapter():
    return AndroidUpdateAdapter("test-app", 1, "1.0.0")


class TestAndroidUpdateAdapter:
    async def test_get_current_version(self, adapter):
        assert await adapter.get_current_version() == "1.0.0"

    async def test_check_play_store_returns_none(self, adapter):
        result = await adapter.check_for_updates()
        assert result is None

    async def test_check_self_hosted_no_endpoint(self):
        adapter = AndroidUpdateAdapter("app", 1, "1.0.0", is_play_store=False)
        result = await adapter.check_for_updates()
        assert result is None

    async def test_apply_update_updates_version(self, adapter):
        from core_infrastructure.update.adapters.android_update_adapter import _AndroidArtifact
        result = await adapter.apply_update(artifact=_AndroidArtifact("2.0.0", "url"))
        assert result.success()

    async def test_rollback_raises_permanent_error(self, adapter):
        with pytest.raises(PermanentError):
            await adapter.rollback()
