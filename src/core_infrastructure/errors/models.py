"""CENF ErrorHandlingManager models — ErrorReport, ErrorClassification, ErrorContext.

Defines the Pydantic models for ErrorHandlingManager data transfer.
ErrorClassification maps directly to the ErrorType taxonomy from common.errors.
ErrorReport provides structured serialization for observability backends.

Security: ErrorReport never includes raw secrets or PII in its payload.
Observability: ErrorReport.error_type enables metric aggregation in dashboards.
@ai-directive: ErrorClassification enum MUST stay in sync with common.errors.ErrorType.
    If you add a new ErrorType, add the corresponding ErrorClassification member here.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from enum import Enum, auto

from pydantic import BaseModel, Field


class ErrorClassification(Enum):
    """Error classification taxonomy matching common.errors.ErrorType.

    Used by ErrorHandlingManager to decide between retry (TRANSIENT, RATE_LIMIT)
    and immediate failure (PERMANENT, VALIDATION, AUTH).
    """

    TRANSIENT = auto()
    PERMANENT = auto()
    VALIDATION = auto()
    AUTH = auto()
    RATE_LIMIT = auto()


class ErrorContext(BaseModel):
    """Contextual metadata for error classification and reporting.

    Attributes:
        correlation_id: Trace identifier from common.context.
        tenant_id: Multi-tenant identifier for data isolation.
        source: Component or function name where the error originated.
    """

    correlation_id: str = Field(
        default="",
        max_length=64,
        description="Trace correlation identifier.",
    )
    tenant_id: str = Field(
        default="",
        max_length=64,
        description="Multi-tenant identifier.",
    )
    source: str = Field(
        default="",
        max_length=256,
        description="Component or function name originating the error.",
    )


class ErrorReport(BaseModel):
    """Structured error report for observability backends.

    Produced by ErrorHandlingManager.handle() and consumed by
    ObservabilityManager for RED metric emission and trace span events.

    Attributes:
        error_type: Classification from the taxonomy.
        message: Human-readable error description (no secrets).
        source: Originating component or function name.
        correlation_id: Trace identifier for linking to logs.
        tenant_id: Tenant context at time of error.
    """

    error_type: str = Field(
        ...,
        description="ErrorClassification value as string (e.g. 'TRANSIENT').",
    )
    message: str = Field(
        ...,
        description="Human-readable error description.",
    )
    source: str = Field(
        default="",
        max_length=256,
        description="Originating component identifier.",
    )
    correlation_id: str = Field(
        default="",
        max_length=64,
        description="Trace correlation identifier.",
    )
    tenant_id: str = Field(
        default="",
        max_length=64,
        description="Tenant context at time of error.",
    )
