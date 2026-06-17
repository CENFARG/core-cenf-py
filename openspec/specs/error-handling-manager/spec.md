---
Spec_ID: SPEC_M04
Title: ErrorHandlingManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [errors, taxonomy, decorator, exception-group]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M04: ErrorHandlingManager

## Purpose

Provide error classification, reporting, and the `@handle_errors` decorator factory. Maps built-in exceptions to ErrorType taxonomy, unwraps ExceptionGroup (PEP 654), and emits RED metrics.

**Does NOT**: Swallow errors (always re-raise), decide business retry logic, include raw secrets in error reports.

## Python Protocol

```python
from __future__ import annotations
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

from core_infrastructure.common.errors import ErrorType
from core_infrastructure.errors.models import ErrorClassification, ErrorReport

F = TypeVar("F", bound=Callable[..., Any])

@runtime_checkable
class ErrorHandlingManager(Protocol):
    """@ai-directive: handle_errors is a sync decorator factory. Apply BEFORE framework middleware."""

    def classify(self, error: Exception) -> ErrorClassification:
        """Classify an exception using the CenfError taxonomy."""
        ...

    def report(self, error: Exception, context: dict[str, Any] | None = None) -> None:
        """Log and emit metrics for a classified error."""
        ...

    def handle(self, error: Exception, context: dict[str, Any] | None = None) -> ErrorReport:
        """Classify and report an error in a single call."""
        ...

    def handle_errors(self, **decorator_opts: Any) -> Callable[[F], F]:
        """Return a decorator that classifies, logs, and re-raises errors."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class ErrorHandlingSettings(BaseModel):
    max_retries_default: int = Field(default=3, ge=1, le=10)
    retry_backoff_base: float = Field(default=2.0, ge=0.5)
    retry_backoff_max: float = Field(default=30.0, ge=5.0)
    buffer_max_size: int = Field(default=1000, ge=100)
    include_stack_trace: bool = Field(default=True)
```

## Gherkin Scenarios

### Scenario: Classify TransientError

- GIVEN a `ConnectionError` is raised
- WHEN `classify(error)` is called
- THEN it returns `ErrorClassification.TRANSIENT`

### Scenario: Classify ValidationError

- GIVEN a `ValueError` from input parsing is raised
- WHEN `classify(error)` is called
- THEN it returns `ErrorClassification.VALIDATION`

### Scenario: @handle_errors decorator re-raises

- GIVEN a function decorated with `@handle_errors()`
- WHEN the function raises `TransientError`
- THEN the error is classified, logged, metrics emitted
- AND the error is RE-RAISED (never swallowed)

### Scenario: ExceptionGroup unwrapping

- GIVEN an `ExceptionGroup` containing `[TransientError, ValidationError]`
- WHEN `unpack_group(group)` is called
- THEN it returns a flat list `[TransientError, ValidationError]`
- AND each error is classified independently

### Scenario: Register custom handler

- GIVEN a custom handler registered for `ErrorType.AUTH`
- WHEN an `AuthError` is handled
- THEN the custom handler is invoked
- AND the error is still re-raised after handling

### Scenario: Error metrics emission

- GIVEN a `TransientError` is classified
- WHEN `report(error)` is called
- THEN `cenf.error.classified_total{error_type="TRANSIENT"}` counter increments

## Error Classification

| Built-in Exception | ErrorType |
|-------------------|-----------|
| `ConnectionError`, `TimeoutError` | TRANSIENT |
| `ValueError`, `KeyError`, `TypeError` | VALIDATION |
| `PermissionError`, auth failures | AUTH |
| HTTP 429 | RATE_LIMIT |
| `FileNotFoundError` (config), `NotImplementedError` | PERMANENT |

## RED Metrics

- `cenf.error.classified_total{error_type="..."}` (counter)
- `cenf.error.pending_count` (gauge)

## Test Requirements

- **Unit**: `InMemoryErrorAdapter` — pure taxonomy, no OTel dependency.
- **Integration**: `TaxonomyAdapter` with real `InMemoryObservabilityAdapter`.
- **E2E**: Error metrics emission verified.

## Do's and Don'ts

**Do**:
- Map built-in exceptions to ErrorType via registry dict
- Use `@handle_errors` decorator for sync functions
- Unwrap ExceptionGroup recursively (PEP 654)
- ALWAYS re-raise after classification (never swallow)

**Don't**:
- Swallow errors under any circumstance
- Decide business retry logic (only classify)
- Include raw secrets in error reports
