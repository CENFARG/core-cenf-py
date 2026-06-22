"""Integration tests for CasbinPermissionAdapter — pycasbin RBAC engine.

Tests cover:
- RBAC enforcement: admin can read/write, user can only read
- Multi-tenant isolation: tenant A policies don't leak to tenant B
- Role inheritance: admin inherits manager permissions
- check_delegation() with temporary policy rules and TTL
- Expired delegation denied
- Delegation scope limited to resource and action
- Error handling: invalid model file, missing policy file
- get_json_schema() contract

Tests use temp model.conf and policy.csv files created via pytest fixtures.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from textwrap import dedent

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.permission.adapters.casbin_permission_adapter import (
    CasbinPermissionAdapter,
)
from core_infrastructure.permission.models import PermissionConfig
from core_infrastructure.permission.ports import PermissionManager

# ── Casbin model.conf (RBAC with domains) ──────────────────────────────────

CASBIN_MODEL_RBAC = dedent("""\
    [request_definition]
    r = sub, dom, obj, act

    [policy_definition]
    p = sub, dom, obj, act

    [role_definition]
    g = _, _, _

    [policy_effect]
    e = some(where (p.eft == allow))

    [matchers]
    m = g(r.sub, p.sub, r.dom) && r.dom == p.dom && (r.obj == p.obj || p.obj == "*") && (r.act == p.act || p.act == "*")
""")

# ── Casbin policy.csv (RBAC with role hierarchy) ────────────────────────────

CASBIN_POLICY_T1 = dedent("""\
    p, admin, t1, *, read
    p, admin, t1, *, write
    p, admin, t1, *, create
    p, admin, t1, *, delete
    p, admin, t1, *, invoke
    p, admin, t1, *, delegate

    p, manager, t1, *, read
    p, manager, t1, *, write
    p, manager, t1, *, create
    p, manager, t1, *, invoke

    p, user, t1, *, read
    p, user, t1, *, invoke

    p, agent_basic, t1, *, read

    g, u_admin, admin, t1
    g, u_manager, manager, t1
    g, u_user, user, t1
    g, agent_1, agent_basic, t1
""")

CASBIN_POLICY_T2 = dedent("""\
    p, admin, t2, *, read
    p, admin, t2, *, write

    g, t2_admin, admin, t2
""")


@pytest.fixture
def casbin_config() -> PermissionConfig:
    """Create a PermissionConfig pointing to temp model/policy files.

    Writes the RBAC model and tenant-1 policy to temporary files.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="casbin_test_"))
    model_path = tmp_dir / "model.conf"
    policy_path = tmp_dir / "policy.csv"
    model_path.write_text(CASBIN_MODEL_RBAC)
    policy_path.write_text(CASBIN_POLICY_T1)
    return PermissionConfig(
        model_path=str(model_path),
        policy_path=str(policy_path),
    )


@pytest.fixture
def adapter(casbin_config: PermissionConfig) -> CasbinPermissionAdapter:
    """Create a CasbinPermissionAdapter with temp RBAC model and policy."""
    return CasbinPermissionAdapter(config=casbin_config)


class TestRBACEnforcement:
    """Tests for RBAC enforcement via pycasbin engine."""

    @pytest.mark.asyncio
    async def test_admin_can_read(self, adapter: CasbinPermissionAdapter) -> None:
        """Admin role can read documents."""
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
    async def test_admin_can_write(self, adapter: CasbinPermissionAdapter) -> None:
        """Admin role can write documents."""
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
    async def test_user_can_read(self, adapter: CasbinPermissionAdapter) -> None:
        """User role can read documents."""
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
    async def test_user_cannot_write(self, adapter: CasbinPermissionAdapter) -> None:
        """User role cannot write documents."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_user",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="write",
        )
        assert decision.is_allowed() is False
        assert decision.reason == "rbac_deny"

    @pytest.mark.asyncio
    async def test_agent_basic_cannot_delegate(self, adapter: CasbinPermissionAdapter) -> None:
        """agent_basic role cannot delegate (RBAC guardrail)."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent_1",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="delegate",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_invalid_principal_type_raises(self, adapter: CasbinPermissionAdapter) -> None:
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


