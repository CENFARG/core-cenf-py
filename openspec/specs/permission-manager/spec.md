---
Spec_ID: SPEC_M18
Title: PermissionManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [permission, rbac, abac, delegation, pycasbin, audit]
Dependency_Hashes: []
Last_Updated: "2026-06-21"
---

# SPEC_M18: PermissionManager

## Purpose

Provide unified human-agent authorization with hybrid RBAC + ABAC model. Treats humans, agents, and teams as *principals* with differentiated types. Supports explicit delegation with short-lived capabilities, declared purpose, and TTL. Every decision records `actor_id`, `on_behalf_of`, `purpose`, `workflow_id` for complete audit trails. Based on pycasbin (Apache 2.0) as policy engine, prepared for future ReBAC adapter (OpenFGA/SpiceDB).

**Does NOT**: Inherit all user permissions to agents, use shared service accounts, encode authorization rules in business logic.

## Python Protocol

```python
from __future__ import annotations
from typing import Protocol, Literal, Mapping, Any, runtime_checkable

PrincipalType = Literal["human", "agent", "team"]
Action = Literal["read", "write", "create", "delete", "invoke", "delegate"]


@runtime_checkable
class PermissionDecision(Protocol):
    """Result of an authorization check.

    Summary:
        Represents a single authorization decision with enough context for
        auditing and observability.
    Security:
        Must not contain secrets or PII; use opaque IDs.
    Observability:
        Should be logged by ObservabilityManager with correlation IDs.
    """

    def is_allowed(self) -> bool: ...
    def reason(self) -> str: ...
    def attributes(self) -> Mapping[str, Any]: ...


@runtime_checkable
class PermissionManager(Protocol):
    """@ai-directive: Always ask PermissionManager before accessing protected resources.
    Treat human users, AI agents, and teams uniformly as principals with a type attribute.
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
        Delegation MUST have explicit TTL and declared purpose.
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
        """Return an abstract view of effective permissions for inspection/UIs."""
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class PermissionRequest(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    tenant_id: str = Field(min_length=1, max_length=64)
    principal_id: str = Field(min_length=1, max_length=128)
    principal_type: Literal["human", "agent", "team"]
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: str = Field(min_length=1, max_length=128)
    action: Literal["read", "write", "create", "delete", "invoke", "delegate"]
    purpose: str | None = Field(default=None, max_length=256)
    workflow_id: str | None = Field(default=None, max_length=64)


class DelegationRequest(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}
    tenant_id: str = Field(min_length=1, max_length=64)
    delegator_id: str = Field(min_length=1, max_length=128)
    delegate_id: str = Field(min_length=1, max_length=128)
    delegate_type: Literal["human", "agent", "team"]
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: str = Field(min_length=1, max_length=128)
    allowed_actions: list[str] = Field(min_length=1, max_length=10)
    ttl_seconds: int = Field(ge=1, le=86400)
    purpose: str = Field(min_length=1, max_length=256)
```

## Gherkin Scenarios

### Scenario: Human permission check — allowed

- GIVEN a human principal with role "manager" and RBAC policy granting `write` on `resource_type="document"`
- WHEN `check_permission(tenant_id="t1", principal_id="u1", principal_type="human", resource_type="document", resource_id="doc-1", action="write")` is called
- THEN it returns `PermissionDecision` with `is_allowed() == True`
- AND reason is `"rbac_allow"`

### Scenario: Agent delegation with TTL

- GIVEN a human delegator "u1" delegates to agent "agent-1" with `allowed_actions=["read"]`, `ttl_seconds=300`, `purpose="generate_report"`
- WHEN `check_delegation(...)` is called within TTL
- THEN it returns `PermissionDecision` with `is_allowed() == True`
- AND attributes include `purpose="generate_report"` and `on_behalf_of="u1"`

### Scenario: Expired delegation denied

- GIVEN a delegation was created with `ttl_seconds=60` and 120 seconds have elapsed
- WHEN `check_delegation(...)` is called for the same delegate
- THEN it returns `PermissionDecision` with `is_allowed() == False`
- AND reason is `"delegation_expired"`

### Scenario: Unauthorized action denied

- GIVEN an agent principal with role "agent_basic" (cannot delegate per RBAC guardrail)
- WHEN `check_permission(..., action="delegate")` is called
- THEN it returns `PermissionDecision` with `is_allowed() == False`
- AND reason is `"rbac_deny"`

### Scenario: Invalid principal type raises ValidationError

- GIVEN a request with `principal_type="unknown"`
- WHEN `check_permission(...)` is called
- THEN it raises `ValidationError` with reason `"invalid_principal_type"`

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Invalid principal type | VALIDATION | Re-raise immediately |
| Missing tenant_id | VALIDATION | Re-raise immediately |
| Permission denied | AUTH | Return denied decision, log audit |
| Delegation expired | AUTH | Return denied decision, log audit |
| Policy engine unreachable | TRANSIENT | Retry with backoff, default deny |
| Policy file malformed | PERMANENT | Fail bootstrap |

## RED Metrics

- `cenf.permission.check_total` (counter)
- `cenf.permission.denied_total` (counter, labels: `reason`, `principal_type`)
- `cenf.permission.check_duration_seconds` (histogram)
- `cenf.permission.delegation_created_total` (counter)
- `cenf.permission.delegation_expired_total` (counter)

## Test Requirements

- **Unit**: `InMemoryPermissionAdapter` — dict-based policy store, no I/O. Tests all check methods, delegation TTL expiry, and error paths.
- **Integration**: `PyCasbinAdapter` with RBAC model file and policy CSV.
- **E2E**: Full delegation chain: human delegates to agent, agent acts on_behalf_of, audit log records chain.

## Do's and Don'ts

**Do**:
- Treat agents as first-class identities with their own principal type
- Use explicit delegation with limited scope and strict TTL
- Record complete audit trail with `on_behalf_of` chain
- Default deny when policy engine is unreachable
- Use pycasbin (Apache 2.0) as the MVP policy engine

**Don't**:
- Inherit all user permissions to agents automatically
- Use a shared service account for all agents
- Encode authorization rules in business logic
- Log PII or secrets in audit records
