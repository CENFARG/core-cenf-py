# API Reference Overview

Complete Protocol and model surface for all 16 core-cenf infrastructure managers. This
page covers the public API contract — Protocols, key methods, models, and import paths.
For implementation details, see the per-manager pages under [Managers](../managers/config-manager).

## Import Convention

Every manager follows a consistent import structure:

```
core_infrastructure/{manager}/
├── ports.py       # Protocol (interface) — what your code imports
├── models.py      # Pydantic models for boundary validation
├── adapters/      # Concrete implementations
│   ├── in_memory_*.py   # Test double (zero deps)
│   └── production.py    # Real adapter
```

```python
# Always import the Protocol, never the adapter
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.config.models import CoreSettings

# Adapters are imported only at bootstrap / test setup
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.config.adapters.pydantic_config_adapter import PydanticConfigAdapter
```

## Common Infrastructure

These modules are shared by all managers, not tied to any single one.

### `core_infrastructure.common.context`

Context propagation with `contextvars`. No dependencies, synchronous only.

```python
from core_infrastructure.common.context import (
    # Getters
    get_correlation_id,   # → str (default "system-init")
    get_tenant_id,        # → str (default "global")
    get_principal_id,     # → str (default "")
    get_trace_id,         # → str (default "")
    get_span_id,          # → str (default "")

    # Setters
    set_correlation_id,   # (cid: str) → None
    set_tenant_id,        # (tid: str) → None
    set_principal_id,     # (pid: str) → None
    set_trace_id,         # (tid: str) → None
    set_span_id,          # (sid: str) → None

    # UUID generation
    new_correlation_id,   # → str (sets AND returns UUID4)

    # Snapshot
    get_context_snapshot,      # → dict[str, str]
    restore_context_snapshot,  # (snapshot: dict[str, str]) → None

    # Validation
    ContextValidation,  # Pydantic model for boundary validation
)
```

### `core_infrastructure.common.errors`

Structured exception hierarchy with five error types.

```python
from core_infrastructure.common.errors import (
    ErrorType,          # Enum: TRANSIENT, PERMANENT, VALIDATION, AUTH, RATE_LIMIT
    CenfError,          # Base class — error_type, retryable, details
    TransientError,     # Retryable: network timeout, DB deadlock
    PermanentError,     # Not retryable: missing resource, invalid config
    ValidationError,    # Input schema violation
    AuthError,          # Invalid/expired token, insufficient permissions
    RateLimitError,     # Bucket exhausted — retry with backoff
)
```

### `core_infrastructure.common.lifecycle`

Lifecycle contract implemented by every adapter.

```python
from core_infrastructure.common.lifecycle import (
    AsyncLifecycle,     # Protocol: start(), stop(), health()
    HealthStatus,       # Pydantic model: service, status, version, timestamp, details
    LifecycleManager,   # Aggregator: register(), health_all(), is_system_healthy()
)
```

`HealthStatus` fields:

| Field | Type | Description |
|---|---|---|
| `service` | `str` (1-128 chars) | Manager name: "config", "logger", "cache" |
| `status` | `Literal["healthy", "degraded", "unhealthy"]` | Current health |
| `version` | `str` (semver pattern) | Adapter version |
| `timestamp` | `datetime` (UTC) | When the check ran |
| `details` | `dict[str, str]` | Diagnostic context (no secrets) |

### `core_infrastructure.bootstrap`

Lifecycle orchestrator for all managers.

```python
from core_infrastructure.bootstrap import BootstrapOrchestrator

orchestrator = BootstrapOrchestrator(*managers)  # in dependency order
await orchestrator.run()        # startup → wait for signal → shutdown
await orchestrator.startup()    # parallel start via asyncio.TaskGroup
await orchestrator.shutdown()   # reverse order, best-effort
statuses = await orchestrator.health()  # → list[HealthStatus]
```

## Manager Protocols

### M01: ConfigManager

