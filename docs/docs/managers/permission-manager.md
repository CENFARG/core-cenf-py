---
sidebar_position: 18
---

# PermissionManager (M18)

Hybrid RBAC + ABAC authorization via `pycasbin` (Apache 2.0). Supports human, agent, and team principals with explicit delegation, time-limited capabilities, and declared purpose. **Default deny when policy engine is unreachable.** Treats human users, AI agents, and teams uniformly as principals with a type attribute.

## Protocol

`PermissionManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.permission.ports`.

### Principal Types and Actions

```python
PrincipalType = Literal["human", "agent", "team"]
Action = Literal["read", "write", "create", "delete", "invoke", "delegate"]
```

---

### `async check_permission(...) → PermissionDecision`

Evaluate whether a principal may perform an action on a resource. Evaluates RBAC + active delegations.

```python
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
) -> PermissionDecision: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `tenant_id` | `str` | Multi-tenant identifier for data isolation |
| `principal_id` | `str` | The principal requesting access (human/agent/team ID) |
| `principal_type` | `PrincipalType` | `"human"`, `"agent"`, or `"team"` |
| `resource_type` | `str` | Type of resource being accessed |
| `resource_id` | `str` | Identifier of the specific resource |
| `action` | `Action` | `"read"`, `"write"`, `"create"`, `"delete"`, `"invoke"`, `"delegate"` |
| `context` | `Mapping \| None` | Optional: `purpose`, `workflow_id`, `on_behalf_of`, `risk_level` |

**Returns:** `PermissionDecision` with `is_allowed()`, `reason()`, and `attributes()`.

**Raises:** `ValidationError` if `principal_type` is invalid or required fields are empty.

---

### `async check_delegation(...) → PermissionDecision`

Validate whether a delegator may delegate `allowed_actions` to a delegate. Delegation MUST have explicit TTL and declared purpose. The adapter stores the delegation record and creates temporary policy entries.

```python
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
) -> PermissionDecision: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `delegator_id` | `str` | Principal granting the delegation |
| `delegate_id` | `str` | Principal receiving the delegation |
| `delegate_type` | `PrincipalType` | Type of the delegate |
| `allowed_actions` | `list[Action]` | Actions the delegate may perform |
| `ttl_seconds` | `int` | Time-to-live in seconds (max 86400 = 24h) |
| `purpose` | `str` | Declared purpose for the delegation |

**Raises:** `ValidationError` if `ttl_seconds` is invalid or required fields are empty.

---

### `async list_effective_permissions(...) → list[Mapping[str, Any]]`

Return an abstract view of effective permissions for inspection, audit dashboards, and debugging. Each entry has at minimum: `resource_type`, `resource_id`, `action`, `source` (rbac/delegation), and `expiry` if applicable.

```python
async def list_effective_permissions(
    self,
    *,
    tenant_id: str,
    principal_id: str,
    principal_type: PrincipalType,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> list[Mapping[str, Any]]: ...
```

---

### `get_json_schema() → dict[str, Any]` *(static)*

Describe this manager contract for agent discovery.

---

## Models

**File:** `core_infrastructure.permission.models`

### `PermissionConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model_path` | `str` (≤1024) | `""` | Path to Casbin `model.conf` (RBAC with domains) |
| `policy_path` | `str` (≤1024) | `""` | Path to Casbin `policy.csv` |

### `DelegationRecord`

Frozen model (`extra="forbid"`). TTL capped at 86400 seconds (24 hours).

| Field | Type | Description |
|-------|------|-------------|
| `delegator_id` | `str` (1–128) | Principal granting the delegation |
| `delegate_id` | `str` (1–128) | Principal receiving the delegation |
| `delegate_type` | `"human" \| "agent" \| "team"` | Type of the delegate |
| `resource_type` | `str` (1–64) | Resource type |
| `resource_id` | `str` (1–128) | Resource identifier |
| `allowed_actions` | `list[str]` (1–10) | Permitted actions |
| `purpose` | `str` (1–256) | Declared purpose |
| `ttl_seconds` | `int` (1–86400) | Time-to-live |
| `created_at` | `datetime` | UTC creation timestamp |
| `expires_at` | `datetime` | Computed from `created_at + ttl_seconds` |

