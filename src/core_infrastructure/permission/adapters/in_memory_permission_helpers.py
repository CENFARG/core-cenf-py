"""InMemoryPermissionAdapter helpers — role hierarchy, delegation validation.

Extracted from ``in_memory_permission_adapter.py`` to comply with the 250-line
CENF rule. Contains the role hierarchy definition, role resolution, delegation
matching, expiration pruning, and JSON schema generation. Larger delegation/
permission-listing functions live in ``in_memory_permission_delegation.py``.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time
from typing import Any

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.permission.models import (
    DelegationRecord,
    PermissionResult,
)
from core_infrastructure.permission.ports import (
    Action,
    PrincipalType,
)

ROLE_HIERARCHY: dict[str, set[str]] = {
    "admin": {"read", "write", "create", "delete", "invoke", "delegate"},
    "manager": {"read", "write", "create", "invoke"},
    "user": {"read", "invoke"},
    "agent_basic": {"read"},
}


def validate_principal_type(principal_type: str) -> None:
    """Validate that principal_type is one of human/agent/team."""
    valid = {"human", "agent", "team"}
    if principal_type not in valid:
        raise ValidationError(
            f"invalid_principal_type: {principal_type!r}",
            details={"reason": "invalid_principal_type",
                     "valid_types": ", ".join(sorted(valid))},
        )


def get_role(
    roles: dict[str, dict[str, str]], tenant_id: str, principal_id: str
) -> str | None:
    """Get the role for a principal in a tenant."""
    return roles.get(tenant_id, {}).get(principal_id)


def check_active_delegation(
    *,
    delegations: dict[str, list[DelegationRecord]],
    tenant_id: str,
    principal_id: str,
    principal_type: PrincipalType,
    resource_type: str,
    resource_id: str,
    action: Action,
) -> PermissionResult | None:
    """Check if an active delegation covers this request. Prunes after checking."""
    now = time.time()
    result: PermissionResult | None = None

    for record in delegations.get(tenant_id, []):
        if record.delegate_id != principal_id:
            continue
        if record.resource_type != resource_type:
            continue
        if record.resource_id != resource_id:
            continue
        if action not in record.allowed_actions:
            continue
        if record.expires_at.timestamp() <= now:
            result = PermissionResult(
                allowed=False, reason="delegation_expired",
                context={"purpose": record.purpose,
                         "on_behalf_of": record.delegator_id},
            )
            break
        result = PermissionResult(
            allowed=True, reason="delegation_allow",
            context={"purpose": record.purpose,
                     "on_behalf_of": record.delegator_id},
        )
        break

    prune_expired_delegations(delegations, tenant_id)
    return result


def prune_expired_delegations(
    delegations: dict[str, list[DelegationRecord]], tenant_id: str
) -> None:
    """Remove expired delegation records for a tenant."""
    if tenant_id not in delegations:
        return
    now = time.time()
    delegations[tenant_id] = [
        r for r in delegations[tenant_id] if r.expires_at.timestamp() > now
    ]


def get_json_schema() -> dict[str, Any]:
    """Describe this manager contract for agent discovery."""
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
                    "tenant_id": "string", "principal_id": "string",
                    "principal_type": "human|agent|team",
                    "resource_type": "string", "resource_id": "string",
                    "action": "read|write|create|delete|invoke|delegate",
                    "context": "object (optional)",
                },
                "returns": "PermissionDecision",
            },
            {
                "name": "check_delegation",
                "description": "Validate and record a time-limited delegation.",
                "parameters": {
                    "tenant_id": "string", "delegator_id": "string",
                    "delegate_id": "string", "delegate_type": "human|agent|team",
                    "resource_type": "string", "resource_id": "string",
                    "allowed_actions": "array", "ttl_seconds": "integer",
                    "purpose": "string", "context": "object (optional)",
                },
                "returns": "PermissionDecision",
            },
            {
                "name": "list_effective_permissions",
                "description": "List effective permissions for a principal.",
                "parameters": {
                    "tenant_id": "string", "principal_id": "string",
                    "principal_type": "human|agent|team",
                    "resource_type": "string (optional)",
                    "resource_id": "string (optional)",
                },
                "returns": "array",
            },
        ],
    }
