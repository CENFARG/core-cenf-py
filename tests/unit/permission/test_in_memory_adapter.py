"""Unit tests for InMemoryPermissionAdapter — dict-backed test double.

Tests cover:
- check_permission() RBAC evaluation with role hierarchy
- Role hierarchy: admin > manager > user > agent_basic
- Deny by default for unknown principals
- check_delegation() with TTL
- list_effective_permissions()
- get_json_schema()
- ValidationError for invalid principal_type

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.permission.adapters.in_memory_permission_adapter import (
    InMemoryPermissionAdapter,
)
from core_infrastructure.permission.models import PermissionConfig
from core_infrastructure.permission.ports import PermissionDecision, PermissionManager


class TestCheckPermission:
    """Tests for check_permission() RBAC evaluation."""

    @pytest.fixture
    def adapter(self) -> InMemoryPermissionAdapter:
        """Create a fresh adapter with pre-loaded roles."""
        config = PermissionConfig()
        adapter = InMemoryPermissionAdapter(config=config)
        # Pre-load roles for testing
        adapter.add_role("u_admin", "admin", "t1")
        adapter.add_role("u_manager", "manager", "t1")
        adapter.add_role("u_user", "user", "t1")
        adapter.add_role("agent_1", "agent_basic", "t1")
        return adapter

    @pytest.mark.asyncio
    async def test_admin_can_read(self, adapter: InMemoryPermissionAdapter) -> None:
        """Admin role can read any resource."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is True
        assert decision.reason == "rbac_allow"

    @pytest.mark.asyncio
    async def test_admin_can_write(self, adapter: InMemoryPermissionAdapter) -> None:
        """Admin role can write any resource."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="write",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_admin_can_delete(self, adapter: InMemoryPermissionAdapter) -> None:
        """Admin role can delete any resource."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="delete",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_admin_can_delegate(self, adapter: InMemoryPermissionAdapter) -> None:
        """Admin role can delegate permissions."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="delegate",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_manager_can_read(self, adapter: InMemoryPermissionAdapter) -> None:
        """Manager role can read resources."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_manager",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_manager_can_write(self, adapter: InMemoryPermissionAdapter) -> None:
        """Manager role can write resources."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_manager",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="write",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_manager_cannot_delete(self, adapter: InMemoryPermissionAdapter) -> None:
        """Manager role cannot delete — only admin can."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_manager",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="delete",
        )
        assert decision.is_allowed() is False
        assert decision.reason == "rbac_deny"

    @pytest.mark.asyncio
    async def test_manager_cannot_delegate(self, adapter: InMemoryPermissionAdapter) -> None:
        """Manager role cannot delegate — only admin can."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_manager",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="delegate",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_user_can_read(self, adapter: InMemoryPermissionAdapter) -> None:
        """User role can read resources."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_user",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_user_cannot_write(self, adapter: InMemoryPermissionAdapter) -> None:
        """User role cannot write — needs manager+."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_user",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="write",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_agent_basic_can_read(self, adapter: InMemoryPermissionAdapter) -> None:
        """agent_basic role can read resources."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent_1",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_agent_basic_cannot_write(self, adapter: InMemoryPermissionAdapter) -> None:
        """agent_basic role cannot write."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent_1",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="write",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_agent_basic_cannot_delegate(self, adapter: InMemoryPermissionAdapter) -> None:
        """agent_basic role cannot delegate per RBAC guardrail."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent_1",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="delegate",
        )
        assert decision.is_allowed() is False
        assert decision.reason == "rbac_deny"

    @pytest.mark.asyncio
    async def test_admin_inherits_manager_permissions(self, adapter: InMemoryPermissionAdapter) -> None:
        """Admin inherits all manager permissions (can read and write)."""
        # Admin already tested to read/write — this confirms inheritance via hierarchy.
        can_read = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        can_write = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="write",
        )
        assert can_read.is_allowed() is True
        assert can_write.is_allowed() is True

    @pytest.mark.asyncio
    async def test_manager_inherits_user_permissions(self, adapter: InMemoryPermissionAdapter) -> None:
        """Manager inherits user permissions (can read)."""
        can_read = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_manager",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert can_read.is_allowed() is True

    @pytest.mark.asyncio
    async def test_unknown_principal_denied(self, adapter: InMemoryPermissionAdapter) -> None:
        """Unknown principal with no role assignment is denied."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="unknown_user",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is False
        assert decision.reason == "rbac_deny"

    @pytest.mark.asyncio
    async def test_invalid_principal_type_raises_validation_error(self, adapter: InMemoryPermissionAdapter) -> None:
        """Invalid principal_type raises ValidationError."""
        with pytest.raises(ValidationError, match="invalid_principal_type"):
            await adapter.check_permission(
                tenant_id="t1",
                principal_id="u1",
                principal_type="unknown",  # type: ignore[arg-type]
                resource_type="document",
                resource_id="doc-1",
                action="read",
            )

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, adapter: InMemoryPermissionAdapter) -> None:
        """Principal in tenant A cannot access resources in tenant B."""
        # u_admin is in t1 only
        decision = await adapter.check_permission(
            tenant_id="t2",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_context_is_passed_through_to_decision(self, adapter: InMemoryPermissionAdapter) -> None:
        """Context dict is included in decision attributes."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
            context={"purpose": "test", "workflow_id": "wf-1"},
        )
        assert decision.is_allowed() is True
        attrs = decision.attributes()
        assert attrs.get("purpose") == "test"
        assert attrs.get("workflow_id") == "wf-1"


