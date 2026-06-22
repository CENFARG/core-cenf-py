"""CENF PermissionManager adapters — concrete policy engine implementations.

Provides InMemoryPermissionAdapter (dict-based test double) and
CasbinPermissionAdapter (pycasbin RBAC engine for production).

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.permission.adapters.in_memory_permission_adapter import (
    InMemoryPermissionAdapter,
)

__all__ = ["InMemoryPermissionAdapter"]
