"""CENF common cross-cutting modules — context propagation, error taxonomy, lifecycle protocol.

Provides zero-dependency shared abstractions used by all 12 infrastructure
managers: contextvars-based correlation tracing, structured error hierarchy,
and the AsyncLifecycle health-check protocol.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.common.context import (
    ContextValidation,
    get_context_snapshot,
    get_correlation_id,
    get_principal_id,
    get_span_id,
    get_tenant_id,
    get_trace_id,
    new_correlation_id,
    restore_context_snapshot,
    set_correlation_id,
    set_principal_id,
    set_span_id,
    set_tenant_id,
    set_trace_id,
)
from core_infrastructure.common.errors import (
    AuthError,
    CenfError,
    ErrorType,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationError,
)
from core_infrastructure.common.lifecycle import AsyncLifecycle, HealthStatus, LifecycleManager

__all__ = [
    "AsyncLifecycle",
    "AuthError",
    "CenfError",
    "ContextValidation",
    "ErrorType",
    "HealthStatus",
    "LifecycleManager",
    "PermanentError",
    "RateLimitError",
    "TransientError",
    "ValidationError",
    "get_context_snapshot",
    "get_correlation_id",
    "get_principal_id",
    "get_span_id",
    "get_tenant_id",
    "get_trace_id",
    "new_correlation_id",
    "restore_context_snapshot",
    "set_correlation_id",
    "set_principal_id",
    "set_span_id",
    "set_tenant_id",
    "set_trace_id",
]
