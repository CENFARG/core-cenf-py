"""CENF PermissionManager — RBAC+ABAC authorization with agent delegation.

Provides a Protocol-based interface for unified human-agent authorization.
Treats humans, agents, and teams as principals with differentiated types.
Supports explicit delegation with short-lived capabilities, declared purpose,
and TTL. Every decision records complete audit trails.

Policy engine: pycasbin (Apache 2.0) for MVP; OpenFGA adapter reserved for
    future ReBAC phase.
Security: Default deny on policy engine failure. Delegations require explicit
    scope and TTL. NEVER inherit all user permissions to agents automatically.
Observability: Emits RED metrics for permission checks, denials, and
    delegation activity.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.permission.adapters.casbin_permission_adapter import (
    CasbinPermissionAdapter,
)
from core_infrastructure.permission.adapters.in_memory_permission_adapter import (
    InMemoryPermissionAdapter,
)
from core_infrastructure.permission.models import (
    DelegationRecord,
    PermissionConfig,
    PermissionResult,
)
from core_infrastructure.permission.ports import (
    Action,
    PermissionDecision,
    PermissionManager,
    PrincipalType,
)

__all__ = [
    "Action",
    "CasbinPermissionAdapter",
    "DelegationRecord",
    "InMemoryPermissionAdapter",
    "PermissionConfig",
    "PermissionDecision",
    "PermissionManager",
    "PermissionResult",
    "PrincipalType",
]
