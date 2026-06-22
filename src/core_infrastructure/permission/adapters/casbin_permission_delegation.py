"""Casbin delegation helpers — delegation creation and permission listing.

Extracted from ``casbin_permission_helpers.py`` to comply with the 250-line
CENF rule. Contains delegation validation, temporary policy creation, and
effective permission listing for the Casbin enforcer.

What: Second-level extraction of delegation/permission-listing functions.
Why: 250-line CENF rule compliance for casbin_permission_helpers.py.
Where: src/core_infrastructure/permission/adapters/casbin_permission_delegation.py

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from core_infrastructure.permission.adapters.casbin_permission_helpers import (
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

logger = logging.getLogger(__name__)


async def perform_delegation(
    *,
    enforcer: Any,
    delegations: list[tuple[str, DelegationRecord]],
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
    """Validate and record a time-limited delegation via Casbin.

    Checks that the delegator has ``delegate`` permission via Casbin
    before creating the delegation. Adds temporary policy rules for
    the delegate with TTL-based expiration.
    """
    validate_principal_type(delegate_type)
    ctx = dict(context) if context else {}

    can_delegate = enforcer.enforce(delegator_id, tenant_id, resource_id, "delegate")
    if not can_delegate:
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
    delegations.append((tenant_id, record))

    for act in allowed_actions:
        enforcer.add_policy(delegate_id, tenant_id, resource_id, act)

    logger.debug(
        "Delegation created: %s -> %s on %s/%s [%s], TTL=%ds, purpose=%s",
        delegator_id, delegate_id, resource_type, resource_id,
        ", ".join(allowed_actions), ttl_seconds, purpose,
    )

    return PermissionResult(  # type: ignore[return-value]
        allowed=True, reason="delegation_created", policy_id="",
        context={**ctx, "purpose": purpose, "on_behalf_of": delegator_id,
                 "expires_at": record.expires_at.isoformat()},
    )


def list_effective_permissions(
    *,
    enforcer: Any,
    delegations: list[tuple[str, DelegationRecord]],
    tenant_id: str,
    principal_id: str,
    principal_type: PrincipalType,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> list[Mapping[str, Any]]:
    """Return abstract view of effective permissions.

    Queries Casbin for permissions granted to the principal directly
    and via role inheritance, plus active delegations.
    """
    result: list[Mapping[str, Any]] = []

    try:
        implicit_perms = enforcer.get_implicit_permissions_for_user(
            principal_id, tenant_id)
    except Exception:
        implicit_perms = []

    for perm in implicit_perms:
        if len(perm) >= 4:
            perm_resource_id = perm[2]
            perm_action = perm[3]
            if resource_id is not None and perm_resource_id != resource_id:
                continue
            result.append({
                "resource_type": resource_type or "*",
                "resource_id": perm_resource_id,
                "action": perm_action, "source": "rbac",
            })

    active_delegations = prune_expired_delegations(enforcer, delegations)
    delegations.clear()
    delegations.extend(active_delegations)

    for _rec_tenant_id, record in delegations:
        if _rec_tenant_id != tenant_id:
            continue
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
