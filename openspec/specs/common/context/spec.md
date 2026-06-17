---
Spec_ID: SPEC_CTX
Title: Common Context Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [contextvars, propagation, tracing, correlation]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_CTX: Common Context

## Purpose

Provide 5 contextvars for implicit propagation of trace identifiers across async boundaries. Zero-dependency module imported by all managers.

## Python API

```python
from contextvars import ContextVar
from pydantic import BaseModel, Field

# ContextVar declarations
_correlation_id: ContextVar[str] = ContextVar("cenf_correlation_id", default="system-init")
_tenant_id: ContextVar[str] = ContextVar("cenf_tenant_id", default="global")
_principal_id: ContextVar[str] = ContextVar("cenf_principal_id", default="")
_trace_id: ContextVar[str] = ContextVar("cenf_trace_id", default="")
_span_id: ContextVar[str] = ContextVar("cenf_span_id", default="")

# Accessor functions
def get_correlation_id() -> str: ...
def set_correlation_id(cid: str) -> None: ...
def get_tenant_id() -> str: ...
def set_tenant_id(tid: str) -> None: ...
def get_principal_id() -> str: ...
def set_principal_id(pid: str) -> None: ...
def get_trace_id() -> str: ...
def set_trace_id(tid: str) -> None: ...
def get_span_id() -> str: ...
def set_span_id(sid: str) -> None: ...
def new_correlation_id() -> str: ...
def get_context_snapshot() -> dict[str, str]: ...
def restore_context_snapshot(snapshot: dict[str, str]) -> None: ...

# Boundary validation
class ContextValidation(BaseModel):
    correlation_id: str = Field(default="system-init", min_length=1, max_length=64)
    tenant_id: str = Field(default="global", min_length=1, max_length=64)
    principal_id: str = Field(default="", max_length=64)
    trace_id: str = Field(default="", max_length=64)
    span_id: str = Field(default="", max_length=64)
```

## Producer/Consumer Matrix

| ContextVar | Producer | Consumers |
|------------|----------|-----------|
| `correlation_id` | HTTP handler, SAQ worker, CLI entry | All managers (logs, spans, DB queries) |
| `tenant_id` | AuthManager (from JWT claims) | DatabaseManager, CacheManager, LoggerManager |
| `principal_id` | AuthManager (from JWT claims) | LoggerManager, AlertManager |
| `trace_id` | ObservabilityManager (OTel span) | LoggerManager, ExternalAPIManager |
| `span_id` | ObservabilityManager (OTel span) | LoggerManager |

## Gherkin Scenarios

### Scenario: Snapshot and restore roundtrip

- GIVEN all 5 contextvars are set to non-default values
- WHEN `get_context_snapshot()` is called
- THEN it returns a dict with all 5 keys and their values
- AND `restore_context_snapshot(snapshot)` restores all 5 contextvars to the captured values

### Scenario: New correlation ID generation

- WHEN `new_correlation_id()` is called
- THEN it returns a valid UUID4 string
- AND `get_correlation_id()` returns the same UUID4

### Scenario: Contextvars propagate across await

- GIVEN correlation_id is set to "abc-123" in an async function
- WHEN the function awaits another async function
- THEN the awaited function reads `get_correlation_id()` as "abc-123"

### Scenario: Validation rejects oversized values

- GIVEN a correlation_id of 200 characters
- WHEN `ContextValidation(correlation_id=value)` is called
- THEN it raises `ValidationError` (max_length=64)

### Scenario: Default values

- WHEN no contextvars are set
- THEN `get_correlation_id()` returns `"system-init"`
- AND `get_tenant_id()` returns `"global"`
- AND `get_principal_id()`, `get_trace_id()`, `get_span_id()` return `""`

## Error Classification

This module does not raise errors. All setters accept raw strings. Validation is the caller's responsibility via `ContextValidation`.

## RED Metrics

None — this is a zero-dependency utility module.

## Test Requirements

- **Unit**: Test all get/set functions, snapshot/restore roundtrip, UUID4 generation.
- **Integration**: Verify contextvars propagate across `asyncio.TaskGroup` boundaries.
- **E2E**: Set contextvars at HTTP entry point, verify they appear in logs and spans across 5 managers.

## Do's and Don'ts

**Do**:
- Store only trace identifiers (no sensitive data)
- Validate values via `ContextValidation` at I/O boundaries
- Use snapshot/restore when crossing async boundaries (SAQ jobs, TaskGroup sub-tasks)

**Don't**:
- Add external imports (zero-dependency module)
- Store PII, credentials, or business data in contextvars
- Pass context as function parameters (use contextvars implicitly)
