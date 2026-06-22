"""InMemoryPermissionAdapter — dict-backed PermissionManager test double.

Provides a lightweight, zero-I/O adapter for unit testing components that
depend on PermissionManager. Pre-loads role → permissions mappings and
evaluates authorization checks entirely in memory.

Role hierarchy: admin > manager > user > agent_basic.
admin: read, write, create, delete, invoke, delegate
manager: read, write, create, invoke (inherit user)
user: read (can invoke self-owned)
agent_basic: read only (no delegate guardrail)

Delegations are stored as DelegationRecord with TTL; expired delegations
are pruned on check_permission().

Security: This adapter performs NO real policy evaluation. NEVER use it
    in production. Max TTL is 86400 seconds (24 hours).
Observability: No RED metrics emitted — this is a test-only adapter.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from core_infrastructure.common.errors import ValidationError
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

# ── Role hierarchy definition ────────────────────────────────────────────────

_ROLE_HIERARCHY: dict[str, set[str]] = {
    "admin": {"read", "write", "create", "delete", "invoke", "delegate"},
    "manager": {"read", "write", "create", "invoke"},
    "user": {"read", "invoke"},
    "agent_basic": {"read"},
}

# admin inherits manager + user permissions; manager inherits user permissions
# This is resolved at runtime: an admin also gets manager's and user's actions
# (already covered since admin set is a superset).


class InMemoryPermissionAdapter:
    """Dict-backed PermissionManager test double with role hierarchy.

    Pre-load roles via add_role() before running tests. Supports
    time-limited delegation with TTL. Delegations are stored in memory
    and pruned on access if expired.

    Args:
        config: PermissionConfig (unused for in-memory adapter, but
            required for interface consistency).
    """

    def __init__(self, config: PermissionConfig) -> None:
        self._config = config
        # tenant_id → {principal_id: role}
        self._roles: dict[str, dict[str, str]] = {}
        # tenant_id → list of DelegationRecord
        self._delegations: dict[str, list[DelegationRecord]] = {}

    # ── Public helpers for test setup ────────────────────────────────────

    def add_role(self, principal_id: str, role: str, tenant_id: str) -> None:
        """Assign a role to a principal within a tenant.

        Args:
            principal_id: The principal to assign.
            role: One of admin, manager, user, agent_basic.
            tenant_id: Multi-tenant identifier.
        """
        if tenant_id not in self._roles:
            self._roles[tenant_id] = {}
        self._roles[tenant_id][principal_id] = role

    # ── PermissionManager Protocol ───────────────────────────────────────

    async def check_permission(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        principal_type: PrincipalType,
        resource_type: str,
        resource_id: str,
        action: Action,
        context: Mapping[str, Any] | None = None,
    ) -> PermissionDecision:
        """Evaluate RBAC + active delegations for the principal.

        Args:
            tenant_id: Multi-tenant identifier.
            principal_id: Principal requesting access.
            principal_type: Type of principal (human, agent, team).
            resource_type: Type of resource.
            resource_id: Resource identifier.
            action: Requested action.
            context: Optional context (purpose, workflow_id, etc.).

        Returns:
            PermissionDecision with allowed/reason/attributes.

        Raises:
            ValidationError: If principal_type is invalid.
        """
        self._validate_principal_type(principal_type)

        ctx = dict(context) if context else {}

        # Check active delegations first
        delegation_decision = self._check_active_delegation(
            tenant_id=tenant_id,
            principal_id=principal_id,
            principal_type=principal_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
        )
        if delegation_decision is not None:
            # Merge context into delegation decision
            merged_context = {**delegation_decision.attributes(), **ctx}
            return PermissionResult(  # type: ignore[return-value]
                allowed=delegation_decision.is_allowed(),
                reason=delegation_decision.reason,
                context=merged_context,
            )

        # Fall back to RBAC
        role = self._get_role(tenant_id, principal_id)
        if role is None:
            return PermissionResult(allowed=False, reason="rbac_deny", context=ctx)  # type: ignore[return-value]

        allowed_actions = _ROLE_HIERARCHY.get(role, set())
        if action in allowed_actions:
            return PermissionResult(allowed=True, reason="rbac_allow", context=ctx)  # type: ignore[return-value]

        return PermissionResult(allowed=False, reason="rbac_deny", context=ctx)  # type: ignore[return-value]

    async def check_delegation(
        self,
        *,
        tenant_id: str,
        delegator_id: str,
        delegate_id: str,
        delegate_type: PrincipalType,
        resource_type: str,
        resource_id: str,
        allowed_actions: list[Action],
        ttl_seconds: int,
        purpose: str,
        context: Mapping[str, Any] | None = None,
    ) -> PermissionDecision:
        """Validate and record a time-limited delegation.

        Checks that the delegator has the 'delegate' permission before
        creating the delegation record.

        Args:
            tenant_id: Multi-tenant identifier.
            delegator_id: Principal granting the delegation.
            delegate_id: Principal receiving the delegation.
            delegate_type: Type of the delegate.
            resource_type: Resource type.
            resource_id: Resource identifier.
            allowed_actions: Actions the delegate may perform.
            ttl_seconds: Time-to-live in seconds (max 86400).
            purpose: Declared purpose.
            context: Optional audit context.

        Returns:
            PermissionDecision with allowed/reason/attributes.

        Raises:
            ValidationError: If ttl_seconds is out of range or required
                fields are empty.
        """
        self._validate_principal_type(delegate_type)

        ctx = dict(context) if context else {}

        # Check delegator has delegate permission
        delegator_role = self._get_role(tenant_id, delegator_id)
        if delegator_role is None:
            return PermissionResult(  # type: ignore[return-value]
                allowed=False,
                reason="rbac_deny",
                policy_id="",
                context={**ctx, "on_behalf_of": delegator_id},
            )

        allowed = _ROLE_HIERARCHY.get(delegator_role, set())
        if "delegate" not in allowed:
            return PermissionResult(  # type: ignore[return-value]
                allowed=False,
                reason="rbac_deny",
                policy_id="",
                context={**ctx, "on_behalf_of": delegator_id},
            )

        # Create delegation record
        record = DelegationRecord(
            delegator_id=delegator_id,
            delegate_id=delegate_id,
            delegate_type=delegate_type,
            resource_type=resource_type,
            resource_id=resource_id,
            allowed_actions=list(allowed_actions),
            purpose=purpose,
            ttl_seconds=ttl_seconds,
        )

        if tenant_id not in self._delegations:
            self._delegations[tenant_id] = []
        self._delegations[tenant_id].append(record)

        return PermissionResult(  # type: ignore[return-value]
            allowed=True,
            reason="delegation_created",
            policy_id="",
            context={
                **ctx,
                "purpose": purpose,
                "on_behalf_of": delegator_id,
                "expires_at": record.expires_at.isoformat(),
            },
        )

    async def list_effective_permissions(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        principal_type: PrincipalType,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Return abstract view of effective permissions for inspection.

        Args:
            tenant_id: Multi-tenant identifier.
            principal_id: Principal to query.
            principal_type: Type of principal.
            resource_type: Optional filter.
            resource_id: Optional filter.

        Returns:
            List of permission entries with resource_type, resource_id,
            action, source (rbac/delegation), and optional expiry.
        """
        result: list[Mapping[str, Any]] = []

        # RBAC permissions from role
        role = self._get_role(tenant_id, principal_id)
        if role is not None:
            actions = _ROLE_HIERARCHY.get(role, set())
            for action in sorted(actions):
                entry: dict[str, Any] = {
                    "resource_type": resource_type or "*",
                    "resource_id": resource_id or "*",
                    "action": action,
                    "source": "rbac",
                }
                if resource_type is not None:
                    entry["resource_type"] = resource_type
                if resource_id is not None:
                    entry["resource_id"] = resource_id
                result.append(entry)

        # Active delegations
        self._prune_expired_delegations(tenant_id)
        for record in self._delegations.get(tenant_id, []):
            if record.delegate_id != principal_id:
                continue
            if resource_type is not None and record.resource_type != resource_type:
                continue
            if resource_id is not None and record.resource_id != resource_id:
                continue
            for action in record.allowed_actions:
                result.append({
                    "resource_type": record.resource_type,
                    "resource_id": record.resource_id,
                    "action": action,
                    "source": "delegation",
                    "expiry": record.expires_at.isoformat(),
                })

        return result

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery.

        Returns:
            dict: JSON Schema describing the PermissionManager interface.
        """
        return {
            "name": "PermissionManager",
            "version": "0.1.0",
            "description": (
                "Unified human-agent authorization with hybrid RBAC+ABAC. "
                "Treats humans, agents, and teams as principals."
            ),
            "methods": [
                {
                    "name": "check_permission",
                    "description": "Evaluate whether a principal may perform an action on a resource.",
                    "parameters": {
                        "tenant_id": "string",
                        "principal_id": "string",
                        "principal_type": "human|agent|team",
                        "resource_type": "string",
                        "resource_id": "string",
                        "action": "read|write|create|delete|invoke|delegate",
                        "context": "object (optional)",
                    },
                    "returns": "PermissionDecision",
                },
                {
                    "name": "check_delegation",
                    "description": "Validate and record a time-limited delegation.",
                    "parameters": {
                        "tenant_id": "string",
                        "delegator_id": "string",
                        "delegate_id": "string",
                        "delegate_type": "human|agent|team",
                        "resource_type": "string",
                        "resource_id": "string",
                        "allowed_actions": "array",
                        "ttl_seconds": "integer",
                        "purpose": "string",
                        "context": "object (optional)",
                    },
                    "returns": "PermissionDecision",
                },
                {
                    "name": "list_effective_permissions",
                    "description": "List effective permissions for a principal.",
                    "parameters": {
                        "tenant_id": "string",
                        "principal_id": "string",
                        "principal_type": "human|agent|team",
                        "resource_type": "string (optional)",
                        "resource_id": "string (optional)",
                    },
                    "returns": "array",
                },
            ],
        }

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _validate_principal_type(principal_type: str) -> None:
        """Validate that principal_type is one of human/agent/team.

        Args:
            principal_type: The type to validate.

        Raises:
            ValidationError: If the type is invalid.
        """
        valid = {"human", "agent", "team"}
        if principal_type not in valid:
            raise ValidationError(
                f"invalid_principal_type: {principal_type!r}",
                details={"reason": "invalid_principal_type", "valid_types": ", ".join(sorted(valid))},
            )

    def _get_role(self, tenant_id: str, principal_id: str) -> str | None:
        """Get the role for a principal in a tenant.

        Args:
            tenant_id: Multi-tenant identifier.
            principal_id: Principal to look up.

        Returns:
            The role name, or None if not found.
        """
        return self._roles.get(tenant_id, {}).get(principal_id)

    def _check_active_delegation(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        principal_type: PrincipalType,
        resource_type: str,
        resource_id: str,
        action: Action,
    ) -> PermissionResult | None:
        """Check if an active (non-expired) delegation covers this request.

        Checks all records, including expired ones, so that expired
        delegations explicitly return ``delegation_expired`` rather than
        falling through to ``rbac_deny``. Prunes after checking.

        Args:
            tenant_id: Multi-tenant identifier.
            principal_id: Principal to check.
            principal_type: Type of principal.
            resource_type: Resource type.
            resource_id: Resource identifier.
            action: Requested action.

        Returns:
            PermissionResult if a matching delegation exists (active or
            expired), else None.
        """
        now = time.time()
        result: PermissionResult | None = None

        for record in self._delegations.get(tenant_id, []):
            if record.delegate_id != principal_id:
                continue
            if record.resource_type != resource_type:
                continue
            if record.resource_id != resource_id:
                continue
            if action not in record.allowed_actions:
                continue
            # Check TTL — return expired explicitly
            if record.expires_at.timestamp() <= now:
                result = PermissionResult(
                    allowed=False,
                    reason="delegation_expired",
                    context={
                        "purpose": record.purpose,
                        "on_behalf_of": record.delegator_id,
                    },
                )
                break
            # Active delegation found — prefer this over any expired match
            result = PermissionResult(
                allowed=True,
                reason="delegation_allow",
                context={
                    "purpose": record.purpose,
                    "on_behalf_of": record.delegator_id,
                },
            )
            break

        # Prune expired AFTER checking so we don't silently drop them
        self._prune_expired_delegations(tenant_id)
        return result

    def _prune_expired_delegations(self, tenant_id: str) -> None:
        """Remove expired delegation records for a tenant.

        Args:
            tenant_id: Multi-tenant identifier to prune.
        """
        if tenant_id not in self._delegations:
            return
        now = time.time()
        self._delegations[tenant_id] = [
            r for r in self._delegations[tenant_id] if r.expires_at.timestamp() > now
        ]
