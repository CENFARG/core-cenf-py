"""CasbinPermissionAdapter — pycasbin RBAC+ABAC engine for production.

Uses pycasbin (Apache 2.0) as the policy engine with RBAC domains for
multi-tenant isolation. Loads model.conf and policy.csv from paths in
PermissionConfig. Supports short-lived delegation via temporary policy
rules stored in-memory with TTL expiration.

Security: Default deny when policy engine is unreachable or model is
    malformed. Delegation policies are temporary and scoped.
Observability: Emits RED metrics for permission checks via
    ObservabilityManager when wired.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import casbin

from core_infrastructure.permission.adapters.casbin_permission_delegation import (
    list_effective_permissions,
    perform_delegation,
)
from core_infrastructure.permission.adapters.casbin_permission_helpers import (
    check_active_delegation,
    get_json_schema,
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


class CasbinPermissionAdapter:
    """pycasbin-based PermissionManager adapter with RBAC domains.

    Loads the Casbin model from ``PermissionConfig.model_path`` and
    policies from ``PermissionConfig.policy_path`` at construction time.
    Delegations create temporary policy rules stored in-memory with
    TTL-based expiration.

    Args:
        config: PermissionConfig with model_path and policy_path.

    Raises:
        FileNotFoundError: If model_path or policy_path does not exist.
        ValueError: If the model file is malformed.
    """

    def __init__(self, config: PermissionConfig) -> None:
        self._config = config
        self._enforcer = casbin.Enforcer(str(config.model_path), str(config.policy_path))
        self._delegations: list[tuple[str, DelegationRecord]] = []

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
        """Evaluate RBAC + active delegations via Casbin enforcer."""
        validate_principal_type(principal_type)
        ctx = dict(context) if context else {}

        delegation_result = check_active_delegation(
            enforcer=self._enforcer,
            delegations=self._delegations,
            tenant_id=tenant_id,
            principal_id=principal_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
        )
        if delegation_result is not None:
            merged_ctx = {**delegation_result.attributes(), **ctx}
            return PermissionResult(  # type: ignore[return-value]
                allowed=delegation_result.is_allowed(),
                reason=delegation_result.reason,
                context=merged_ctx,
            )

        allowed = self._enforcer.enforce(principal_id, tenant_id, resource_id, action)
        if allowed:
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
        """Validate and record a time-limited delegation (delegates to helpers)."""
        return await perform_delegation(
            enforcer=self._enforcer,
            delegations=self._delegations,
            tenant_id=tenant_id,
            delegator_id=delegator_id,
            delegate_id=delegate_id,
            delegate_type=delegate_type,
            resource_type=resource_type,
            resource_id=resource_id,
            allowed_actions=allowed_actions,
            ttl_seconds=ttl_seconds,
            purpose=purpose,
            context=context,
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
        """Return abstract view of effective permissions (delegates to helpers)."""
        return list_effective_permissions(
            enforcer=self._enforcer,
            delegations=self._delegations,
            tenant_id=tenant_id,
            principal_id=principal_id,
            principal_type=principal_type,
            resource_type=resource_type,
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

    def _check_active_delegation(
        self, *, tenant_id: str, principal_id: str, resource_type: str,
        resource_id: str, action: Action,
    ) -> PermissionResult | None:
        return check_active_delegation(
            enforcer=self._enforcer, delegations=self._delegations,
            tenant_id=tenant_id, principal_id=principal_id,
            resource_type=resource_type, resource_id=resource_id, action=action,
        )

    def _prune_expired_delegations(self) -> None:
        self._delegations = prune_expired_delegations(self._enforcer, self._delegations)
