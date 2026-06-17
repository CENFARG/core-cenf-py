"""Unit tests for AlertManager Protocol and AlertRule/AlertLevel models.

Tests cover:
- AlertManager Protocol contract (send_alert, register_rule, evaluate_and_alert, get_json_schema)
- Protocol is runtime-checkable
- AlertLevel enum values
- AlertRule Pydantic model validation
- Protocol satisfaction checks

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.alert.ports import AlertLevel, AlertManager, AlertRule


class TestAlertLevelEnum:
    """Verify AlertLevel StrEnum values."""

    def test_info_value(self) -> None:
        """AlertLevel.INFO has correct value."""
        assert AlertLevel.INFO == "info"

    def test_warning_value(self) -> None:
        """AlertLevel.WARNING has correct value."""
        assert AlertLevel.WARNING == "warning"

    def test_critical_value(self) -> None:
        """AlertLevel.CRITICAL has correct value."""
        assert AlertLevel.CRITICAL == "critical"

    def test_string_equality(self) -> None:
        """AlertLevel members compare equal to their string values."""
        assert AlertLevel.INFO == "info"
        assert AlertLevel.WARNING == "warning"


class TestAlertRuleModel:
    """Verify AlertRule Pydantic model validation."""

    def test_valid_rule_construction(self) -> None:
        """AlertRule can be constructed with required fields."""
        rule = AlertRule(
            rule_id="high_error_rate",
            condition={"error_rate": 0.05},
            level=AlertLevel.CRITICAL,
            channels=["slack"],
        )
        assert rule.rule_id == "high_error_rate"
        assert rule.condition == {"error_rate": 0.05}
        assert rule.level == AlertLevel.CRITICAL
        assert rule.channels == ["slack"]
        assert rule.throttle_seconds == 60

    def test_default_throttle(self) -> None:
        """AlertRule has a default throttle_seconds of 60."""
        rule = AlertRule(
            rule_id="test",
            condition={},
            channels=["slack"],
        )
        assert rule.throttle_seconds == 60

    def test_custom_throttle(self) -> None:
        """AlertRule accepts a custom throttle_seconds."""
        rule = AlertRule(
            rule_id="test",
            condition={},
            channels=["slack"],
            throttle_seconds=300,
        )
        assert rule.throttle_seconds == 300

    def test_default_level(self) -> None:
        """AlertRule defaults to WARNING level."""
        rule = AlertRule(
            rule_id="test",
            condition={},
            channels=["slack"],
        )
        assert rule.level == AlertLevel.WARNING

    def test_empty_rule_id_fails(self) -> None:
        """rule_id must not be empty."""
        with pytest.raises(PydanticValidationError):
            AlertRule(rule_id="", condition={}, channels=["slack"])

    def test_empty_channels_fails(self) -> None:
        """channels must have at least one entry."""
        with pytest.raises(PydanticValidationError):
            AlertRule(rule_id="test", condition={}, channels=[])

    def test_multiple_channels(self) -> None:
        """AlertRule supports multiple channels."""
        rule = AlertRule(
            rule_id="test",
            condition={},
            channels=["slack", "discord", "email"],
        )
        assert len(rule.channels) == 3

    def test_frozen_model_immutable(self) -> None:
        """AlertRule is frozen — attributes cannot be changed."""
        rule = AlertRule(rule_id="test", condition={}, channels=["slack"])
        with pytest.raises((TypeError, ValueError)):
            rule.rule_id = "new-id"  # type: ignore[misc]

    def test_extra_fields_forbidden(self) -> None:
        """AlertRule rejects extra fields."""
        with pytest.raises(PydanticValidationError):
            AlertRule(rule_id="test", condition={}, channels=["slack"], extra="nope")


class TestAlertManagerProtocol:
    """Verify AlertManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """AlertManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(AlertManager, "_is_runtime_protocol") or hasattr(
            AlertManager, "__protocol_attrs__"
        )

    def test_has_send_alert_method(self) -> None:
        """Protocol requires send_alert(level, title, message, metadata)."""
        assert hasattr(AlertManager, "send_alert")

    def test_has_register_rule_method(self) -> None:
        """Protocol requires register_rule(rule)."""
        assert hasattr(AlertManager, "register_rule")

    def test_has_evaluate_and_alert_method(self) -> None:
        """Protocol requires evaluate_and_alert(event_context)."""
        assert hasattr(AlertManager, "evaluate_and_alert")

    def test_has_get_json_schema_method(self) -> None:
        """Protocol requires get_json_schema()."""
        assert hasattr(AlertManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all AlertManager methods satisfies the protocol."""

        class ValidAlert:
            async def send_alert(self, level, title, message, metadata=None): ...
            def register_rule(self, rule): ...
            async def evaluate_and_alert(self, event_context): ...
            @staticmethod
            def get_json_schema(): ...

        assert isinstance(ValidAlert(), AlertManager)

    def test_class_missing_send_alert_fails_protocol(self) -> None:
        """A class without send_alert() does NOT satisfy the protocol."""

        class Incomplete:
            def register_rule(self, rule): ...

        assert not isinstance(Incomplete(), AlertManager)