### `PermissionResult`

Concrete `PermissionDecision` with `allowed` (bool), `reason` (str), `policy_id` (str), and `context` (dict).

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `CasbinPermissionAdapter` | `pycasbin` engine | Production — RBAC with domains, model.conf + policy.csv |
| `InMemoryPermissionAdapter` | In-memory dict | Testing — preconfigure allow/deny decisions per tenant+principal+resource |

**Policy model:** RBAC with domains where `tenant_id` is the domain. Role hierarchy via Casbin's `g` function. Delegations create temporary policy rules stored in-memory with TTL expiration. `CasbinPermissionAdapter` loads `model.conf` and `policy.csv` from paths in `PermissionConfig`.

---

## Usage Example

```python
from core_infrastructure.permission.adapters.in_memory_permission_adapter import (
    InMemoryPermissionAdapter,
)
from core_infrastructure.permission.models import PermissionConfig, PermissionResult

# Testing: InMemoryPermissionAdapter
perm_mgr = InMemoryPermissionAdapter(config=PermissionConfig())

# Pre-configure decisions
perm_mgr.set_decision(
    tenant_id="cntrs",
    principal_id="user-123",
    resource_type="document",
    resource_id="doc-001",
    action="read",
    allowed=True,
    reason="rbac_allow",
)
perm_mgr.set_decision(
    tenant_id="cntrs",
    principal_id="user-123",
    resource_type="document",
    resource_id="doc-001",
    action="delete",
    allowed=False,
    reason="rbac_deny",
)

# Check permission
decision = await perm_mgr.check_permission(
    tenant_id="cntrs",
    principal_id="user-123",
    principal_type="human",
    resource_type="document",
    resource_id="doc-001",
    action="read",
    context={"purpose": "audit"},
)
assert decision.is_allowed() is True
assert decision.reason() == "rbac_allow"

# Denied action
denied = await perm_mgr.check_permission(
    tenant_id="cntrs",
    principal_id="user-123",
    principal_type="human",
    resource_type="document",
    resource_id="doc-001",
    action="delete",
)
assert denied.is_allowed() is False

# Delegation: grant agent temporary read access
delegation = await perm_mgr.check_delegation(
    tenant_id="cntrs",
    delegator_id="user-123",
    delegate_id="agent-456",
    delegate_type="agent",
    resource_type="document",
    resource_id="doc-001",
    allowed_actions=["read"],
    ttl_seconds=3600,
    purpose="audit_review",
)
assert delegation.is_allowed() is True

# List effective permissions (for UI)
perms = await perm_mgr.list_effective_permissions(
    tenant_id="cntrs",
    principal_id="user-123",
    principal_type="human",
)

# Production: CasbinPermissionAdapter
# from core_infrastructure.permission.adapters.casbin_permission_adapter import CasbinPermissionAdapter
# casbin_mgr = CasbinPermissionAdapter(config=PermissionConfig(
#     model_path="rbac_model.conf",
#     policy_path="rbac_policy.csv",
# ))
```

---

## @ai-directive

> **Always consult PermissionManager before accessing protected resources.** Treat human users, AI agents, and teams uniformly as principals with a type attribute. NEVER inherit all user permissions to agents automatically — each delegation must have explicit scope, TTL, and declared purpose. Default deny when policy engine is unreachable. `on_behalf_of` is recorded in audit context for every agent action.

## Related

- [AuthManager](auth-manager.md) — sets `tenant_id` and `principal_id` contextvars after token validation
- [LicenceManager](licence-manager.md) — determines WHAT features exist; PermissionManager determines WHO can use them
- [ObservabilityManager](observability-manager.md) — every decision emits audit counters