class TestDelegation:
    """Tests for check_delegation() TTL-based delegation."""

    @pytest.fixture
    def adapter(self) -> InMemoryPermissionAdapter:
        """Adapter with admin user for delegation testing."""
        config = PermissionConfig()
        adapter = InMemoryPermissionAdapter(config=config)
        adapter.add_role("u_admin", "admin", "t1")
        return adapter

    @pytest.mark.asyncio
    async def test_admin_can_delegate_to_agent(self, adapter: InMemoryPermissionAdapter) -> None:
        """Admin can delegate read permission to an agent."""
        decision = await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="generate_report",
        )
        assert decision.is_allowed() is True
        assert decision.reason == "delegation_created"

    @pytest.mark.asyncio
    async def test_delegation_enables_permission_for_delegate(self, adapter: InMemoryPermissionAdapter) -> None:
        """After delegation, the delegate can perform the delegated action."""
        await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="generate_report",
        )
        # Now agent-1 should be able to read doc-1
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent-1",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is True
        assert "delegation" in decision.reason

    @pytest.mark.asyncio
    async def test_delegation_is_scoped_to_resource(self, adapter: InMemoryPermissionAdapter) -> None:
        """Delegation is scoped to the specific resource and action."""
        await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="test",
        )
        # Different resource should be denied
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent-1",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-2",
            action="read",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_delegation_is_scoped_to_action(self, adapter: InMemoryPermissionAdapter) -> None:
        """Delegation only allows the specified actions."""
        await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="test",
        )
        # Write action should still be denied
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent-1",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="write",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_expired_delegation_is_denied(self, adapter: InMemoryPermissionAdapter) -> None:
        """Delegation with a short TTL expires and then is denied."""
        await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=1,
            purpose="test",
        )
        # Wait for expiry
        await asyncio.sleep(1.1)
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent-1",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is False
        assert decision.reason == "delegation_expired"

    @pytest.mark.asyncio
    async def test_non_admin_cannot_delegate(self, adapter: InMemoryPermissionAdapter) -> None:
        """A user without delegate permission cannot delegate."""
        adapter.add_role("u_user", "user", "t1")
        decision = await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_user",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="test",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_delegation_with_purpose_appears_in_attributes(self, adapter: InMemoryPermissionAdapter) -> None:
        """Delegation purpose and on_behalf_of appear in decision attributes."""
        decision = await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent-1",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="generate_report",
        )
        attrs = decision.attributes()
        assert attrs.get("purpose") == "generate_report"
        assert attrs.get("on_behalf_of") == "u_admin"


