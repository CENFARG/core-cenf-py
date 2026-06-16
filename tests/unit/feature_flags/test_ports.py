"""Unit tests for FeatureFlagManager Protocol and Pydantic models.

Tests cover:
- FeatureFlagManager Protocol contract (is_enabled, get_flag_value, get_all_flags, refresh)
- Protocol is runtime-checkable
- FlagContext Pydantic model validation and defaults
- FlagConfig Pydantic model validation and defaults
- FeatureFlag Pydantic model validation

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.feature_flags.models import (
    FeatureFlag,
    FlagConfig,
    FlagContext,
)
from core_infrastructure.feature_flags.ports import FeatureFlagManager


class TestFeatureFlagManagerProtocol:
    """Verify FeatureFlagManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """FeatureFlagManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(FeatureFlagManager, "_is_runtime_protocol") or hasattr(
            FeatureFlagManager, "__protocol_attrs__"
        )

    def test_has_is_enabled_method(self) -> None:
        """Protocol requires is_enabled(flag_key, context) -> bool."""
        assert hasattr(FeatureFlagManager, "is_enabled")

    def test_has_get_flag_value_method(self) -> None:
        """Protocol requires get_flag_value(flag_key, context, default) -> Any."""
        assert hasattr(FeatureFlagManager, "get_flag_value")

    def test_has_get_all_flags_method(self) -> None:
        """Protocol requires get_all_flags(context) -> dict[str, bool]."""
        assert hasattr(FeatureFlagManager, "get_all_flags")

    def test_has_refresh_method(self) -> None:
        """Protocol requires refresh()."""
        assert hasattr(FeatureFlagManager, "refresh")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all methods satisfies the protocol."""

        class ValidFlags:
            def is_enabled(self, flag_key, context=None) -> bool: ...
            def get_flag_value(self, flag_key, context=None, default=None): ...
            def get_all_flags(self, context=None) -> dict: ...
            async def refresh(self) -> None: ...

        assert isinstance(ValidFlags(), FeatureFlagManager)

    def test_class_missing_is_enabled_fails_protocol(self) -> None:
        """A class without is_enabled() does NOT satisfy the protocol."""

        class Incomplete:
            def get_all_flags(self, context=None) -> dict: ...

        assert not isinstance(Incomplete(), FeatureFlagManager)


class TestFlagContextModel:
    """Verify FlagContext Pydantic model."""

    def test_default_context(self) -> None:
        """FlagContext creates with sensible defaults."""
        ctx = FlagContext()
        assert ctx.tenant_id == "global"
        assert ctx.environment == "development"
        assert ctx.attributes == {}

    def test_custom_context(self) -> None:
        """FlagContext accepts custom values."""
        ctx = FlagContext(
            tenant_id="tenant-1",
            environment="staging",
            attributes={"region": "us-east-1"},
        )
        assert ctx.tenant_id == "tenant-1"
        assert ctx.environment == "staging"
        assert ctx.attributes == {"region": "us-east-1"}

    def test_tenant_id_min_length(self) -> None:
        """tenant_id must be at least 1 character."""
        with pytest.raises(PydanticValidationError):
            FlagContext(tenant_id="")


class TestFlagConfigModel:
    """Verify FlagConfig Pydantic model validation and defaults."""

    def test_default_config(self) -> None:
        """FlagConfig creates with sensible defaults."""
        config = FlagConfig()
        assert config.provider == "memory"
        assert config.cache_ttl == 60
        assert config.default_all is False

    def test_custom_config(self) -> None:
        """FlagConfig accepts custom values."""
        config = FlagConfig(provider="unleash", cache_ttl=120, default_all=True)
        assert config.provider == "unleash"
        assert config.cache_ttl == 120
        assert config.default_all is True

    def test_invalid_provider_fails(self) -> None:
        """provider must be 'memory' or 'unleash'."""
        with pytest.raises(PydanticValidationError):
            FlagConfig(provider="launchdarkly")  # type: ignore[arg-type]


class TestFeatureFlagModel:
    """Verify FeatureFlag Pydantic model."""

    def test_feature_flag_creation(self) -> None:
        """FeatureFlag creates with required fields."""
        flag = FeatureFlag(key="new-feature", enabled=True)
        assert flag.key == "new-feature"
        assert flag.enabled is True
        assert flag.value is None
        assert flag.rules == []

    def test_feature_flag_with_rules(self) -> None:
        """FeatureFlag supports rules for context-based evaluation."""
        flag = FeatureFlag(
            key="beta-feature",
            enabled=True,
            value={"variant": "B"},
            rules=[
                {"attribute": "environment", "operator": "eq", "value": "staging"},
                {"attribute": "region", "operator": "eq", "value": "us-east-1"},
            ],
        )
        assert len(flag.rules) == 2
        assert flag.value == {"variant": "B"}
