"""Unit tests for MemoryFeatureFlagAdapter — in-memory dict-backed FeatureFlagManager.

Tests cover:
- Protocol compliance (satisfies FeatureFlagManager)
- is_enabled returns True for enabled flags
- is_enabled returns False for disabled flags
- is_enabled returns False for unknown flags (default)
- Context-based evaluation (environment matching)
- get_flag_value with and without defaults
- get_all_flags listing
- refresh() operation

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import (
    FeatureFlag,
    FlagConfig,
    FlagContext,
)
from core_infrastructure.feature_flags.ports import FeatureFlagManager


@pytest.fixture
def config() -> FlagConfig:
    """Create a default FlagConfig."""
    return FlagConfig(provider="memory", cache_ttl=60, default_all=False)


@pytest.fixture
def adapter(config: FlagConfig) -> MemoryFeatureFlagAdapter:
    """Create a MemoryFeatureFlagAdapter with default config."""
    return MemoryFeatureFlagAdapter(config=config)


class TestMemoryFeatureFlagAdapterProtocol:
    """Verify adapter satisfies FeatureFlagManager Protocol."""

    def test_satisfies_feature_flag_manager_protocol(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """MemoryFeatureFlagAdapter passes isinstance check."""
        assert isinstance(adapter, FeatureFlagManager)


class TestIsEnabled:
    """Verify is_enabled behavior."""

    def test_is_enabled_returns_true_for_enabled_flag(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """is_enabled returns True for an enabled flag."""
        adapter.set_flag(FeatureFlag(key="new-feature", enabled=True))
        assert adapter.is_enabled("new-feature") is True

    def test_is_enabled_returns_false_for_disabled_flag(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """is_enabled returns False for a disabled flag."""
        adapter.set_flag(FeatureFlag(key="old-feature", enabled=False))
        assert adapter.is_enabled("old-feature") is False

    def test_is_enabled_returns_false_for_unknown_flag(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """is_enabled returns False for unknown flags (default)."""
        assert adapter.is_enabled("nonexistent") is False

    def test_is_enabled_returns_default_when_configured(self, config: FlagConfig) -> None:
        """is_enabled returns config.default_all for unknown flags."""
        adapter_all_true = MemoryFeatureFlagAdapter(
            config=FlagConfig(default_all=True)
        )
        assert adapter_all_true.is_enabled("any-feature") is True


class TestContextEvaluation:
    """Verify context-based flag evaluation (environment matching)."""

    def test_flag_respects_environment_context(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """is_enabled evaluates rules against the provided context."""
        adapter.set_flag(
            FeatureFlag(
                key="staging-only",
                enabled=True,
                rules=[{"attribute": "environment", "operator": "eq", "value": "staging"}],
            )
        )

        staging_ctx = FlagContext(environment="staging")
        prod_ctx = FlagContext(environment="production")

        assert adapter.is_enabled("staging-only", staging_ctx) is True
        assert adapter.is_enabled("staging-only", prod_ctx) is False

    def test_flag_without_rules_always_evaluates(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """A flag without rules is evaluated purely on enabled state."""
        adapter.set_flag(FeatureFlag(key="global-flag", enabled=True))

        ctx = FlagContext(environment="any")
        assert adapter.is_enabled("global-flag", ctx) is True

    def test_flag_with_non_matching_rule_is_disabled(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """A flag with rules that don't match the context is treated as disabled."""
        adapter.set_flag(
            FeatureFlag(
                key="region-specific",
                enabled=True,
                rules=[{"attribute": "environment", "operator": "eq", "value": "us-east-1"}],
            )
        )

        ctx = FlagContext(environment="eu-west-1")
        assert adapter.is_enabled("region-specific", ctx) is False


class TestGetFlagValue:
    """Verify get_flag_value behavior."""

    def test_get_flag_value_returns_value_for_known_flag(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """get_flag_value returns the flag's value."""
        adapter.set_flag(
            FeatureFlag(key="theme", enabled=True, value={"color": "dark"})
        )
        result = adapter.get_flag_value("theme")
        assert result == {"color": "dark"}

    def test_get_flag_value_returns_default_for_unknown_flag(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """get_flag_value returns the default value for unknown flags."""
        result = adapter.get_flag_value("unknown", default="fallback")
        assert result == "fallback"

    def test_get_flag_value_returns_none_default_for_unknown(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """get_flag_value returns None if no default provided and flag unknown."""
        result = adapter.get_flag_value("unknown")
        assert result is None


class TestGetAllFlags:
    """Verify get_all_flags behavior."""

    def test_get_all_flags_returns_all_flag_states(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """get_all_flags returns a dict of all flag keys to enabled state."""
        adapter.set_flag(FeatureFlag(key="flag-a", enabled=True))
        adapter.set_flag(FeatureFlag(key="flag-b", enabled=False))
        adapter.set_flag(FeatureFlag(key="flag-c", enabled=True))

        flags = adapter.get_all_flags()
        assert flags == {"flag-a": True, "flag-b": False, "flag-c": True}

    def test_get_all_flags_empty_when_no_flags_set(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """get_all_flags returns empty dict when no flags configured."""
        flags = adapter.get_all_flags()
        assert flags == {}

    def test_get_all_flags_with_context_filters(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """get_all_flags evaluates rules against context."""
        adapter.set_flag(
            FeatureFlag(
                key="staging-flag",
                enabled=True,
                rules=[{"attribute": "environment", "operator": "eq", "value": "staging"}],
            )
        )
        adapter.set_flag(FeatureFlag(key="global-flag", enabled=True))

        staging_ctx = FlagContext(environment="staging")
        prod_ctx = FlagContext(environment="production")

        staging_flags = adapter.get_all_flags(staging_ctx)
        prod_flags = adapter.get_all_flags(prod_ctx)

        assert staging_flags == {"staging-flag": True, "global-flag": True}
        assert prod_flags == {"staging-flag": False, "global-flag": True}


class TestRefresh:
    """Verify refresh() behavior."""

    @pytest.mark.asyncio
    async def test_refresh_does_not_raise(self, adapter: MemoryFeatureFlagAdapter) -> None:
        """refresh() completes without raising (no-op for in-memory adapter)."""
        await adapter.refresh()  # Should not raise
