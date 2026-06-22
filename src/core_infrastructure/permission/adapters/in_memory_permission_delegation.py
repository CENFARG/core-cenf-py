"""InMemoryPermission delegation helpers — delegation creation and permission listing.

Extracted from ``in_memory_permission_helpers.py`` to comply with the 250-line
CENF rule. Contains delegation validation, record creation with TTL, and
effective permission listing with role hierarchy resolution.

What: Second-level extraction of delegation/permission-listing functions.
Why: 250-line CENF rule compliance for in_memory_permission_helpers.py.
Where: src/core_infrastructure/permission/adapters/in_memory_permission_delegation.py

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core_infrastructure.permission.adapters.in_memory_permission_helpers import (
    ROLE_HIERARCHY,
    get_role,
    prune_expired_delegations,
    validate_principal_type,
)
from core_infrastructure.permission.models import (
    DelegationRecord,
    PermissionResult,
)
from core_infrastructure.permission.ports import (
    Action,
    PermissionDecision,
    PrincipalType,
)


async def perform_delegation(
    *,
    roles: dict[str, dict[str, str]],
    delegations: dict[str, list[DelegationRecord]],
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
    """
    validate_principal_type(delegate_type)
    ctx = dict(context) if context else {}

    delegator_role = get_role(roles, tenant_id, delegator_id)
    if delegator_role is None:
        return PermissionResult(  # type: ignore[return-value]
            allowed=False, reason="rbac_deny", policy_id="",
            context={**ctx, "on_behalf_of": delegator_id},
        )

    allowed = ROLE_HIERARCHY.get(delegator_role, set())
    if "delegate" not in allowed:
        return PermissionResult(  # type: ignore[return-value]
            allowed=False, reason="rbac_deny", policy_id="",
            context={**ctx, "on_behalf_of": delegator_id},
        )

    record = DelegationRecord(
        delegator_id=delegator_id, delegate_id=delegate_id,
        delegate_type=delegate_type, resource_type=resource_type,
        resource_id=resource_id, allowed_actions=list(allowed_actions),
        purpose=purpose, ttl_seconds=ttl_seconds,
    )

    if tenant_id not in delegations:
        delegations[tenant_id] = []
    delegations[tenant_id].append(record)

    return PermissionResult(  # type: ignore[return-value]
        allowed=True, reason="delegation_created", policy_id="",
        context={**ctx, "purpose": purpose, "on_behalf_of": delegator_id,
                 "expires_at": record.expires_at.isoformat()},
    )


def list_effective_permissions(
    *,
    roles: dict[str, dict[str, str]],
    delegations: dict[str, list[DelegationRecord]],
    tenant_id: str,
    principal_id: str,
    principal_type: PrincipalType,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> list[Mapping[str, Any]]:
    """Return abstract view of effective permissions for inspection."""
    result: list[Mapping[str, Any]] = []

    role = get_role(roles, tenant_id, principal_id)
    if role is not None:
        actions = ROLE_HIERARCHY.get(role, set())
        for action in sorted(actions):
            entry: dict[str, Any] = {
                "resource_type": resource_type or "*",
                "resource_id": resource_id or "*",
                "action": action, "source": "rbac",
            }
            if resource_type is not None:
                entry["resource_type"] = resource_type
            if resource_id is not None:
                entry["resource_id"] = resource_id
            result.append(entry)

    prune_expired_delegations(delegations, tenant_id)
    for record in delegations.get(tenant_id, []):
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
                "action": action, "source": "delegation",
                "expiry": record.expires_at.isoformat(),
            })

    return result
