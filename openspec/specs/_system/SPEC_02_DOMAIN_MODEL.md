---
Spec_ID: SPEC_02
Title: Domain Model
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [domain, protocols, types, contextvars]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_02: Domain Model

## Purpose

Define all 16 manager Protocol definitions as domain types, the context propagation model (5 contextvars), lifecycle model (AsyncLifecycle), and error taxonomy that form the type-safe foundation of CENF Core Infrastructure.

## Context Propagation Model

The system SHALL use 5 `contextvars` for implicit propagation across async boundaries:

| ContextVar | Default | Purpose |
|------------|---------|---------|
| `correlation_id` | `"system-init"` | Request correlation across services |
| `tenant_id` | `"global"` | Multi-tenant data isolation |
| `principal_id` | `""` | Audit trail principal identity |
| `trace_id` | `""` | OpenTelemetry trace ID (hex) |
| `span_id` | `""` | OpenTelemetry span ID (hex) |

### Requirement: ContextVar Accessors

The system SHALL provide get/set functions for each contextvar with Pydantic validation at I/O boundaries via `ContextValidation` model.

#### Scenario: Snapshot and restore roundtrip

- GIVEN a context with correlation_id="abc", tenant_id="tenant-1", trace_id="trace-1", span_id="span-1", principal_id="user-1"
- WHEN `get_context_snapshot()` is called
- THEN it returns a dict with all 5 keys and their values
- AND `restore_context_snapshot(snapshot)` restores all 5 contextvars

#### Scenario: Validation at boundary

- GIVEN an external HTTP header with correlation_id of 200 characters
- WHEN `ContextValidation(correlation_id=value)` is called
- THEN it raises `ValidationError` (max_length=64)

### Requirement: New Correlation ID

The system SHALL provide `new_correlation_id()` that generates a UUID4, sets it on the contextvar, and returns it.

#### Scenario: Fresh correlation ID generation

- WHEN `new_correlation_id()` is called
- THEN it returns a valid UUID4 string
- AND `get_correlation_id()` returns the same UUID4

## Lifecycle Model

### AsyncLifecycle Protocol

Every manager SHALL implement `AsyncLifecycle` with three methods:

```python
@runtime_checkable
class AsyncLifecycle(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def health(self) -> HealthStatus: ...
```

**Rules:**
- `start()` MUST be idempotent (track `_started` flag)
- `stop()` MUST be safe to call multiple times (track `_stopped` flag)
- `health()` MUST NEVER raise — return `status="degraded"` on internal failure

### HealthStatus Model

```python
class HealthStatus(BaseModel):
    service: str = Field(..., min_length=1, max_length=128)
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+")
    timestamp: datetime
    details: dict[str, str] = Field(default_factory=dict)
    def is_healthy(self) -> bool: ...
```

#### Scenario: Health aggregation

- GIVEN 3 managers: config=healthy, logger=healthy, cache=degraded
- WHEN `LifecycleManager.is_system_healthy()` is called
- THEN it returns `False` (not all healthy)

## Error Taxonomy

All CENF infrastructure errors SHALL inherit from `CenfError` with 5 concrete subclasses:

| Error Class | ErrorType | Retryable | Examples |
|-------------|-----------|-----------|----------|
| `TransientError` | TRANSIENT | True | Network timeout, connection refused |
| `PermanentError` | PERMANENT | False | Missing config file, schema mismatch |
| `ValidationError` | VALIDATION | False | Invalid input, type coercion failure |
| `AuthError` | AUTH | False | Invalid token, expired credentials |
| `RateLimitError` | RATE_LIMIT | True | HTTP 429, quota exhausted |

### Requirement: Error Classification

The system SHALL classify built-in exceptions to ErrorType:
- `ConnectionError`, `TimeoutError`, `asyncio.TimeoutError` → TRANSIENT
- `ValueError`, `KeyError`, `TypeError` (input) → VALIDATION
- `PermissionError`, authentication failures → AUTH
- HTTP 429 → RATE_LIMIT
- `FileNotFoundError` (config), `NotImplementedError` → PERMANENT

#### Scenario: ExceptionGroup unwrapping

- GIVEN an `ExceptionGroup` containing `TransientError` and `ValidationError`
- WHEN `ErrorHandlingManager.unpack_group()` is called
- THEN it returns a flat list `[TransientError, ValidationError]`
- AND each error is classified independently

## Manager Protocol Registry

All 16 manager Protocols are defined in their respective `ports.py` files. Each Protocol SHALL:
1. Be `@runtime_checkable`
2. Include `get_json_schema()` static method
3. Have Google-style docstrings with `@ai-directive` annotations
4. Use Python 3.12+ type hints (PEP 695)

| # | Manager | Port File | Key Methods |
|---|---------|-----------|-------------|
| M01 | ConfigManager | `config/ports.py` | get_env, get_string, get_number, get_boolean, get_json, get_section, reload |
| M02 | LoggerManager | `logger/ports.py` | debug, info, warn, error, bind, mask |
| M03 | SecretManager | `secrets/ports.py` | get_secret, invalidate_cache, rotate_secret |
| M04 | ErrorHandlingManager | `errors/ports.py` | classify, report, handle, handle_errors |
| M05 | ObservabilityManager | `observability/ports.py` | increment_counter, record_histogram, start_span, flush |
| M06 | AuthManager | `auth/ports.py` | validate_token, get_claims, refresh_jwks, validate_scopes |
| M07 | CacheManager | `cache/ports.py` | get, set, delete, exists, clear, get_or_set |
| M08 | DatabaseManager | `database/ports.py` | transaction, get_repository |
| M09 | FileStorageManager | `filestorage/ports.py` | upload, download, delete, exists, generate_presigned_url, list_objects |
| M10 | TaskQueueManager | `taskqueue/ports.py` | enqueue, dequeue, ack, nack, schedule, get_job, get_dlq_jobs |
| M11 | ExternalAPIManager | `external_api/ports.py` | request, get, post, get_circuit_state |
| M12 | FeatureFlagManager | `feature_flags/ports.py` | is_enabled, get_flag_value, get_all_flags, refresh |
| M13 | DependencyManager | `dependency/ports.py` | resolve_class, register, is_known, list_keys, invalidate_cache |
| M14 | DynamicPromptingManager | `dynamic_prompting/ports.py` | assemble, validate_expressions |
| M15 | AlertManager | `alert/ports.py` | send_alert, register_rule, evaluate_and_alert |
| M16 | RateLimiterManager | `ratelimit/ports.py` | is_allowed, get_remaining, get_reset_time, configure_bucket |