```python
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.config.models import CoreSettings
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `get_env` | `() → Literal["local","dev","staging","prod"]` | `str` | Current deployment environment |
| `get_string` | `(key, default?) → str` | `str` | Dot-notation string config |
| `get_number` | `(key, default?) → float` | `float` | Numeric config value |
| `get_boolean` | `(key, default?) → bool` | `bool` | Boolean config value |
| `get_json` | `(key, default?) → Any` | `Any` | JSON-deserialized value |
| `get_section` | `(namespace) → dict[str, Any]` | `dict` | All keys under namespace |
| `reload` | `async () → None` | `None` | Hot-reload from backing store |
| `get_json_schema` | `() → dict[str, Any]` | `dict` | JSON Schema for LLM discovery |

### M02: LoggerManager

```python
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.logger.models import LoggerSettings
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `debug` | `(msg, **kwargs) → None` | `None` | Debug-level structured log |
| `info` | `(msg, **kwargs) → None` | `None` | Info-level structured log |
| `warn` | `(msg, **kwargs) → None` | `None` | Warning-level structured log |
| `error` | `(msg, **kwargs) → None` | `None` | Error-level structured log |
| `mask` | `(value, visible_chars?) → str` | `str` | Mask sensitive value for safe logging |
| `bind` | `(**context) → LoggerManager` | `LoggerManager` | Create child logger with extra context |
| `get_logs` | `() → list[dict]` | `list[dict]` | All logged records (in-memory adapter) |

### M03: SecretManager

```python
from core_infrastructure.secrets.ports import SecretManager
from core_infrastructure.secrets.models import SecretConfig, SecretRef, SecretValue
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `get_secret` | `async (key) → str` | `str` | Retrieve credential (masked repr) |
| `set_secret` | `(key, value) → None` | `None` | Store credential |
| `rotate_secret` | `async (key, new_value) → None` | `None` | Atomically replace credential |
| `invalidate_cache` | `(key) → None` | `None` | Force next get_secret to fetch fresh |

### M04: ErrorHandlingManager

```python
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.errors.models import ErrorClassification, ErrorContext, ErrorReport
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `handle_errors` | `(**opts) → decorator` | `Callable` | Decorator: classify + report + re-raise |
| `classify` | `(exception) → ErrorType` | `ErrorType` | Map exception to error category |
| `report` | `(exception, context?) → None` | `None` | Emit metrics + log the error |
| `get_captured` | `() → list[Exception]` | `list` | Errors captured (CapturingErrorAdapter) |

### M05: ObservabilityManager

```python
from core_infrastructure.observability.ports import ObservabilityManager
from core_infrastructure.observability.models import ObservabilitySettings
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `increment_counter` | `(name, value?, attributes?) → None` | `None` | Increment a RED counter |
| `record_histogram` | `(name, value, attributes?) → None` | `None` | Record a duration/ distribution |
| `start_span` | `(name, attributes?) → context mgr` | `SpanContext` | Begin a trace span |
| `get_trace_id` | `() → str` | `str` | Current trace ID (hex) |
| `get_current_span` | `() → str` | `str` | Current span ID (hex) |
| `get_metrics` | `() → list[dict]` | `list[dict]` | All recorded metrics (in-memory) |
| `get_spans` | `() → list[dict]` | `list[dict]` | All recorded spans (in-memory) |

### M06: AuthManager

```python
from core_infrastructure.auth.ports import AuthManager
from core_infrastructure.auth.models import AuthConfig, TokenClaims
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `validate_token` | `async (token) → TokenClaims` | `TokenClaims` | Validate JWT, extract claims, set contextvars |
| `validate_scopes` | `(claims, required) → bool` | `bool` | Check if claims contain all required scopes |

`TokenClaims` fields: `sub`, `iss`, `aud`, `exp`, `iat`, `nbf`, `scopes`, `tenant_id`, `principal_id`.

### M07: CacheManager

```python
from core_infrastructure.cache.ports import CacheManager
from core_infrastructure.cache.models import CacheConfig, CacheEntry, StampedeConfig
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `get` | `(key) → Any` | `Any \| None` | Retrieve cached value |
| `set` | `(key, value, ttl?) → None` | `None` | Store value with optional TTL |
| `get_or_set` | `(key, factory, ttl?) → Any` | `Any` | Get or compute with XFetch stampede mitigation |
| `exists` | `(key) → bool` | `bool` | Check if key exists in cache |
| `delete` | `(key) → None` | `None` | Evict a key |

### M08: DatabaseManager

```python
from core_infrastructure.database.ports import DatabaseManager, GenericRepository, TransactionScope
from core_infrastructure.database.models import DatabaseConfig, PaginatedResult, RepositoryQuery
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `get_repository` | `(entity_type) → GenericRepository` | `GenericRepository` | Get typed repository |
| `transaction` | `() → async context mgr` | `TransactionScope` | Begin ACID transaction |

