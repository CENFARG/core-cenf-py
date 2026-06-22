"""CasbinPermissionAdapter helpers — delegation matching, validation, policy utilities.

Extracted from ``casbin_permission_adapter.py`` to comply with the 250-line
CENF rule. Contains delegation matching, expiration pruning, principal type
validation, and JSON schema generation. Larger delegation/permission-listing
functions live in ``casbin_permission_delegation.py``.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.permission.models import (
    DelegationRecord,
    PermissionResult,
)
from core_infrastructure.permission.ports import Action

logger = logging.getLogger(__name__)


def validate_principal_type(principal_type: str) -> None:
    """Validate principal_type is one of human/agent/team."""
    valid = {"human", "agent", "team"}
    if principal_type not in valid:
        raise ValidationError(
            f"invalid_principal_type: {principal_type!r}",
            details={"reason": "invalid_principal_type",
                     "valid_types": ", ".join(sorted(valid))},
        )


def check_active_delegation(
    *,
    enforcer: Any,
    delegations: list[tuple[str, DelegationRecord]],
    tenant_id: str,
    principal_id: str,
    resource_type: str,
    resource_id: str,
    action: Action,
) -> PermissionResult | None:
    """Check if an active delegation covers this request. Prunes after checking."""
    now = time.time()
    result: PermissionResult | None = None

    for _rec_tenant_id, record in delegations:
        if _rec_tenant_id != tenant_id:
            continue
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
        allowed = enforcer.enforce(principal_id, tenant_id, resource_id, action)
        if allowed:
            result = PermissionResult(
                allowed=True, reason="delegation_allow",
                context={"purpose": record.purpose,
                         "on_behalf_of": record.delegator_id},
            )
            break

    _prune_expired_delegations(enforcer, delegations)
    return result


def prune_expired_delegations(
    enforcer: Any,
    delegations: list[tuple[str, DelegationRecord]],
) -> list[tuple[str, DelegationRecord]]:
    """Remove expired delegation records and Casbin policies."""
    now = time.time()
    active: list[tuple[str, DelegationRecord]] = []
    for tenant_id, record in delegations:
        if record.expires_at.timestamp() > now:
            active.append((tenant_id, record))
        else:
            for act in record.allowed_actions:
                with contextlib.suppress(Exception):
                    enforcer.remove_policy(
                        record.delegate_id, tenant_id,
                        record.resource_id, act,
                    )
    return active


_prune_expired_delegations = prune_expired_delegations


def get_json_schema() -> dict[str, Any]:
    """Describe this manager contract for agent discovery."""
    return {
        "name": "PermissionManager",
        "engine": "pycasbin",
        "version": "0.1.0",
        "description": (
            "Unified human-agent authorization with RBAC+ABAC via pycasbin. "
            "Treats humans, agents, and teams as principals with domain-based "
            "multi-tenant isolation. Supports explicit delegation with TTL."
        ),
        "methods": [
            {
                "name": "check_permission",
                "description": "Evaluate RBAC + active delegations via Casbin.",
                "parameters": {
                    "tenant_id": "string (Casbin domain)",
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
                "description": "Create temporary Casbin policy with TTL.",
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
                },
                "returns": "PermissionDecision",
            },
        ],
    }