class TestListEffectivePermissions:
    """Tests for list_effective_permissions()."""

    @pytest.fixture
    def adapter(self) -> InMemoryPermissionAdapter:
        """Adapter with roles and a delegation."""
        config = PermissionConfig()
        adapter = InMemoryPermissionAdapter(config=config)
        adapter.add_role("u_admin", "admin", "t1")
        return adapter

    @pytest.mark.asyncio
    async def test_returns_list(self, adapter: InMemoryPermissionAdapter) -> None:
        """list_effective_permissions returns a list."""
        perms = await adapter.list_effective_permissions(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
        )
        assert isinstance(perms, list)

    @pytest.mark.asyncio
    async def test_returns_entries_with_required_keys(self, adapter: InMemoryPermissionAdapter) -> None:
        """Each entry has resource_type, resource_id, action, source keys."""
        perms = await adapter.list_effective_permissions(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
        )
        assert len(perms) > 0
        for entry in perms:
            assert "resource_type" in entry
            assert "resource_id" in entry
            assert "action" in entry
            assert "source" in entry

    @pytest.mark.asyncio
    async def test_filter_by_resource_type(self, adapter: InMemoryPermissionAdapter) -> None:
        """Filter returns only matching resource_type."""
        perms = await adapter.list_effective_permissions(
            tenant_id="t1",
            principal_id="u_admin",
            principal_type="human",
            resource_type="document",
        )
        for entry in perms:
            assert entry["resource_type"] == "document"

    @pytest.mark.asyncio
    async def test_unknown_principal_returns_empty(self, adapter: InMemoryPermissionAdapter) -> None:
        """Unknown principal returns empty list."""
        perms = await adapter.list_effective_permissions(
            tenant_id="t1",
            principal_id="nobody",
            principal_type="human",
        )
        assert perms == []


class TestGetJsonSchema:
    """Tests for get_json_schema()."""

    def test_returns_dict(self) -> None:
        """get_json_schema returns a dict."""
        schema = InMemoryPermissionAdapter.get_json_schema()
        assert isinstance(schema, dict)

    def test_contains_manager_name(self) -> None:
        """Schema includes the manager name."""
        schema = InMemoryPermissionAdapter.get_json_schema()
        assert "name" in schema
        assert schema["name"] == "PermissionManager"

    def test_contains_methods(self) -> None:
        """Schema includes method descriptions."""
        schema = InMemoryPermissionAdapter.get_json_schema()
        assert "methods" in schema
        assert isinstance(schema["methods"], list)
        assert len(schema["methods"]) > 0


class TestProtocolCompliance:
    """Verify InMemoryPermissionAdapter satisfies PermissionManager Protocol."""

    def test_satisfies_protocol(self) -> None:
        """InMemoryPermissionAdapter satisfies PermissionManager Protocol."""
        config = PermissionConfig()
        adapter = InMemoryPermissionAdapter(config=config)
        assert isinstance(adapter, PermissionManager)

    def test_returns_permission_decision(self) -> None:
        """Adapter returns objects that satisfy PermissionDecision."""
        config = PermissionConfig()
        adapter = InMemoryPermissionAdapter(config=config)
        adapter.add_role("u1", "admin", "t1")

        import asyncio

        result = asyncio.run(
            adapter.check_permission(
                tenant_id="t1",
                principal_id="u1",
                principal_type="human",
                resource_type="doc",
                resource_id="d1",
                action="read",
            )
        )
        assert isinstance(result, PermissionDecision)
        assert result.is_allowed() is True
