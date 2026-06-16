"""CENF context propagation — contextvars-based tracing primitives.

Provides implicit correlation and tracing identifiers that propagate across
async boundaries within the same asyncio task without needing to pass them
as explicit function parameters. All 12 infrastructure managers read these
contextvars to attach correlation/trace data to logs, spans, and outbound
requests.

Security: No sensitive data stored in contextvars — only trace identifiers.
Observability: Every log line and span auto-injects correlation_id + tenant_id.
@ai-directive: This is a zero-dependency module. Do NOT add external imports.

Author: CENF AI Team
Version: 0.1.0
"""

import uuid
from contextvars import ContextVar

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# ContextVar declarations (module-level, zero-dependency)
# ---------------------------------------------------------------------------

_correlation_id: ContextVar[str] = ContextVar("cenf_correlation_id", default="system-init")
_tenant_id: ContextVar[str] = ContextVar("cenf_tenant_id", default="global")
_trace_id: ContextVar[str] = ContextVar("cenf_trace_id", default="")
_span_id: ContextVar[str] = ContextVar("cenf_span_id", default="")


# ---------------------------------------------------------------------------
# Getter / Setter functions
# ---------------------------------------------------------------------------


def get_correlation_id() -> str:
    """Return the current correlation_id or the default ``"system-init"``.

    Returns:
        str: Current correlation_id context value.
    """
    return _correlation_id.get()


def set_correlation_id(cid: str) -> None:
    """Set the correlation_id contextvar.

    Args:
        cid: New correlation_id string. Must be 1-64 chars (validated by
            ``ContextValidation`` at the boundary where the value originates).

    Security: Callers MUST validate the input via ``ContextValidation`` before
        calling this setter if the value comes from an external source.
    """
    _correlation_id.set(cid)


def get_tenant_id() -> str:
    """Return the current tenant_id or the default ``"global"``.

    Returns:
        str: Current tenant_id context value.
    """
    return _tenant_id.get()


def set_tenant_id(tid: str) -> None:
    """Set the tenant_id contextvar.

    Args:
        tid: New tenant_id string (1-64 chars).
    """
    _tenant_id.set(tid)


def get_trace_id() -> str:
    """Return the current trace_id or empty string if no trace is active.

    Returns:
        str: Current OpenTelemetry trace_id (hex) or ``""``.
    """
    return _trace_id.get()


def set_trace_id(tid: str) -> None:
    """Set the trace_id contextvar.

    Args:
        tid: OpenTelemetry trace_id hex string.
    """
    _trace_id.set(tid)


def get_span_id() -> str:
    """Return the current span_id or empty string if no span is active.

    Returns:
        str: Current OpenTelemetry span_id (hex) or ``""``.
    """
    return _span_id.get()


def set_span_id(sid: str) -> None:
    """Set the span_id contextvar.

    Args:
        sid: OpenTelemetry span_id hex string.
    """
    _span_id.set(sid)


# ---------------------------------------------------------------------------
# Snapshot / Restore (serialization for crossing async boundaries)
# ---------------------------------------------------------------------------


def get_context_snapshot() -> dict[str, str]:
    """Capture all four contextvars into a serializable dict.

    Use this before crossing a boundary where contextvars might be lost
    (e.g., SAQ job payload, HTTP request dispatch).

    Returns:
        dict[str, str]: Snapshot with keys ``correlation_id``, ``tenant_id``,
            ``trace_id``, ``span_id``.

    Observability: Snapshot values are logged at DEBUG level by LoggerManager.
    """
    return {
        "correlation_id": get_correlation_id(),
        "tenant_id": get_tenant_id(),
        "trace_id": get_trace_id(),
        "span_id": get_span_id(),
    }


def restore_context_snapshot(snapshot: dict[str, str]) -> None:
    """Restore contextvars from a previously captured snapshot dict.

    Args:
        snapshot: Dict produced by ``get_context_snapshot()``. Missing keys
            are left unchanged.

    Security: Input trusted — caller is responsible for validating snapshot
        contents before restoration.
    """
    if "correlation_id" in snapshot:
        set_correlation_id(snapshot["correlation_id"])
    if "tenant_id" in snapshot:
        set_tenant_id(snapshot["tenant_id"])
    if "trace_id" in snapshot:
        set_trace_id(snapshot["trace_id"])
    if "span_id" in snapshot:
        set_span_id(snapshot["span_id"])


# ---------------------------------------------------------------------------
# UUID generation
# ---------------------------------------------------------------------------


def new_correlation_id() -> str:
    """Generate a fresh UUID4 correlation_id and set it on the contextvar.

    Returns:
        str: The newly generated UUID4 string.

    Observability: The previous correlation_id is logged at DEBUG level
        before replacement by LoggerManager.
    """
    cid = str(uuid.uuid4())
    set_correlation_id(cid)
    return cid


# ---------------------------------------------------------------------------
# Boundary validation model
# ---------------------------------------------------------------------------


class ContextValidation(BaseModel):
    """Pydantic model for validating contextvar values at I/O boundaries.

    All ``set_*`` functions in this module accept raw strings. Use this model
    to validate values coming from external sources (HTTP headers, message
    payloads, CLI arguments) BEFORE calling the setters.

    @ai-directive: This is the single validation gate for context propagation.
    """

    correlation_id: str = Field(
        default="system-init",
        min_length=1,
        max_length=64,
        description="Unique identifier correlating requests across services.",
    )
    tenant_id: str = Field(
        default="global",
        min_length=1,
        max_length=64,
        description="Multi-tenant identifier for data isolation.",
    )
    trace_id: str = Field(
        default="",
        max_length=64,
        description="OpenTelemetry trace_id (hex).",
    )
    span_id: str = Field(
        default="",
        max_length=64,
        description="OpenTelemetry span_id (hex).",
    )