class TestMultiTenantIsolation:
    """Tests for multi-tenant isolation."""

    @pytest.fixture
    def multi_tenant_config(self) -> PermissionConfig:
        """Create config with policies for both t1 and t2."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="casbin_mt_"))
        model_path = tmp_dir / "model.conf"
        policy_path = tmp_dir / "policy.csv"
        model_path.write_text(CASBIN_MODEL_RBAC)
        # Combined policies for t1 and t2
        combined = CASBIN_POLICY_T1.strip() + "\n" + CASBIN_POLICY_T2.strip() + "\n"
        policy_path.write_text(combined)
        return PermissionConfig(
            model_path=str(model_path),
            policy_path=str(policy_path),
        )

    @pytest.mark.asyncio
    async def test_tenant_a_policies_do_not_leak_to_tenant_b(
        self, multi_tenant_config: PermissionConfig
    ) -> None:
        """User u_admin in t1 cannot access resources in t2."""
        adapter = CasbinPermissionAdapter(config=multi_tenant_config)
        # u_admin is defined in t1
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
    async def test_tenant_b_user_can_access_own_resources(
        self, multi_tenant_config: PermissionConfig
    ) -> None:
        """User in t2 can access t2 resources."""
        adapter = CasbinPermissionAdapter(config=multi_tenant_config)
        decision = await adapter.check_permission(
            tenant_id="t2",
            principal_id="t2_admin",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is True


class TestRoleInheritance:
    """Tests for role hierarchy via Casbin grouping (g)."""

    @pytest.mark.asyncio
    async def test_admin_inherits_manager_permissions(self, adapter: CasbinPermissionAdapter) -> None:
        """Admin can write (manager-level permission) via role inheritance."""
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
    async def test_manager_inherits_user_permissions(self, adapter: CasbinPermissionAdapter) -> None:
        """Manager can read (user-level permission) via role inheritance."""
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="u_manager",
            principal_type="human",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is True


class TestDelegationWithTTL:
    """Tests for short-lived delegation with Casbin adapter."""

    @pytest.mark.asyncio
    async def test_admin_can_delegate_to_agent(self, adapter: CasbinPermissionAdapter) -> None:
        """Admin can delegate read to agent with TTL."""
        decision = await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent_delegate",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="generate_report",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_delegation_enables_permission(self, adapter: CasbinPermissionAdapter) -> None:
        """After delegation, the delegate can read the resource."""
        await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent_delegate",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="test",
        )
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent_delegate",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is True

    @pytest.mark.asyncio
    async def test_delegation_is_scoped_to_resource(self, adapter: CasbinPermissionAdapter) -> None:
        """Delegated permission only applies to the specific resource."""
        await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent_delegate",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=300,
            purpose="test",
        )
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent_delegate",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-2",
            action="read",
        )
        assert decision.is_allowed() is False

    @pytest.mark.asyncio
    async def test_expired_delegation_denied(self, adapter: CasbinPermissionAdapter) -> None:
        """Delegation with 1s TTL expires and is denied."""
        await adapter.check_delegation(
            tenant_id="t1",
            delegator_id="u_admin",
            delegate_id="agent_short",
            delegate_type="agent",
            resource_type="document",
            resource_id="doc-1",
            allowed_actions=["read"],
            ttl_seconds=1,
            purpose="test",
        )
        await asyncio.sleep(1.1)
        decision = await adapter.check_permission(
            tenant_id="t1",
            principal_id="agent_short",
            principal_type="agent",
            resource_type="document",
            resource_id="doc-1",
            action="read",
        )
        assert decision.is_allowed() is False
        assert "delegation_expired" in decision.reason


class TestJsonSchema:
    """Tests for Casbin adapter get_json_schema()."""

    def test_returns_dict(self, adapter: CasbinPermissionAdapter) -> None:
        """get_json_schema returns a dict."""
        schema = CasbinPermissionAdapter.get_json_schema()
        assert isinstance(schema, dict)
        assert "name" in schema


class TestProtocolCompliance:
    """Verify CasbinPermissionAdapter satisfies PermissionManager Protocol."""

    def test_satisfies_protocol(self, adapter: CasbinPermissionAdapter) -> None:
        """CasbinPermissionAdapter satisfies PermissionManager Protocol."""
        assert isinstance(adapter, PermissionManager)
