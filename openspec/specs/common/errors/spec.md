---
Spec_ID: SPEC_ERR
Title: Common Errors Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [errors, taxonomy, exceptions, classification]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_ERR: Common Errors

## Purpose

Define the error taxonomy base classes. All CENF infrastructure errors inherit from `CenfError` with 5 concrete subclasses. Pure Python exceptions — no Pydantic models needed.

## Python API

```python
from enum import Enum, auto

class ErrorType(Enum):
    TRANSIENT = auto()
    PERMANENT = auto()
    VALIDATION = auto()
    AUTH = auto()
    RATE_LIMIT = auto()

class CenfError(Exception):
    error_type: ErrorType = ErrorType.PERMANENT
    retryable: bool = False
    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None: ...
    def __repr__(self) -> str: ...

class TransientError(CenfError):
    error_type: ErrorType = ErrorType.TRANSIENT
    retryable: bool = True

class PermanentError(CenfError):
    error_type: ErrorType = ErrorType.PERMANENT
    retryable: bool = False

class ValidationError(CenfError):
    error_type: ErrorType = ErrorType.VALIDATION
    retryable: bool = False

class AuthError(CenfError):
    error_type: ErrorType = ErrorType.AUTH
    retryable: bool = False

class RateLimitError(CenfError):
    error_type: ErrorType = ErrorType.RATE_LIMIT
    retryable: bool = True
```

## Gherkin Scenarios

### Scenario: TransientError is retryable

- WHEN `e = TransientError("timeout")` is created
- THEN `e.retryable` is `True`
- AND `e.error_type` is `ErrorType.TRANSIENT`

### Scenario: PermanentError is not retryable

- WHEN `e = PermanentError("file not found")` is created
- THEN `e.retryable` is `False`
- AND `e.error_type` is `ErrorType.PERMANENT`

### Scenario: Details dict is JSON-serializable

- WHEN `e = CenfError("test", details={"key": "value", "code": "123"})` is created
- THEN `e.details` is `{"key": "value", "code": "123"}`
- AND `json.dumps(e.details)` succeeds (all str keys and values)

### Scenario: is_retryable via ErrorType

- GIVEN the ErrorHandlingManager classifies errors
- WHEN a `TransientError` is classified
- THEN `is_retryable` returns `True`
- AND when a `ValidationError` is classified
- THEN `is_retryable` returns `False`

### Scenario: __repr__ does not leak details

- WHEN `e = AuthError("invalid token", details={"token": "secret-123"})` is created
- THEN `repr(e)` includes the error type
- AND callers MUST NOT log `repr(e)` if details contain sensitive data

### Scenario: CenfError subclasses are catchable

- WHEN `raise TransientError("test")` is executed
- THEN `except CenfError:` catches it
- AND `except TransientError:` also catches it (more specific)

## Error Classification

This module DEFINES the taxonomy. The ErrorHandlingManager (M04) USES it to classify built-in exceptions.

| Error Class | ErrorType | Retryable |
|-------------|-----------|-----------|
| TransientError | TRANSIENT | True |
| PermanentError | PERMANENT | False |
| ValidationError | VALIDATION | False |
| AuthError | AUTH | False |
| RateLimitError | RATE_LIMIT | True |

## RED Metrics

None — this module defines types, it does not emit metrics. ErrorHandlingManager emits metrics when classifying.

## Test Requirements

- **Unit**: Test each error class has correct `error_type` and `retryable` values.
- **Integration**: Verify `json.dumps(error.details)` works for all error types.
- **E2E**: ErrorHandlingManager correctly classifies each CenfError subclass.

## Do's and Don'ts

**Do**:
- Use `details` dict for structured context (str keys and values only)
- Inherit from the correct CenfError subclass for each error scenario
- Check `error.retryable` before implementing retry logic

**Don't**:
- Add Pydantic models here (pure Python exceptions)
- Include raw secrets or tokens in `message` or `details`
- Create new error subclasses without updating ErrorHandlingManager's classification
