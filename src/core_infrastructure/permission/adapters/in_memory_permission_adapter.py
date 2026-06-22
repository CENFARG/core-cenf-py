"""InMemoryPermissionAdapter — dict-backed PermissionManager test double.

Provides a lightweight, zero-I/O adapter for unit testing components that
depend on PermissionManager. Pre-loads role → permissions mappings and
evaluates authorization checks entirely in memory.

Role hierarchy: admin > manager > user > agent_basic.
admin: read, write, create, delete, invoke, delegate
manager: read, write, create, invoke (inherit user)
user: read (can invoke self-owned)
agent_basic: read only (no delegate guardrail)

Security: This adapter performs NO real policy evaluation. NEVER use it
    in production. Max TTL is 86400 seconds (24 hours).
Observability: No RED metrics emitted — this is a test-only adapter.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core_infrastructure.permission.adapters.in_memory_permission_delegation import (
    list_effective_permissions,
    perform_delegation,
)
from core_infrastructure.permission.adapters.in_memory_permission_helpers import (
    ROLE_HIERARCHY,
    check_active_delegation,
    get_json_schema,
    get_role,
    prune_expired_delegations,
    validate_principal_type,
)
from core_infrastructure.permission.models import (
    DelegationRecord,
    PermissionConfig,
    PermissionResult,
)
from core_infrastructure.permission.ports import (
    Action,
    PermissionDecision,
    PrincipalType,
)

# Backward-compatible alias
_ROLE_HIERARCHY: dict[str, set[str]] = ROLE_HIERARCHY


class InMemoryPermissionAdapter:
    """Dict-backed PermissionManager test double with role hierarchy."""

    def __init__(self, config: PermissionConfig) -> None:
        self._config = config
        self._roles: dict[str, dict[str, str]] = {}
        self._delegations: dict[str, list[DelegationRecord]] = {}

    def add_role(self, principal_id: str, role: str, tenant_id: str) -> None:
        """Assign a role to a principal within a tenant."""
        if tenant_id not in self._roles:
            self._roles[tenant_id] = {}
        self._roles[tenant_id][principal_id] = role

    # ── PermissionManager Protocol ───────────────────────────────────────

    async def check_permission(
        self, *, tenant_id: str, principal_id: str, principal_type: PrincipalType,
        resource_type: str, resource_id: str, action: Action,
        context: Mapping[str, Any] | None = None,
    ) -> PermissionDecision:
        """Evaluate RBAC + active delegations for the principal."""
        validate_principal_type(principal_type)
        ctx = dict(context) if context else {}

        delegation_decision = check_active_delegation(
            delegations=self._delegations, tenant_id=tenant_id,
            principal_id=principal_id, principal_type=principal_type,
            resource_type=resource_type, resource_id=resource_id, action=action,
        )
        if delegation_decision is not None:
            merged_context = {**delegation_decision.attributes(), **ctx}
            return PermissionResult(  # type: ignore[return-value]
                allowed=delegation_decision.is_allowed(),
                reason=delegation_decision.reason, context=merged_context,
            )

        role = get_role(self._roles, tenant_id, principal_id)
        if role is None:
            return PermissionResult(allowed=False, reason="rbac_deny", context=ctx)  # type: ignore[return-value]

        allowed_actions = ROLE_HIERARCHY.get(role, set())
        if action in allowed_actions:
            return PermissionResult(allowed=True, reason="rbac_allow", context=ctx)  # type: ignore[return-value]
        return PermissionResult(allowed=False, reason="rbac_deny", context=ctx)  # type: ignore[return-value]

    async def check_delegation(
        self, *, tenant_id: str, delegator_id: str, delegate_id: str,
        delegate_type: PrincipalType, resource_type: str, resource_id: str,
        allowed_actions: list[Action], ttl_seconds: int, purpose: str,
        context: Mapping[str, Any] | None = None,
    ) -> PermissionDecision:
        """Validate and record a time-limited delegation (delegates to helpers)."""
        return await perform_delegation(
            roles=self._roles, delegations=self._delegations,
            tenant_id=tenant_id, delegator_id=delegator_id,
            delegate_id=delegate_id, delegate_type=delegate_type,
            resource_type=resource_type, resource_id=resource_id,
            allowed_actions=allowed_actions, ttl_seconds=ttl_seconds,
            purpose=purpose, context=context,
        )

    async def list_effective_permissions(
        self, *, tenant_id: str, principal_id: str, principal_type: PrincipalType,
        resource_type: str | None = None, resource_id: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Return abstract view of effective permissions (delegates to helpers)."""
        return list_effective_permissions(
            roles=self._roles, delegations=self._delegations,
            tenant_id=tenant_id, principal_id=principal_id,
            principal_type=principal_type, resource_type=resource_type,
            resource_id=resource_id,
        )

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract (delegates to helpers)."""
        return get_json_schema()

    # ── Backward-compatible wrappers ────────────────────────────────────

    @staticmethod
    def _validate_principal_type(principal_type: str) -> None:
        validate_principal_type(principal_type)

    def _get_role(self, tenant_id: str, principal_id: str) -> str | None:
        return get_role(self._roles, tenant_id, principal_id)

    def _check_active_delegation(
        self, *, tenant_id: str, principal_id: str, principal_type: PrincipalType,
        resource_type: str, resource_id: str, action: Action,
    ) -> PermissionResult | None:
        return check_active_delegation(
            delegations=self._delegations, tenant_id=tenant_id,
            principal_id=principal_id, principal_type=principal_type,
            resource_type=resource_type, resource_id=resource_id, action=action,
        )

    def _prune_expired_delegations(self, tenant_id: str) -> None:
        prune_expired_delegations(self._delegations, tenant_id)
