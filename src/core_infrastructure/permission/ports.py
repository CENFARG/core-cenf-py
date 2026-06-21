"""PermissionManager Protocol — the contract every permission adapter must satisfy.

Defines the authorization interface consumed by all infrastructure managers
that need RBAC+ABAC access control. Supports human, agent, and team principals
with explicit delegation, short-lived capabilities, and declared purpose.

Based on pycasbin (Apache 2.0) as the MVP policy engine with RBAC domains.
Future ReBAC adapter (OpenFGA/SpiceDB) reserved.

Security: Default deny when policy engine is unreachable. Delegation MUST
    have explicit TTL and declared purpose.
Observability: Every decision records actor_id, on_behalf_of, purpose,
    workflow_id for complete audit trails.
@ai-directive: Always ask PermissionManager before accessing protected resources.
    Treat human users, AI agents, and teams uniformly as principals with a
    type attribute. NEVER inherit all user permissions to agents automatically.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Protocol, runtime_checkable

PrincipalType = Literal["human", "agent", "team"]
"""Valid principal types: human users, AI agents, and teams."""

Action = Literal["read", "write", "create", "delete", "invoke", "delegate"]
"""Valid actions a principal may perform on a resource."""


@runtime_checkable
class PermissionDecision(Protocol):
    """Result of an authorization check.

    Represents a single authorization decision with enough context for
    auditing and observability. Implementations must be immutable or
    at minimum provide stable return values from all three methods.

    Security:
        Must not contain secrets or PII; use opaque IDs.
    Observability:
        Should be logged by ObservabilityManager with correlation IDs.
    """

    def is_allowed(self) -> bool:
        """Return whether the action is permitted.

        Returns:
            bool: True if the principal is authorized to perform the action.
        """
        ...

    def reason(self) -> str:
        """Return a human-readable reason for the decision.

        Returns:
            str: Reason code like ``"rbac_allow"``, ``"rbac_deny"``,
                ``"delegation_expired"``, or ``"default_deny"``.
        """
        ...

    def attributes(self) -> Mapping[str, Any]:
        """Return contextual attributes for audit and observability.

        Returns:
            Mapping[str, Any]: Attributes such as ``purpose``, ``on_behalf_of``,
                ``policy_id``, ``workflow_id``. Must be JSON-serializable.
        """
        ...


@runtime_checkable
class PermissionManager(Protocol):
    """Authorization contract for RBAC+ABAC access control.

    All infrastructure managers that need to authorize access to protected
    resources consume this interface. Concrete adapters provide dict-based
    policies (InMemoryPermissionAdapter for testing) or pycasbin engine
    (CasbinPermissionAdapter for production).

    Rules:
        - check_permission() evaluates RBAC + active delegations.
        - check_delegation() validates and records a time-limited delegation.
        - list_effective_permissions() returns an abstract view for UIs.
        - get_json_schema() describes this contract for agent discovery.
        - Default deny when policy engine is unreachable.

    Security: NEVER inherit all user permissions to agents automatically.
        Each delegation must have explicit scope and TTL.

    @ai-directive: Always ask PermissionManager before accessing protected
        resources. Treat human users, AI agents, and teams uniformly as
        principals with a type attribute.
    """

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
        """Evaluate whether the principal may perform action on resource.

        Context SHOULD include purpose, workflow_id, on_behalf_of, risk_level.

        Args:
            tenant_id: Multi-tenant identifier for data isolation.
            principal_id: The principal requesting access (human/agent/team ID).
            principal_type: Type of the principal (human, agent, team).
            resource_type: Type of the resource being accessed.
            resource_id: Identifier of the specific resource.
            action: The action being requested.
            context: Optional context including purpose, workflow_id,
                on_behalf_of, risk_level.

        Returns:
            PermissionDecision: The authorization result with reason and
                audit attributes.

        Raises:
            ValidationError: If principal_type is invalid (not human/agent/team)
                or required fields are empty.
        """
        ...

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
        """Validate whether delegator may delegate allowed_actions to delegate.

        Delegation MUST have explicit TTL and declared purpose. The adapter
        stores the delegation record and creates temporary policy entries
        for the delegate.

        Args:
            tenant_id: Multi-tenant identifier.
            delegator_id: The principal granting the delegation.
            delegate_id: The principal receiving the delegation.
            delegate_type: Type of the delegate (human, agent, team).
            resource_type: Type of the resource.
            resource_id: Identifier of the resource.
            allowed_actions: Actions the delegate is permitted to perform.
            ttl_seconds: Time-to-live in seconds for this delegation.
            purpose: Declared purpose for the delegation.
            context: Optional context for audit.

        Returns:
            PermissionDecision: Allowed if delegator has delegate permission
                and the delegation is valid; denied otherwise.

        Raises:
            ValidationError: If ttl_seconds is invalid or required fields
                are empty.
        """
        ...

    async def list_effective_permissions(
        self,
        *,
        tenant_id: str,
        principal_id: str,
        principal_type: PrincipalType,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> list[Mapping[str, Any]]:
        """Return an abstract view of effective permissions for inspection/UIs.

        Useful for permission explorers, audit dashboards, and debugging.
        Optionally filter by resource_type and resource_id.

        Args:
            tenant_id: Multi-tenant identifier.
            principal_id: The principal whose permissions to list.
            principal_type: Type of the principal.
            resource_type: Optional filter by resource type.
            resource_id: Optional filter by resource identifier.

        Returns:
            list[Mapping[str, Any]]: List of permission entries, each with
                at minimum: resource_type, resource_id, action, source
                (rbac/delegation), and expiry (if applicable).
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery.

        Returns a JSON Schema that tools/agents can use to understand
        how to call the PermissionManager.

        Returns:
            dict[str, Any]: JSON Schema describing the PermissionManager
                interface (methods, parameters, return types).
        """
        ...
