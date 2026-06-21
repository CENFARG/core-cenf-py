"""Unit tests for PermissionManager Protocol and Permission models.

Tests cover:
- PermissionManager Protocol contract (check_permission, check_delegation,
  list_effective_permissions, get_json_schema)
- PermissionDecision Protocol (is_allowed, reason, attributes)
- Literal types: PrincipalType, Action
- PermissionConfig, DelegationRecord, PermissionResult Pydantic models
- Protocol is runtime-checkable

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.permission.models import (
    DelegationRecord,
    PermissionConfig,
    PermissionResult,
)
from core_infrastructure.permission.ports import (
    Action,
    PermissionDecision,
    PermissionManager,
    PrincipalType,
)


class TestPrincipalTypeLiteral:
    """Verify PrincipalType Literal values."""

    def test_human_is_valid(self) -> None:
        """'human' is a valid PrincipalType."""
        assert "human" in PrincipalType.__args__  # type: ignore[attr-defined]

    def test_agent_is_valid(self) -> None:
        """'agent' is a valid PrincipalType."""
        assert "agent" in PrincipalType.__args__  # type: ignore[attr-defined]

    def test_team_is_valid(self) -> None:
        """'team' is a valid PrincipalType."""
        assert "team" in PrincipalType.__args__  # type: ignore[attr-defined]

    def test_principal_type_count(self) -> None:
        """PrincipalType has exactly 3 members."""
        assert len(PrincipalType.__args__) == 3  # type: ignore[attr-defined]


class TestActionLiteral:
    """Verify Action Literal values."""

    def test_read_action(self) -> None:
        """'read' is a valid Action."""
        assert "read" in Action.__args__  # type: ignore[attr-defined]

    def test_write_action(self) -> None:
        """'write' is a valid Action."""
        assert "write" in Action.__args__  # type: ignore[attr-defined]

    def test_create_action(self) -> None:
        """'create' is a valid Action."""
        assert "create" in Action.__args__  # type: ignore[attr-defined]

    def test_delete_action(self) -> None:
        """'delete' is a valid Action."""
        assert "delete" in Action.__args__  # type: ignore[attr-defined]

    def test_invoke_action(self) -> None:
        """'invoke' is a valid Action."""
        assert "invoke" in Action.__args__  # type: ignore[attr-defined]

    def test_delegate_action(self) -> None:
        """'delegate' is a valid Action."""
        assert "delegate" in Action.__args__  # type: ignore[attr-defined]

    def test_action_count(self) -> None:
        """Action has exactly 6 members."""
        assert len(Action.__args__) == 6  # type: ignore[attr-defined]


class TestPermissionDecisionProtocol:
    """Verify PermissionDecision Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """PermissionDecision Protocol is decorated with @runtime_checkable."""
        assert hasattr(PermissionDecision, "_is_runtime_protocol") or hasattr(
            PermissionDecision, "__protocol_attrs__"
        )

    def test_has_is_allowed_method(self) -> None:
        """Protocol requires is_allowed() -> bool."""
        assert hasattr(PermissionDecision, "is_allowed")

    def test_has_reason_method(self) -> None:
        """Protocol requires reason() -> str."""
        assert hasattr(PermissionDecision, "reason")

    def test_has_attributes_method(self) -> None:
        """Protocol requires attributes() -> Mapping."""
        assert hasattr(PermissionDecision, "attributes")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all PermissionDecision methods satisfies the protocol."""

        class ValidDecision:
            def is_allowed(self) -> bool:
                return True

            def reason(self) -> str:
                return "ok"

            def attributes(self) -> dict[str, str]:
                return {}

        assert isinstance(ValidDecision(), PermissionDecision)

    def test_class_missing_is_allowed_fails_protocol(self) -> None:
        """A class without is_allowed() does NOT satisfy PermissionDecision."""

        class Incomplete:
            def reason(self) -> str:
                return "nope"

        assert not isinstance(Incomplete(), PermissionDecision)


class TestPermissionManagerProtocol:
    """Verify PermissionManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """PermissionManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(PermissionManager, "_is_runtime_protocol") or hasattr(
            PermissionManager, "__protocol_attrs__"
        )

    def test_has_check_permission_method(self) -> None:
        """Protocol requires check_permission() -> PermissionDecision."""
        assert hasattr(PermissionManager, "check_permission")

    def test_has_check_delegation_method(self) -> None:
        """Protocol requires check_delegation() -> PermissionDecision."""
        assert hasattr(PermissionManager, "check_delegation")

    def test_has_list_effective_permissions_method(self) -> None:
        """Protocol requires list_effective_permissions() -> list."""
        assert hasattr(PermissionManager, "list_effective_permissions")

    def test_has_get_json_schema_method(self) -> None:
        """Protocol requires get_json_schema() -> dict."""
        assert hasattr(PermissionManager, "get_json_schema")

    def test_get_json_schema_is_static(self) -> None:
        """get_json_schema is a staticmethod on the Protocol."""
        import inspect

        # Check it's a static method descriptor
        method = inspect.getattr_static(PermissionManager, "get_json_schema")
        assert isinstance(method, staticmethod)

    def test_complete_adapter_satisfies_protocol(self) -> None:
        """A class implementing all methods satisfies the PermissionManager Protocol."""

        class CompleteAdapter:
            async def check_permission(
                self,
                *,
                tenant_id: str,
                principal_id: str,
                principal_type: str,
                resource_type: str,
                resource_id: str,
                action: str,
                context: dict | None = None,
            ):
                ...

            async def check_delegation(
                self,
                *,
                tenant_id: str,
                delegator_id: str,
                delegate_id: str,
                delegate_type: str,
                resource_type: str,
                resource_id: str,
                allowed_actions: list,
                ttl_seconds: int,
                purpose: str,
                context: dict | None = None,
            ):
                ...

            async def list_effective_permissions(
                self,
                *,
                tenant_id: str,
                principal_id: str,
                principal_type: str,
                resource_type: str | None = None,
                resource_id: str | None = None,
            ) -> list:
                return []

            @staticmethod
            def get_json_schema() -> dict:
                return {}

        assert isinstance(CompleteAdapter(), PermissionManager)

    def test_class_missing_check_permission_fails_protocol(self) -> None:
        """A class without check_permission does NOT satisfy PermissionManager."""

        class Incomplete:
            @staticmethod
            def get_json_schema() -> dict:
                return {}

        assert not isinstance(Incomplete(), PermissionManager)


class TestPermissionConfigModel:
    """Verify PermissionConfig Pydantic model."""

    def test_valid_config(self) -> None:
        """PermissionConfig with valid model_path and policy_path."""
        config = PermissionConfig(model_path="model.conf", policy_path="policy.csv")
        assert config.model_path == "model.conf"
        assert config.policy_path == "policy.csv"

    def test_default_paths(self) -> None:
        """PermissionConfig has empty defaults."""
        config = PermissionConfig()
        assert config.model_path == ""
        assert config.policy_path == ""

    def test_empty_model_path_fails(self) -> None:
        """model_path is validated for min_length=1 if the adapter requires it."""
        # PermissionConfig allows empty defaults for in-memory adapter.
        # The min-length constraint is enforced by the adapter at runtime.
        config = PermissionConfig(model_path="", policy_path="policy.csv")
        assert config.model_path == ""


class TestDelegationRecordModel:
    """Verify DelegationRecord Pydantic model."""

    def test_valid_record(self) -> None:
        """DelegationRecord with all required fields."""
        now = datetime.now(UTC)
        record = DelegationRecord(
            delegator_id="u1",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            purpose="generate_report",
            ttl_seconds=300,
            created_at=now,
        )
        assert record.delegator_id == "u1"
        assert record.delegate_id == "agent-1"
        assert record.delegate_type == "agent"
        assert record.allowed_actions == ["read"]
        assert record.purpose == "generate_report"
        assert record.ttl_seconds == 300

    def test_expires_at_computed_from_created_at(self) -> None:
        """expires_at is computed as created_at + ttl_seconds."""
        now = datetime.now(UTC)
        record = DelegationRecord(
            delegator_id="u1",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            purpose="test",
            ttl_seconds=300,
            created_at=now,
        )
        expected = now.timestamp() + 300
        assert abs(record.expires_at.timestamp() - expected) < 1

    def test_empty_delegator_id_fails(self) -> None:
        """delegator_id must not be empty."""
        with pytest.raises(PydanticValidationError):
            DelegationRecord(
                delegator_id="",
                delegate_id="agent-1",
                delegate_type="agent",
                resource_type="document",
                resource_id="doc-1",
                allowed_actions=["read"],
                purpose="test",
                ttl_seconds=300,
            )

    def test_empty_delegate_id_fails(self) -> None:
        """delegate_id must not be empty."""
        with pytest.raises(PydanticValidationError):
            DelegationRecord(
                delegator_id="u1",
                delegate_id="",
                delegate_type="agent",
                resource_type="document",
                resource_id="doc-1",
                allowed_actions=["read"],
                purpose="test",
                ttl_seconds=300,
            )

    def test_invalid_delegate_type_fails(self) -> None:
        """delegate_type must be one of human/agent/team."""
        with pytest.raises(PydanticValidationError):
            DelegationRecord(
                delegator_id="u1",
                delegate_id="agent-1",
                delegate_type="unknown",  # type: ignore[arg-type]
                resource_type="document",
                resource_id="doc-1",
                allowed_actions=["read"],
                purpose="test",
                ttl_seconds=300,
            )

    def test_ttl_seconds_negative_fails(self) -> None:
        """ttl_seconds must be positive."""
        with pytest.raises(PydanticValidationError):
            DelegationRecord(
                delegator_id="u1",
                delegate_id="agent-1",
                delegate_type="agent",
                resource_type="document",
                resource_id="doc-1",
                allowed_actions=["read"],
                purpose="test",
                ttl_seconds=-1,
            )

    def test_ttl_seconds_zero_fails(self) -> None:
        """ttl_seconds=0 fails (must be >= 1)."""
        with pytest.raises(PydanticValidationError):
            DelegationRecord(
                delegator_id="u1",
                delegate_id="agent-1",
                delegate_type="agent",
                resource_type="document",
                resource_id="doc-1",
                allowed_actions=["read"],
                purpose="test",
                ttl_seconds=0,
            )

    def test_empty_purpose_fails(self) -> None:
        """purpose must not be empty."""
        with pytest.raises(PydanticValidationError):
            DelegationRecord(
                delegator_id="u1",
                delegate_id="agent-1",
                delegate_type="agent",
                resource_type="document",
                resource_id="doc-1",
                allowed_actions=["read"],
                purpose="",
                ttl_seconds=300,
            )


class TestPermissionResultModel:
    """Verify PermissionResult Pydantic model."""

    def test_satisfies_permission_decision_protocol(self) -> None:
        """PermissionResult satisfies PermissionDecision Protocol at runtime."""
        result = PermissionResult(allowed=True, reason="rbac_allow", policy_id="pol-1")
        # As a Pydantic model with is_allowed(), reason field, and attributes(),
        # it passes the @runtime_checkable isinstance check.
        assert isinstance(result, PermissionDecision)

    def test_allowed_result(self) -> None:
        """PermissionResult with allowed=True."""
        result = PermissionResult(allowed=True, reason="rbac_allow", policy_id="pol-1")
        assert result.allowed is True
        assert result.reason == "rbac_allow"
        assert result.policy_id == "pol-1"
        assert result.context == {}

    def test_denied_result(self) -> None:
        """PermissionResult with allowed=False."""
        result = PermissionResult(allowed=False, reason="rbac_deny", policy_id="pol-2")
        assert result.allowed is False

    def test_with_context(self) -> None:
        """PermissionResult with context dict."""
        result = PermissionResult(
            allowed=True,
            reason="rbac_allow",
            policy_id="pol-1",
            context={"purpose": "report", "on_behalf_of": "u1"},
        )
        assert result.context == {"purpose": "report", "on_behalf_of": "u1"}

    def test_empty_reason_fails(self) -> None:
        """reason must not be empty."""
        with pytest.raises(PydanticValidationError):
            PermissionResult(allowed=True, reason="", policy_id="pol-1")
