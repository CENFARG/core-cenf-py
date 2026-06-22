---
sidebar_position: 4
---

# ErrorHandlingManager (M04)

Structured error classification and reporting using the CenfError taxonomy. The `@handle_errors` decorator factory provides automatic classification, logging, and RED metric emission — and **NEVER swallows errors**.

## Protocol

`ErrorHandlingManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.errors.ports`.

### `classify(error: Exception) → ErrorClassification`

Classify an exception using the CenfError taxonomy.

```python
def classify(self, error: Exception) -> ErrorClassification: ...
```

For CenfError subclasses, the mapping is direct (`TransientError` → `TRANSIENT`). For standard library exceptions, heuristics apply (e.g., `TimeoutError` → `TRANSIENT`).

---

### `report(error: Exception, context: dict[str, Any] | None = None) → None`

Log and emit metrics for a classified error.

```python
def report(self, error: Exception, context: dict[str, Any] | None = None) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `error` | `Exception` | The exception to report |
| `context` | `dict[str, Any] \| None` | Optional dict with `correlation_id`, `tenant_id`, `source` keys |

---

### `handle(error: Exception, context: dict[str, Any] | None = None) → ErrorReport`

Classify and report an error in a single call.

```python
def handle(self, error: Exception, context: dict[str, Any] | None = None) -> ErrorReport: ...
```

**Returns:** `ErrorReport` — structured error report for observability backends.

---

### `handle_errors(**decorator_opts: Any) → Callable[[F], F]`

Return a decorator that classifies, logs, and **re-raises** errors.

```python
def handle_errors(self, **decorator_opts: Any) -> Callable[[F], F]: ...
```

When the wrapped function raises, the decorator:
1. Classifies the exception via `classify()`
2. Logs it via LoggerManager
3. Emits a RED counter via ObservabilityManager (`cenf.error.classified_total{error_type="..."}`)
4. **RE-RAISES** the exception (NEVER swallows)

| Param | Type | Description |
|-------|------|-------------|
| `**decorator_opts` | `Any` | Options: `reraise=True`, `log_level="ERROR"` |

**@ai-directive:** The decorator MUST use `@functools.wraps` to preserve function metadata.

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing error handler configuration.

## ErrorClassification

```python
class ErrorClassification(Enum):
    TRANSIENT = auto()    # Retryable — network timeout, DB deadlock
    PERMANENT = auto()    # Not retryable — missing resource, invalid config
    VALIDATION = auto()   # Schema violation — Pydantic
    AUTH = auto()         # Expired token, wrong signature
    RATE_LIMIT = auto()   # Bucket exhausted
```

| Classification | Retry? | Examples |
|----------------|--------|----------|
| `TRANSIENT` | Yes | `TimeoutError`, `ConnectionError`, DB deadlocks |
| `PERMANENT` | No | Missing resource, invalid configuration |
| `VALIDATION` | No | Pydantic `ValidationError` |
| `AUTH` | No | `AuthError` — expired token, wrong signature |
| `RATE_LIMIT` | Yes (after backoff) | Bucket exhausted |

## ExceptionGroup Unwrapping (PEP 654)

The `ClassificationAdapter` unwraps `ExceptionGroup` instances (PEP 654) before classification. Each sub-exception is classified individually, and the worst classification is returned:
- Any `AUTH` or `PERMANENT` in the group → result is `AUTH` / `PERMANENT`
- All `TRANSIENT` → result is `TRANSIENT`

## Models

### `ErrorContext`

**File:** `core_infrastructure.errors.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `correlation_id` | `str` (max 64) | `""` | Trace correlation identifier |
| `tenant_id` | `str` (max 64) | `""` | Multi-tenant identifier |
| `source` | `str` (max 256) | `""` | Component or function name originating the error |

### `ErrorReport`

| Field | Type | Description |
|-------|------|-------------|
| `error_type` | `str` *(required)* | Classification value (e.g., `"TRANSIENT"`) |
| `message` | `str` *(required)* | Human-readable description (no secrets) |
| `source` | `str` (max 256) | Originating component identifier |
| `correlation_id` | `str` (max 64) | Trace correlation identifier |
| `tenant_id` | `str` (max 64) | Tenant context at time of error |

## Adapters

| Adapter | Behavior | Use Case |
|---------|----------|----------|
| `ClassificationAdapter` | Full taxonomy classification + logging + metrics | Production |
| `CapturingErrorAdapter` | Captures errors without re-raising | Testing — assert on captured errors |

## Usage Example

```python
from core_infrastructure.errors.adapters.classification_adapter import ClassificationAdapter

# Bootstrap
errors = ClassificationAdapter(
    config_manager=config,
    logger_manager=logger,
    observability_manager=obs,
)

# --- Decorator pattern (RECOMMENDED) ---

@errors.handle_errors(reraise=True, log_level="ERROR")
def process_payment(payment_id: str) -> None:
    # If this raises, the decorator:
    # 1. Classifies the exception
    # 2. Logs it via LoggerManager
    # 3. Emits RED counter via ObservabilityManager
    # 4. RE-RAISES (never swallows)
    raise TransientError("Payment gateway timeout")

# --- Manual handling ---

try:
    result = call_external_api()
except Exception as e:
    # Classify only
    classification = errors.classify(e)
    # → ErrorClassification.TRANSIENT

    # Report only (logs + metrics)
    errors.report(e, context={"source": "payment_processor"})

    # Or do both in one call
    report = errors.handle(e, context={"source": "payment_processor"})
    # → ErrorReport(error_type="TRANSIENT", message="...", ...)
```

### Testing with CapturingErrorAdapter

```python
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter

errors = CapturingErrorAdapter(config, logger, obs)

@errors.handle_errors()
def faulty_function():
    raise ValidationError("Invalid input")

# The error is captured, NOT re-raised
faulty_function()
assert len(errors.captured_errors) == 1
assert errors.captured_errors[0].error_type == "VALIDATION"
```

## @ai-directive

- **`@handle_errors` NEVER swallows — always re-raises.** Use `CapturingErrorAdapter` in tests if you need to capture instead.
- `handle_errors` is a synchronous decorator factory. It MUST be applied BEFORE any framework-level middleware that catches exceptions.
- When adding a new error taxonomy member, update both `ErrorClassification` enum AND `classify()` implementation.

## Related

- [LoggerManager](logger-manager.md) — receives classified error log records
- [ObservabilityManager](observability-manager.md) — receives RED counter emissions
- [TaskQueueManager](task-queue-manager.md) — uses TRANSIENT for retry decisions