`GenericRepository` methods: `insert(data)`, `find_by_id(id)`, `find_all(filters?, order_by?, limit?, offset?)`, `count(filters?)`, `update(id, data)`, `delete(id)`.

### M09: FileStorageManager

```python
from core_infrastructure.filestorage.ports import FileStorageManager
from core_infrastructure.filestorage.models import FileRef, StorageConfig, UploadResult
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `upload` | `async (bucket, key, data, content_type?) → UploadResult` | `UploadResult` | Store blob |
| `download` | `async (bucket, key) → bytes` | `bytes` | Retrieve blob |
| `exists` | `async (bucket, key) → bool` | `bool` | Check blob existence |
| `delete` | `async (bucket, key) → None` | `None` | Remove blob |
| `list_objects` | `async (bucket, prefix?) → list[FileRef]` | `list[FileRef]` | List blobs in bucket |
| `generate_presigned_url` | `async (bucket, key, expiry) → str` | `str` | Generate time-limited access URL |

### M10: TaskQueueManager

```python
from core_infrastructure.taskqueue.ports import TaskQueueManager
from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus, QueueConfig
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `enqueue` | `async (queue, payload, max_retries?) → JobRef` | `JobRef` | Submit job |
| `dequeue` | `async (queue) → Job \| None` | `Job \| None` | Claim next job |
| `ack` | `async (job_id) → None` | `None` | Confirm successful completion |
| `nack` | `async (job_id, requeue?) → None` | `None` | Report failure |
| `schedule` | `async (queue, payload, execute_at, max_retries?) → JobRef` | `JobRef` | Deferred execution |
| `get_job` | `async (job_id) → Job \| None` | `Job \| None` | Fetch job by ID |
| `get_dlq_jobs` | `async (queue) → list[Job]` | `list[Job]` | Inspect dead letter queue |

### M11: ExternalAPIManager

```python
from core_infrastructure.external_api.ports import ExternalAPIManager
from core_infrastructure.external_api.models import ApiResponse, CircuitState, RequestConfig, RetryPolicy
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `get` | `async (url, headers?, timeout?) → ApiResponse` | `ApiResponse` | HTTP GET with circuit breaker |
| `post` | `async (url, body?, headers?, timeout?) → ApiResponse` | `ApiResponse` | HTTP POST with circuit breaker |
| `put` | `async (url, body?, headers?, timeout?) → ApiResponse` | `ApiResponse` | HTTP PUT with circuit breaker |
| `delete` | `async (url, headers?, timeout?) → ApiResponse` | `ApiResponse` | HTTP DELETE with circuit breaker |
| `get_circuit_state` | `(host) → CircuitState` | `CircuitState` | Inspect circuit breaker state |

`CircuitState`: `CLOSED` (healthy), `OPEN` (failing, reject fast), `HALF_OPEN` (testing recovery).

### M12: FeatureFlagManager

```python
from core_infrastructure.feature_flags.ports import FeatureFlagManager
from core_infrastructure.feature_flags.models import FeatureFlag, FlagConfig, FlagContext
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `is_enabled` | `(flag_key, context?) → bool` | `bool` | Evaluate flag (never throws) |
| `get_flag_value` | `(flag_key, context?) → Any` | `Any` | Get flag payload |
| `get_all_flags` | `(context?) → dict[str, bool]` | `dict` | Evaluate all registered flags |
| `set_flag` | `(flag) → None` | `None` | Register/update a flag |
| `reload` | `async () → None` | `None` | Hot-reload flags from source |

### M13: DependencyManager

