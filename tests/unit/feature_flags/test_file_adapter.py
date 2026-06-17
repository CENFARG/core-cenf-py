"""Unit tests for FileFeatureFlagAdapter — YAML file-backed FeatureFlagManager.

Tests cover:
- Protocol compliance (satisfies FeatureFlagManager)
- Loading flags from a YAML file
- is_enabled with rule-based evaluation
- get_flag_value and get_all_flags
- Default behavior for missing flags (never throws)
- Hot-reload when YAML file changes
- Rule matching with simple condition dicts

Uses temporary YAML files via tmp_path fixture.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
import yaml

from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.feature_flags.models import FlagContext
from core_infrastructure.feature_flags.ports import FeatureFlagManager
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_flags_file(path: Path, flags: dict) -> None:
    """Write a YAML flags file."""
    path.write_text(yaml.dump(flags), encoding="utf-8")


SAMPLE_FLAGS_YAML = {
    "new-feature": {"enabled": True, "rules": [], "default": False},
    "beta-feature": {
        "enabled": True,
        "rules": [{"condition": {"environment": "staging"}}],
        "default": False,
    },
    "admin-only": {
        "enabled": True,
        "rules": [{"condition": {"role": "admin"}}],
        "default": False,
    },
    "disabled-feature": {"enabled": False, "rules": [], "default": False},
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_flags_file(tmp_path: Path) -> Path:
    """Create a temporary YAML flags file."""
    path = tmp_path / "flags.yaml"
    _write_flags_file(path, SAMPLE_FLAGS_YAML)
    return path


@pytest.fixture
def config(tmp_flags_file: Path) -> InMemoryConfigAdapter:
    """Create config pointing to temp flags file."""
    return InMemoryConfigAdapter(
        initial_data={
            "feature_flags": {
                "file_path": str(tmp_flags_file),
                "provider": "file",
            },
        }
    )


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """Create InMemoryLoggerAdapter."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    """Create InMemoryObservabilityAdapter."""
    return InMemoryObservabilityAdapter()


@pytest.fixture
def error_handler(
    config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, observability: InMemoryObservabilityAdapter
) -> CapturingErrorAdapter:
    """Create CapturingErrorAdapter."""
    return CapturingErrorAdapter(config, logger, observability)


@pytest.fixture
def adapter(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
    error_handler: CapturingErrorAdapter,
):
    """Create a FileFeatureFlagAdapter with temp YAML file."""
    from core_infrastructure.feature_flags.adapters.file_feature_flag_adapter import (
        FileFeatureFlagAdapter,
    )

    return FileFeatureFlagAdapter(config, logger, error_handler)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFileFeatureFlagAdapterProtocol:
    """Verify FileFeatureFlagAdapter satisfies FeatureFlagManager Protocol."""

    def test_satisfies_feature_flag_manager_protocol(self, adapter) -> None:
        """FileFeatureFlagAdapter passes isinstance check."""
        assert isinstance(adapter, FeatureFlagManager)


class TestFileFeatureFlagAdapterLoading:
    """Verify flag loading from YAML file."""

    def test_loads_flags_from_yaml_file(self, adapter) -> None:
        """Flags are loaded from the YAML file on init."""
        assert adapter.is_enabled("new-feature") is True
        assert adapter.is_enabled("disabled-feature") is False

    def test_unknown_flag_returns_false(self, adapter) -> None:
        """Unknown flags return False (fail-safe, never throws)."""
        assert adapter.is_enabled("nonexistent-flag") is False

    def test_unknown_flag_uses_default_when_configured(self, tmp_path: Path) -> None:
        """Unknown flags can return True if default is True."""
        from core_infrastructure.feature_flags.adapters.file_feature_flag_adapter import (
            FileFeatureFlagAdapter,
        )

        cfg = InMemoryConfigAdapter(
            initial_data={
                "feature_flags": {
                    "file_path": str(tmp_path / "empty.yaml"),
                    "default_all": True,
                },
            }
        )
        _write_flags_file(tmp_path / "empty.yaml", {})
        logger = InMemoryLoggerAdapter()
        obs = InMemoryObservabilityAdapter()
        err = CapturingErrorAdapter(cfg, logger, obs)

        adapter = FileFeatureFlagAdapter(cfg, logger, err)
        assert adapter.is_enabled("any-unknown") is True


class TestFileFeatureFlagAdapterRuleEvaluation:
    """Verify rule-based flag evaluation."""

    def test_rule_matches_by_environment(self, adapter) -> None:
        """Flag with environment rule matches correct context."""
        staging_ctx = FlagContext(environment="staging")
        prod_ctx = FlagContext(environment="production")

        assert adapter.is_enabled("beta-feature", staging_ctx) is True
        assert adapter.is_enabled("beta-feature", prod_ctx) is False

    def test_rule_matches_by_attribute(self, adapter) -> None:
        """Flag with role attribute rule matches correct context."""
        admin_ctx = FlagContext(attributes={"role": "admin"})
        user_ctx = FlagContext(attributes={"role": "user"})

        assert adapter.is_enabled("admin-only", admin_ctx) is True
        assert adapter.is_enabled("admin-only", user_ctx) is False

    def test_evaluation_never_throws_on_error(self, adapter) -> None:
        """Even with broken data, is_enabled never raises."""
        # Force a problematic scenario: flag not found returns False
        result = adapter.is_enabled("nonexistent", FlagContext(environment="staging"))
        assert result is False


class TestFileFeatureFlagAdapterGetFlagValue:
    """Verify get_flag_value behavior."""

    def test_get_flag_value_returns_default_for_missing(self, adapter) -> None:
        """get_flag_value returns provided default for missing flags."""
        result = adapter.get_flag_value("missing-flag", default="fallback")
        assert result == "fallback"

    def test_get_all_flags_evaluates_all(self, adapter) -> None:
        """get_all_flags returns all flag states against context."""
        staging_ctx = FlagContext(environment="staging")

        flags = adapter.get_all_flags(staging_ctx)
        assert flags["new-feature"] is True
        assert flags["beta-feature"] is True  # staging matches
        assert flags["disabled-feature"] is False

        prod_ctx = FlagContext(environment="production")
        flags_prod = adapter.get_all_flags(prod_ctx)
        assert flags_prod["beta-feature"] is False  # production doesn't match

    def test_get_all_flags_empty_when_no_file(self, tmp_path: Path) -> None:
        """get_all_flags returns empty dict when no flags exist."""
        from core_infrastructure.feature_flags.adapters.file_feature_flag_adapter import (
            FileFeatureFlagAdapter,
        )

        cfg = InMemoryConfigAdapter(
            initial_data={"feature_flags": {"file_path": str(tmp_path / "nonexistent.yaml")}}
        )
        logger = InMemoryLoggerAdapter()
        obs = InMemoryObservabilityAdapter()
        err = CapturingErrorAdapter(cfg, logger, obs)

        adapter = FileFeatureFlagAdapter(cfg, logger, err)
        flags = adapter.get_all_flags()
        assert flags == {}


class TestFileFeatureFlagAdapterHotReload:
    """Verify hot-reload when YAML file changes."""

    def test_reloads_when_file_changes(self, tmp_flags_file: Path, adapter) -> None:
        """Flag state updates when YAML file is modified and reloaded."""
        # Initially disabled
        assert adapter.is_enabled("new-feature") is True

        # Modify the file - disable new-feature
        updated = dict(SAMPLE_FLAGS_YAML)
        updated["new-feature"] = {"enabled": False, "rules": [], "default": False}
        _write_flags_file(tmp_flags_file, updated)

        # Wait for hot-reload to detect change (or trigger manually)
        adapter._reload_sync()

        # Now it should be disabled
        assert adapter.is_enabled("new-feature") is False

    def test_adds_new_flag_on_reload(self, tmp_flags_file: Path, adapter) -> None:
        """New flags added to YAML appear after reload."""
        assert adapter.is_enabled("brand-new-flag") is False

        updated = dict(SAMPLE_FLAGS_YAML)
        updated["brand-new-flag"] = {"enabled": True, "rules": [], "default": False}
        _write_flags_file(tmp_flags_file, updated)

        adapter._reload_sync()

        assert adapter.is_enabled("brand-new-flag") is True

    def test_reload_is_atomic(self, tmp_flags_file: Path, adapter) -> None:
        """Reload doesn't break existing evaluations mid-reload."""
        assert adapter.is_enabled("new-feature") is True

        updated = dict(SAMPLE_FLAGS_YAML)
        updated["new-feature"] = {"enabled": False, "rules": [], "default": False}
        _write_flags_file(tmp_flags_file, updated)

        adapter._reload_sync()

        assert adapter.is_enabled("new-feature") is False
        # Other flags unaffected
        assert adapter.is_enabled("disabled-feature") is False

    @pytest.mark.asyncio
    async def test_refresh_does_not_raise(self, adapter) -> None:
        """refresh() completes without raising errors."""
        await adapter.refresh()

    @pytest.mark.asyncio
    async def test_reload_async(self, tmp_flags_file: Path, adapter) -> None:
        """Async _reload also works."""
        updated = dict(SAMPLE_FLAGS_YAML)
        updated["new-feature"] = {"enabled": False, "rules": [], "default": False}
        _write_flags_file(tmp_flags_file, updated)

        await adapter._reload()

        assert adapter.is_enabled("new-feature") is False