```python
from core_infrastructure.dependency.ports import DependencyManager
from core_infrastructure.dependency.models import DependencyConfig, RegistryEntry
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `register` | `(namespace, key, target) → None` | `None` | Register a dependency |
| `resolve_class` | `(module_path, class_name) → Any` | `Any` | Lazily import and return class |
| `is_known` | `(namespace, key) → bool` | `bool` | Check registry |
| `list_keys` | `(namespace) → list[str]` | `list[str]` | List keys in namespace |

### M14: DynamicPromptingManager

```python
from core_infrastructure.dynamic_prompting.ports import DynamicPromptingManager, PromptBlock
from core_infrastructure.dynamic_prompting.models import PromptConfig
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `assemble` | `async (base, blocks, context_state) → str` | `str` | Conditionally assemble prompt |
| `validate_blocks` | `(blocks) → list[str]` | `list[str]` | Validate block definitions |

`PromptBlock` fields: `id`, `condition` (dict or None), `content`, `priority`.

### M15: AlertManager

```python
from core_infrastructure.alert.ports import AlertManager, AlertLevel, AlertRule
from core_infrastructure.alert.models import AlertChannel, AlertConfig
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `send_alert` | `async (level, title, message, metadata?) → None` | `None` | Fire-and-forget alert dispatch |
| `register_rule` | `(rule) → None` | `None` | Register condition→alert mapping |
| `evaluate_and_alert` | `async (event) → None` | `None` | Match event against rules, dispatch |

`AlertLevel`: `INFO`, `WARNING`, `CRITICAL`.

### M16: RateLimiterManager

```python
from core_infrastructure.ratelimit.ports import RateLimiterManager
from core_infrastructure.ratelimit.models import BucketState, RateLimitConfig, RateLimitHeaders
```

| Method | Signature | Returns | Description |
|---|---|---|---|
| `is_allowed` | `async (bucket_key, cost?) → bool` | `bool` | Check if operation is allowed |
| `configure_bucket` | `(bucket_key, capacity, refill_rate, window_type?) → None` | `None` | Create/update rate limit bucket |
| `get_remaining` | `async (bucket_key) → int` | `int` | Tokens remaining in bucket |
| `get_reset_time` | `async (bucket_key) → float` | `float` | Unix timestamp when bucket resets |

## Adapter Catalog

Every manager ships with in-memory test doubles. Production adapters depend on optional
extras.

| Manager | In-Memory Adapter | Production Adapter(s) | Optional Deps |
|---|---|---|---|
| ConfigManager | `InMemoryConfigAdapter` | `PydanticConfigAdapter` | pyyaml, python-dotenv |
| LoggerManager | `InMemoryLoggerAdapter` | `StructlogAdapter` | structlog |
| SecretManager | `InMemorySecretAdapter` | `EncryptedSecretAdapter` | cryptography |
| ErrorHandlingManager | `CapturingErrorAdapter` | `ClassificationAdapter` | — |
| ObservabilityManager | `InMemoryObservabilityAdapter` | `OTelAdapter` | opentelemetry |
| AuthManager | `StaticAuthAdapter` | `JwtAuthAdapter` | python-jose |
| CacheManager | `MemoryCacheAdapter` | `RedisCacheAdapter` | redis |
| DatabaseManager | `MemoryDatabaseAdapter` | `SQLAlchemyAdapter` | sqlalchemy, asyncpg |
| FileStorageManager | `MemoryStorageAdapter` | `LocalStorageAdapter`, `S3StorageAdapter`, `GcsStorageAdapter`, `AzureStorageAdapter` | aiofiles, aioboto3, gcloud-aio-storage, azure-storage-blob |
| TaskQueueManager | `MemoryTaskQueueAdapter` | — | — |
| ExternalAPIManager | `MockHTTPAdapter` | `ResilientHTTPAdapter` | aiohttp, tenacity |
| FeatureFlagManager | `MemoryFeatureFlagAdapter` | `FileFeatureFlagAdapter` | watchfiles, pyyaml |
| DependencyManager | `InMemoryDependencyAdapter` | `ImportlibDependencyAdapter` | — |
| DynamicPromptingManager | — | `ConditionalPromptAdapter` | — |
| AlertManager | — | `DispatchAlertAdapter` | aiohttp |
| RateLimiterManager | `InMemoryRateLimitAdapter` | `TokenBucketAdapter` | — |
