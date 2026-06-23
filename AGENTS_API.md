# Core-CENF API Catalog — Agent Reference
> For AI coding agents. Parseable in <5 seconds. 21 managers, 125+ methods.

## Quick Lookup
| ID | Manager | Purpose | Key Method |
|----|---------|---------|------------|
| M01 | ConfigManager | Read-only config (YAML+env) | `get_string(key)` |
| M02 | LoggerManager | Structured logging (dev/test/prod) | `logger.info(msg, **ctx)` |
| M03 | SecretManager | Encrypted credential storage | `get_secret(key)` → masked |
| M04 | ErrorHandlingManager | Classify & report errors | `handle_errors(**opts)` decorator |
| M05 | ObservabilityManager | OTel RED metrics & tracing | `increment_counter(name)` |
| M06 | AuthManager | JWT validation (HS256/RS256) | `validate_token(token)` → claims |
| M07 | CacheManager | KV cache + stampede mitigation | `get_or_set(key, factory, ttl)` |
| M08 | DatabaseManager | Transactions + generic repos | `transaction()` context mgr |
| M09 | FileStorageManager | Multi-cloud blob storage | `upload(bucket, key, data)` |
| M10 | TaskQueueManager | Async jobs + DLQ + schedule | `enqueue(queue, payload)` |
| M11 | ExternalAPIManager | Resilient HTTP + circuit breaker | `request(method, url)` |
| M12 | FeatureFlagManager | Runtime toggles (YAML→Unleash) | `is_enabled(flag, context)` |
| M13 | DependencyManager | Lazy safe import resolution | `resolve_class(module, class)` |
| M14 | DynamicPromptingManager | Conditional prompt assembly | `assemble(base, blocks, ctx)` |
| M15 | AlertManager | Slack/Discord/Email alerts | `send_alert(level, title, msg)` |
| M16 | RateLimiterManager | Token bucket rate limiting | `is_allowed(bucket_key)` |
| M17 | I18nManager | Multi-language translations | `t(key, **params)` |
| M18 | PermissionManager | RBAC+ABAC access control | `check_permission(...)` |
| M19 | LicenceManager | Signed licence validation | `load_license_from_string(...)` |
| M20 | UpdateManager | Desktop auto-update + rollback | `check_for_updates(...)` |
| M21 | BusEventManager | Decoupled pub/sub messaging | `publish(event_type, payload)` |

---

## M01 — ConfigManager (src/core_infrastructure/config)
**Dependencies**: None (root)
**Protocol**: `core_infrastructure.config.ports.ConfigManager`
**Models**: `core_infrastructure.config.models.CoreSettings`

> @ai-directive: The generic type parameters on get_json[T] and get_section[T] MUST be preserved by all adapter implementations for mypy strict mode.

> @ai-directive: When adding a new config key, update CoreSettings AND ensure both adapters handle the new key correctly.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| get_env | `() -> Env` | `Literal["local","dev","staging","prod"]` | — | Deployment environment |
| get_string | `(key: str, default_value: str \| None = None) -> str` | `str` | `ValidationError` | Dot-notation keys |
| get_number | `(key: str, default_value: float \| None = None) -> float` | `float` | `ValidationError` | Value not numeric |
| get_boolean | `(key: str, default_value: bool \| None = None) -> bool` | `bool` | `ValidationError` | Value not boolean |
| get_json | `(key: str, default_value: Any = None) -> Any` | `Any` | `ValidationError` | JSON-deserialized; invalid JSON |
| get_section | `(namespace: str) -> dict[str, Any]` | `dict[str, Any]` | — | All keys under namespace |
| reload | `() -> None` (async) | `None` | — | asyncio.Lock protected; INFO log |
| get_json_schema | `() -> dict[str, Any]` | `dict[str, Any]` | — | JSON Schema of CoreSettings; AX discovery |

**Adapters**:
- Production: `PydanticConfigAdapter` (`core_infrastructure.config.adapters.pydantic_config_adapter.PydanticConfigAdapter`)
- Test: `InMemoryConfigAdapter` (`core_infrastructure.config.adapters.in_memory_config_adapter.InMemoryConfigAdapter`)

---

## M02 — LoggerManager (src/core_infrastructure/logger)
**Dependencies**: ConfigManager
**Protocol**: `core_infrastructure.logger.ports.LoggerManager`
**Models**: `core_infrastructure.logger.models.LoggerSettings`

> @ai-directive: LoggerManager methods are SYNC only — structlog is sync, no async log methods are needed.

> @ai-directive: When adding a new log level, update both the Protocol and all adapter implementations.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| debug | `(message: str, **kwargs: Any) -> None` | `None` | — | MUST NEVER raise |
| info | `(message: str, **kwargs: Any) -> None` | `None` | — | MUST NEVER raise |
| warn | `(message: str, **kwargs: Any) -> None` | `None` | — | MUST NEVER raise |
| error | `(message: str, exc: Exception \| None = None, **kwargs: Any) -> None` | `None` | — | Optional exception; MUST NEVER raise |
| bind | `(**kwargs: Any) -> LoggerManager` | `LoggerManager` | — | Returns new logger with bound context |
| mask | `(value: str, visible_chars: int = 4) -> str` | `str` | — | Redacts all but last N chars |
| get_json_schema | `() -> dict[str, Any]` | `dict[str, Any]` | — | JSON Schema of LoggerSettings; AX discovery |

**Adapters**:
- Production: `StructlogAdapter` (`core_infrastructure.logger.adapters.structlog_adapter.StructlogAdapter`)
- Test: `InMemoryLoggerAdapter` (`core_infrastructure.logger.adapters.in_memory_logger_adapter.InMemoryLoggerAdapter`)

---

## M03 — SecretManager (src/core_infrastructure/secrets)
**Dependencies**: ConfigManager, LoggerManager
**Protocol**: `core_infrastructure.secrets.ports.SecretManager`
**Models**: `core_infrastructure.secrets.models.SecretConfig`

> @ai-directive: All secret adapters MUST mask secrets in __repr__ and logs. NEVER add a method that returns raw secrets without masking warnings.

> @ai-directive: When adding a new method, update all adapter implementations AND ensure SecretValue.__repr__ masking covers any new return paths.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| get_secret | `(key: str) -> str` (async) | `str` | `ValidationError`, `PermanentError` | Decrypted value; NEVER log raw value |
| invalidate_cache | `(key: str \| None = None) -> None` | `None` | — | None=all; concurrent-safe |
| rotate_secret | `(key: str, new_value: str) -> None` (async) | `None` | `PermanentError` | Old value evicted immediately |
| get_json_schema | `() -> dict[str, Any]` | `dict[str, Any]` | — | JSON Schema of SecretConfig; AX discovery |

**Adapters**:
- Production: `EncryptedSecretAdapter` (`core_infrastructure.secrets.adapters.encrypted_secret_adapter.EncryptedSecretAdapter`)
- Test: `InMemorySecretAdapter` (`core_infrastructure.secrets.adapters.in_memory_secret_adapter.InMemorySecretAdapter`)

---

## M04 — ErrorHandlingManager (src/core_infrastructure/errors)
**Dependencies**: LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.errors.ports.ErrorHandlingManager`
**Models**: `core_infrastructure.errors.models.ErrorClassification`, `core_infrastructure.errors.models.ErrorReport`

> @ai-directive: handle_errors is a synchronous decorator factory. It MUST be applied BEFORE any framework-level middleware that catches exceptions.

> @ai-directive: When adding a new error taxonomy member, update both ErrorClassification enum AND classify() implementation.

> @ai-directive: The decorator MUST use @functools.wraps to preserve function metadata. It MUST NEVER swallow errors.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| classify | `(error: Exception) -> ErrorClassification` | `ErrorClassification` | — | CenfError→direct; stdlib→heuristics |
| report | `(error: Exception, context: dict[str, Any] \| None = None) -> None` | `None` | — | Logs + emits RED counter |
| handle | `(error: Exception, context: dict[str, Any] \| None = None) -> ErrorReport` | `ErrorReport` | — | classify+report in single call |
| handle_errors | `(**decorator_opts: Any) -> Callable[[F], F]` | `Callable[[F], F]` | ALWAYS re-raises | Decorator factory; NEVER swallows |

**Adapters**:
- Production: `ClassificationAdapter` (`core_infrastructure.errors.adapters.classification_adapter.ClassificationAdapter`)
- Test: `CapturingErrorAdapter` (`core_infrastructure.errors.adapters.capturing_error_adapter.CapturingErrorAdapter`)

---

## M05 — ObservabilityManager (src/core_infrastructure/observability)
**Dependencies**: ConfigManager
**Protocol**: `core_infrastructure.observability.ports.ObservabilityManager`
**Models**: `core_infrastructure.observability.models.ObservabilitySettings`

> @ai-directive: ObservabilityManager methods are SYNC except flush(). NEVER throw on telemetry failure — degrade gracefully.

> @ai-directive: When adding a new metric type, update both the Protocol and all adapter implementations.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| increment_counter | `(name: str, value: float = 1.0, attributes: dict[str, Any] \| None = None) -> None` | `None` | — | MUST NEVER raise |
| record_histogram | `(name: str, value: float, attributes: dict[str, Any] \| None = None) -> None` | `None` | — | MUST NEVER raise |
| start_span | `(name: str, attributes: dict[str, Any] \| None = None) -> Any` | span object | — | Context manager; sets trace_id/span_id contextvars |
| get_current_span | `() -> Any` | span \| None | — | None if no active span |
| get_trace_id | `() -> str` | `str` | — | Hex string; "" if no trace |
| flush | `() -> None` (async) | `None` | — | Force-flush; idempotent |
| get_json_schema | `() -> dict[str, Any]` | `dict[str, Any]` | — | JSON Schema of ObservabilitySettings; AX discovery |

**Adapters**:
- Production: `OtelAdapter` (`core_infrastructure.observability.adapters.otel_adapter.OtelAdapter`)
- Test: `InMemoryObservabilityAdapter` (`core_infrastructure.observability.adapters.in_memory_observability_adapter.InMemoryObservabilityAdapter`)

---

## M06 — AuthManager (src/core_infrastructure/auth)
**Dependencies**: ConfigManager, SecretManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.auth.ports.AuthManager`
**Models**: `core_infrastructure.auth.models.TokenClaims`

> @ai-directive: All validate_token() methods MUST be async — token validation may involve network I/O (JWKS refresh). NEVER cache validation results indefinitely.

> @ai-directive: When adding a new validation check, update all adapter implementations AND TokenClaims model.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| validate_token | `(token: str) -> TokenClaims` (async) | `TokenClaims` | `AuthError` | Full validation: sig, exp, iss, aud, nbf |
| get_claims | `(token: str) -> TokenClaims` (async) | `TokenClaims` | `AuthError` | Extract without full re-validation |
| refresh_jwks | `() -> None` (async) | `None` | `AuthError` | Refresh JWKS cache; idempotent |
| validate_scopes | `(claims: TokenClaims, required: list[str]) -> bool` | `bool` | — | Sync; pure logic, no I/O |

**Adapters**:
- Production: `JwtAuthAdapter` (`core_infrastructure.auth.adapters.jwt_auth_adapter.JwtAuthAdapter`)
- Test: `StaticAuthAdapter` (`core_infrastructure.auth.adapters.static_auth_adapter.StaticAuthAdapter`)

---

## M07 — CacheManager (src/core_infrastructure/cache)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.cache.ports.CacheManager`
**Models**: `core_infrastructure.cache.models.CacheConfig`

> @ai-directive: get_or_set() MUST implement XFetch stampede mitigation. The factory callable MUST be async-compatible for I/O-bound value generation.

> @ai-directive: All methods are synchronous. get_or_set() factory may be sync or async; sync factories are called directly, async factories must be managed by the caller (this Protocol does NOT mandate asyncio).

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| get | `(key: str) -> Any` | `Any` | — | None on miss/expiry; never raises |
| set | `(key: str, value: Any, ttl: int \| None = None) -> None` | `None` | — | Overwrites; None ttl→CacheConfig.default_ttl |
| delete | `(key: str) -> None` | `None` | — | Idempotent |
| exists | `(key: str) -> bool` | `bool` | — | TTL-aware: False for expired |
| clear | `() -> None` | `None` | — | Removes ALL entries; emits cenf.cache.clear_total |
| get_or_set | `(key: str, factory: Callable[[], Any], ttl: int \| None = None) -> Any` | `Any` | — | XFetch stampede mitigation; emits hit/miss counters |

**Adapters**:
- Production: `RedisCacheAdapter` (`core_infrastructure.cache.adapters.redis_cache_adapter.RedisCacheAdapter`)
- Test: `MemoryCacheAdapter` (`core_infrastructure.cache.adapters.memory_cache_adapter.MemoryCacheAdapter`)

---

## M08 — DatabaseManager (src/core_infrastructure/database)
**Dependencies**: ConfigManager, SecretManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.database.ports.DatabaseManager`, `core_infrastructure.database.ports.GenericRepository[T]`, `core_infrastructure.database.ports.TransactionScope`
**Models**: `core_infrastructure.database.models.DatabaseConfig`

> @ai-directive: GenericRepository[T] is a Protocol with TypeVar T — adapter implementations MUST preserve the generic type for mypy strict mode.

> @ai-directive: All repository methods are async because they may involve network I/O (database queries). In-memory adapter simulates this with synchronous operations wrapped in coroutines.

### TransactionScope
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| commit | `() -> None` (async) | `None` | `PermanentError` | Atomic apply; idempotent |
| rollback | `() -> None` (async) | `None` | — | Discard all; idempotent |

### GenericRepository[T]
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| find_by_id | `(id: Any) -> T \| None` (async) | `T \| None` | — | None if not found |
| find_all | `(filters: dict[str, Any] \| None = None, order_by: str \| None = None, limit: int = 100, offset: int = 0) -> list[T]` (async) | `list[T]` | — | Empty list on no match |
| insert | `(entity: T) -> T` (async) | `T` | — | Returns entity with generated id |
| update | `(entity: T) -> T` (async) | `T` | `ValidationError` | Entity must exist |
| delete | `(id: Any) -> None` (async) | `None` | — | Idempotent |
| count | `(filters: dict[str, Any] \| None = None) -> int` (async) | `int` | — | 0 if none match |

### DatabaseManager
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| transaction | `() -> AbstractAsyncContextManager[TransactionScope]` | async ctx mgr | — | `async with db.transaction() as tx:` |
| get_repository | `(entity_type: type[T]) -> GenericRepository[T]` | `GenericRepository[T]` | — | Typed repository for entity T |

**Adapters**:
- Production: `SqlalchemyAdapter` (`core_infrastructure.database.adapters.sqlalchemy_adapter.SqlalchemyAdapter`)
- Test: `MemoryDatabaseAdapter` (`core_infrastructure.database.adapters.memory_database_adapter.MemoryDatabaseAdapter`)

---

## M09 — FileStorageManager (src/core_infrastructure/filestorage)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.filestorage.ports.FileStorageManager`
**Models**: `core_infrastructure.filestorage.models.FileRef`, `core_infrastructure.filestorage.models.UploadResult`

> @ai-directive: When implementing a new adapter, ensure upload() accepts bytes (not str) for data to avoid encoding ambiguity.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| upload | `(bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> UploadResult` (async) | `UploadResult` | `ValidationError`, `PermanentError` | Overwrites existing |
| download | `(bucket: str, key: str) -> bytes` (async) | `bytes` | `ValidationError`, `PermanentError` | Not found→ValidationError |
| delete | `(bucket: str, key: str) -> None` (async) | `None` | — | Idempotent |
| exists | `(bucket: str, key: str) -> bool` (async) | `bool` | — | Readable check |
| generate_presigned_url | `(bucket: str, key: str, expiry: int = 3600) -> str` (async) | `str` | `ValidationError` | file:// for local; NEVER log at INFO+ |
| list_objects | `(bucket: str, prefix: str = "") -> list[FileRef]` (async) | `list[FileRef]` | — | Empty list on no match |

**Adapters**:
- Production: `S3StorageAdapter` (`core_infrastructure.filestorage.adapters.s3_storage_adapter.S3StorageAdapter`)
- Test: `MemoryStorageAdapter` (`core_infrastructure.filestorage.adapters.memory_storage_adapter.MemoryStorageAdapter`)

---

## M10 — TaskQueueManager (src/core_infrastructure/taskqueue)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.taskqueue.ports.TaskQueueManager`
**Models**: `core_infrastructure.taskqueue.models.Job`, `core_infrastructure.taskqueue.models.JobRef`

> @ai-directive: Ack/nack MUST be idempotent — calling ack on an already-acked job is a no-op. DLQ jobs require manual inspection and reprocessing.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| enqueue | `(queue_name: str, payload: dict[str, Any], max_retries: int \| None = None) -> JobRef` (async) | `JobRef` | `ValidationError` | Queue created implicitly; payload must be JSON-serializable |
| dequeue | `(queue_name: str) -> Job \| None` (async) | `Job \| None` | — | Oldest PENDING; PENDING→RUNNING; None if empty |
| ack | `(job_id: str) -> None` (async) | `None` | — | RUNNING→COMPLETED; idempotent |
| nack | `(job_id: str, requeue: bool = True) -> None` (async) | `None` | — | requeue=True→PENDING (DEAD at max_retries); requeue=False→FAILED |
| schedule | `(queue_name: str, payload: dict[str, Any], execute_at: datetime, max_retries: int \| None = None) -> JobRef` (async) | `JobRef` | `ValidationError` | Deferred execution; dequeue skips future execute_at |
| get_job | `(job_id: str) -> Job \| None` (async) | `Job \| None` | — | None for unknown IDs; never raises |
| get_dlq_jobs | `(queue_name: str) -> list[Job]` (async) | `list[Job]` | — | DEAD jobs in DLQ |

**Adapters**:
- Production: `SaqAdapter` (`core_infrastructure.taskqueue.adapters.saq_adapter.SaqAdapter`)
- Test: `MemoryTaskQueueAdapter` (`core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter.MemoryTaskQueueAdapter`)

---

## M11 — ExternalAPIManager (src/core_infrastructure/external_api)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager, AuthManager
**Protocol**: `core_infrastructure.external_api.ports.ExternalAPIManager`
**Models**: `core_infrastructure.external_api.models.ApiResponse`, `core_infrastructure.external_api.models.CircuitState`, `core_infrastructure.external_api.models.RetryPolicy`

> @ai-directive: Circuit breaker is per-host — hosts are extracted from URL. get_circuit_state() is synchronous (reads cached state, no I/O).

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| request | `(method: str, url: str, headers: dict[str, str] \| None = None, body: dict[str, Any] \| None = None, timeout: float \| None = None, retry_policy: RetryPolicy \| None = None) -> ApiResponse` (async) | `ApiResponse` | — | Core method; circuit breaker + retry; never raises on HTTP errors |
| get | `(url: str, headers: dict[str, str] \| None = None, timeout: float \| None = None) -> ApiResponse` (async) | `ApiResponse` | — | Convenience wrapper |
| post | `(url: str, body: dict[str, Any] \| None = None, headers: dict[str, str] \| None = None, timeout: float \| None = None) -> ApiResponse` (async) | `ApiResponse` | — | Convenience wrapper |
| get_circuit_state | `(host: str) -> CircuitState` | `CircuitState` | — | Sync; reads cached state |

**Adapters**:
- Production: `ResilientHttpAdapter` (`core_infrastructure.external_api.adapters.resilient_http_adapter.ResilientHttpAdapter`)
- Test: `MockHTTPAdapter` (`core_infrastructure.external_api.adapters.mock_http_adapter.MockHTTPAdapter`)

---

## M12 — FeatureFlagManager (src/core_infrastructure/feature_flags)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.feature_flags.ports.FeatureFlagManager`
**Models**: `core_infrastructure.feature_flags.models.FlagContext`

> @ai-directive: is_enabled() MUST return False for unknown flags — never throw. get_flag_value() returns default on cache miss. refresh() is async for Unleash polling but may be sync for memory adapters.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| is_enabled | `(flag_key: str, context: FlagContext \| None = None) -> bool` | `bool` | — | False for unknown; never raises |
| get_flag_value | `(flag_key: str, context: FlagContext \| None = None, default: Any = None) -> Any` | `Any` | — | Default on cache miss |
| get_all_flags | `(context: FlagContext \| None = None) -> dict[str, bool]` | `dict[str, bool]` | — | All flags evaluated against context |
| refresh | `() -> None` (async) | `None` | — | No-op for memory adapters |

**Adapters**:
- Production: `FileFeatureFlagAdapter` (`core_infrastructure.feature_flags.adapters.file_feature_flag_adapter.FileFeatureFlagAdapter`)
- Test: `MemoryFeatureFlagAdapter` (`core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter.MemoryFeatureFlagAdapter`)

---

## M13 — DependencyManager (src/core_infrastructure/dependency)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.dependency.ports.DependencyManager`
**Models**: `core_infrastructure.dependency.models.RegistryEntry`

> @ai-directive: module_path must come from a registry allowlisted; never from direct user input.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| resolve_class | `(module_path: str, class_name: str) -> type` | `type` | `ValidationError`, `ModuleNotFoundError`, `AttributeError` | Allowlist BEFORE import; cached |
| register | `(namespace: str, key: str, target: tuple[str, str] \| Any) -> None` | `None` | — | Tuple=lazy; Any=pre-instantiated |
| is_known | `(namespace: str, key: str) -> bool` | `bool` | — | Sync; cheap; no import |
| list_keys | `(namespace: str) -> list[str]` | `list[str]` | — | All keys under namespace |
| invalidate_cache | `() -> None` (async) | `None` | — | Force re-import on next resolve_class |
| get_required_packages | `() -> list[str]` | `list[str]` | — | For Docker/pyproject.toml |
| get_json_schema | `() -> dict[str, Any]` (static) | `dict[str, Any]` | — | AX discovery |

**Adapters**:
- Production: `ImportlibDependencyAdapter` (`core_infrastructure.dependency.adapters.importlib_dependency_adapter.ImportlibDependencyAdapter`)
- Test: `InMemoryDependencyAdapter` (`core_infrastructure.dependency.adapters.in_memory_dependency_adapter.InMemoryDependencyAdapter`)

---

## M14 — DynamicPromptingManager (src/core_infrastructure/dynamic_prompting)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.dynamic_prompting.ports.DynamicPromptingManager`
**Models**: `core_infrastructure.dynamic_prompting.ports.PromptBlock` (inline Pydantic model)

> @ai-directive: Condition matching is dict-based for MVP — CEL is future.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| assemble | `(base_prompt: str \| None, blocks: list[PromptBlock], context_state: dict[str, Any]) -> str` (async) | `str` | — | Sorts by priority; dot-notation key resolution |
| validate_blocks | `(blocks: list[PromptBlock]) -> list[str]` | `list[str]` | — | Sync; empty=valid; checks dup IDs, priority |
| get_json_schema | `() -> dict[str, Any]` (static) | `dict[str, Any]` | — | AX discovery — PromptBlock model |

**PromptBlock model**:
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| id | `str` | required | Min length 1; unique |
| condition | `dict[str, Any] \| None` | `None` | None=always included; all pairs must match |
| content | `str` | required | Min length 1 |
| priority | `int` | `10` | Range 0-100; lower=first |

**Adapters**:
- Production/test: `ConditionalPromptAdapter` (`core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter.ConditionalPromptAdapter`)

---

## M15 — AlertManager (src/core_infrastructure/alert)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager, SecretManager
**Protocol**: `core_infrastructure.alert.ports.AlertManager`
**Models**: `core_infrastructure.alert.ports.AlertLevel` (StrEnum), `core_infrastructure.alert.ports.AlertRule` (Pydantic)

> @ai-directive: Dict-based condition matching for MVP. CEL integration is planned for a future release.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| send_alert | `(level: AlertLevel, title: str, message: str, metadata: dict[str, Any] \| None = None) -> None` (async) | `None` | — | Fire-and-forget; channel failures logged not raised |
| register_rule | `(rule: AlertRule) -> None` | `None` | — | Overwrites same rule_id |
| evaluate_and_alert | `(event_context: dict[str, Any]) -> None` (async) | `None` | — | Matches rules; respects throttle |
| get_json_schema | `() -> dict[str, Any]` (static) | `dict[str, Any]` | — | AX discovery — AlertConfig |

**AlertLevel**: `"info"` | `"warning"` | `"critical"`
**AlertRule fields**: `rule_id: str`, `condition: dict[str, Any]`, `level: AlertLevel` (default WARNING), `channels: list[str]`, `throttle_seconds: int` (0-3600, default 60)

**Adapters**:
- Production/test: `DispatchAlertAdapter` (`core_infrastructure.alert.adapters.dispatch_alert_adapter.DispatchAlertAdapter`)

---

## M16 — RateLimiterManager (src/core_infrastructure/ratelimit)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.ratelimit.ports.RateLimiterManager`
**Models**: `core_infrastructure.ratelimit.models.RateLimitConfig`

> @ai-directive: Use is_allowed before any rate-limited operation. Bucket keys are arbitrary strings.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| is_allowed | `(bucket_key: str, cost: float = 1.0) -> bool` (async) | `bool` | — | Consumes tokens if allowed |
| get_remaining | `(bucket_key: str) -> int` (async) | `int` | — | Read-only; does not consume |
| get_reset_time | `(bucket_key: str) -> float` (async) | `float` | — | Unix timestamp of full refill |
| configure_bucket | `(bucket_key: str, capacity: int, refill_rate: float, window_type: str = "token_bucket") -> None` | `None` | — | token_bucket or sliding_window |
| get_json_schema | `() -> dict[str, Any]` (static) | `dict[str, Any]` | — | AX discovery — RateLimitConfig |

**Adapters**:
- Production: `TokenBucketAdapter` (`core_infrastructure.ratelimit.adapters.token_bucket_adapter.TokenBucketAdapter`)
- Test: `InMemoryRateLimitAdapter` (`core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter.InMemoryRateLimitAdapter`)

---

## M17 — I18nManager (src/core_infrastructure/i18n)
**Dependencies**: ConfigManager, LoggerManager
**Protocol**: `core_infrastructure.i18n.ports.I18nManager`
**Models**: `core_infrastructure.i18n.models.I18nConfig`

> @ai-directive: NEVER throw on missing translation — return [missing: key] as a visible fallback so developers can spot untranslated strings.

> @ai-directive: When adding a new locale, update the YAML file AND ensure both adapters handle the new locale correctly.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| set_locale | `(locale: str) -> None` | `None` | — | Switch active language immediately |
| t | `(key: str, **params: Any) -> str` | `str` | — | NEVER raises; missing→`[missing: key]`; str.format() params |
| get_available_locales | `() -> list[str]` | `list[str]` | — | Sorted locale codes |
| load_translations | `(path: str \| dict[str, Any], locale: str) -> None` | `None` | — | YAML path or dict |
| get_json_schema | `() -> dict[str, Any]` | `dict[str, Any]` | — | JSON Schema of I18nConfig; AX discovery |

**Adapters**:
- Production: `YamlI18nAdapter` (`core_infrastructure.i18n.adapters.yaml_i18n_adapter.YamlI18nAdapter`)
- Test: `InMemoryI18nAdapter` (`core_infrastructure.i18n.adapters.in_memory_i18n_adapter.InMemoryI18nAdapter`)

---

## M18 — PermissionManager (src/core_infrastructure/permission)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.permission.ports.PermissionManager`, `core_infrastructure.permission.ports.PermissionDecision`
**Models**: `core_infrastructure.permission.models.PermissionConfig`
**Types**: `PrincipalType = Literal["human","agent","team"]`, `Action = Literal["read","write","create","delete","invoke","delegate"]`

> @ai-directive: Always ask PermissionManager before accessing protected resources. Treat human users, AI agents, and teams uniformly as principals with a type attribute. NEVER inherit all user permissions to agents automatically.

### PermissionDecision
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| is_allowed | `() -> bool` | `bool` | — | |
| reason | `() -> str` | `str` | — | e.g. "rbac_allow", "delegation_expired", "default_deny" |
| attributes | `() -> Mapping[str, Any]` | `Mapping[str, Any]` | — | purpose, on_behalf_of, policy_id, workflow_id |

### PermissionManager
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| check_permission | `(*, tenant_id: str, principal_id: str, principal_type: PrincipalType, resource_type: str, resource_id: str, action: Action, context: Mapping[str, Any] \| None = None) -> PermissionDecision` (async) | `PermissionDecision` | `ValidationError` | Default deny; pycasbin RBAC+delegations |
| check_delegation | `(*, tenant_id: str, delegator_id: str, delegate_id: str, delegate_type: PrincipalType, resource_type: str, resource_id: str, allowed_actions: list[Action], ttl_seconds: int, purpose: str, context: Mapping[str, Any] \| None = None) -> PermissionDecision` (async) | `PermissionDecision` | `ValidationError` | Explicit TTL + purpose required |
| list_effective_permissions | `(*, tenant_id: str, principal_id: str, principal_type: PrincipalType, resource_type: str \| None = None, resource_id: str \| None = None) -> list[Mapping[str, Any]]` (async) | `list[Mapping[str, Any]]` | — | For UIs and audit dashboards |
| get_json_schema | `() -> dict[str, Any]` (static) | `dict[str, Any]` | — | AX discovery |

**Adapters**:
- Production: `CasbinPermissionAdapter` (`core_infrastructure.permission.adapters.casbin_permission_adapter.CasbinPermissionAdapter`)
- Test: `InMemoryPermissionAdapter` (`core_infrastructure.permission.adapters.in_memory_permission_adapter.InMemoryPermissionAdapter`)

---

## M19 — LicenceManager (src/core_infrastructure/licence)
**Dependencies**: ConfigManager, SecretManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.licence.ports.LicenceManager`, `core_infrastructure.licence.ports.LicenseInfo`
**Models**: `core_infrastructure.licence.models.LicenceConfig`

> @ai-directive: Use LicenceManager to determine which features exist for a tenant. This manager validates cryptographically signed licence documents and exposes feature availability as simple flags. It does NOT decide who can use features.

> @ai-directive: Use LicenceManager to determine which features exist for a tenant. It does NOT decide who can use features — that is the PermissionManager's responsibility.

### LicenseInfo
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| tenant_id | `() -> str` | `str` | — | |
| tier | `() -> str` | `str` | — | "free", "pro", "enterprise" |
| features | `() -> Mapping[str, bool]` | `Mapping[str, bool]` | — | Feature→enabled mapping |
| expires_at | `() -> float \| None` | `float \| None` | — | UNIX epoch; None=perpetual |
| is_valid | `() -> bool` | `bool` | — | Not expired, not revoked |
| is_grace_period | `() -> bool` | `bool` | — | Expired but within grace_period_days |
| claims | `() -> Mapping[str, Any]` | `Mapping[str, Any]` | — | Full claims; NEVER exposes raw keys |

### LicenceManager
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| load_license_from_string | `(*, tenant_id: str, raw_license: str) -> LicenseInfo` (async) | `LicenseInfo` | `AuthError`, `ValidationError` | RS256 JWT validation |
| load_license_from_file | `(*, tenant_id: str, path: str) -> LicenseInfo` (async) | `LicenseInfo` | `AuthError`, `PermanentError` | .lic file → delegates to from_string |
| get_license | `(*, tenant_id: str) -> LicenseInfo \| None` (async) | `LicenseInfo \| None` | — | Cached; None=expired past grace |
| is_feature_enabled | `(*, tenant_id: str, feature_key: str) -> bool` (async) | `bool` | — | Single feature check |
| list_enabled_features | `(*, tenant_id: str) -> Mapping[str, bool]` (async) | `Mapping[str, bool]` | — | All features from licence |
| revoke_license | `(*, tenant_id: str) -> None` (async) | `None` | — | get_license→None after revoke |
| get_json_schema | `() -> dict[str, Any]` (static) | `dict[str, Any]` | — | AX discovery |

**Adapters**:
- Production: `JwtLicenceAdapter` (`core_infrastructure.licence.adapters.jwt_licence_adapter.JwtLicenceAdapter`)
- Test: `InMemoryLicenceAdapter` (`core_infrastructure.licence.adapters.in_memory_licence_adapter.InMemoryLicenceAdapter`)

---

## M20 — UpdateManager (src/core_infrastructure/update)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.update.ports.UpdateManager`, `core_infrastructure.update.ports.AvailableRelease`, `core_infrastructure.update.ports.UpdateArtifact`, `core_infrastructure.update.ports.UpdateResult`
**Models**: `core_infrastructure.update.models.UpdateConfig`
**Types**: `Channel = Literal["stable","beta","canary"]`

> @ai-directive: Use UpdateManager to discover and apply desktop app updates. Always verify signatures and hashes before installing. Never install unverified artifacts.

> @ai-directive: Always verify signatures and hashes before installing. Never install unverified artifacts. Use rollback() to recover from failed updates.

### UpdateArtifact (Protocol)
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| url | `() -> str` | `str` | — | Download URL |
| platform | `() -> str` | `str` | — | "windows", "macos", "linux" |
| arch | `() -> str` | `str` | — | "x64", "arm64" |
| kind | `() -> str` | `str` | — | "installer", "archive", "delta" |
| hash | `() -> str` | `str` | — | 64-char SHA-256 hex |
| signature | `() -> str \| None` | `str \| None` | — | Ed25519 base64; None if unsigned |

### AvailableRelease (Protocol)
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| version | `() -> str` | `str` | — | SemVer |
| channel | `() -> Channel` | `Channel` | — | stable, beta, canary |
| artifacts | `() -> list[UpdateArtifact]` | `list[UpdateArtifact]` | — | |
| metadata | `() -> Mapping[str, Any]` | `Mapping[str, Any]` | — | |

### UpdateResult (Protocol)
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| success | `() -> bool` | `bool` | — | |
| new_version | `() -> str \| None` | `str \| None` | — | None on failure |
| error | `() -> str \| None` | `str \| None` | — | MUST NOT contain sensitive paths/keys |

### UpdateManager
| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| get_current_version | `(*, app_id: str) -> str` (async) | `str` | — | SemVer |
| check_for_updates | `(*, app_id: str, channel: Channel = "stable") -> AvailableRelease \| None` (async) | `AvailableRelease \| None` | `TransientError` | None=up-to-date |
| download_update | `(*, app_id: str, release: AvailableRelease) -> UpdateArtifact` (async) | `UpdateArtifact` | `AuthError`, `PermanentError` | SHA-256 + Ed25519 verified |
| apply_update | `(*, app_id: str, artifact: UpdateArtifact) -> UpdateResult` (async) | `UpdateResult` | — | Auto-rollback on failure |
| rollback | `(*, app_id: str) -> UpdateResult` (async) | `UpdateResult` | `PermanentError` | Restore prev known-good |
| get_json_schema | `() -> dict[str, Any]` (static) | `dict[str, Any]` | — | AX discovery |

**Adapters**:
- Production: `HttpUpdateAdapter` (`core_infrastructure.update.adapters.http_update_adapter.HttpUpdateAdapter`)
- Test: `InMemoryUpdateAdapter` (`core_infrastructure.update.adapters.in_memory_update_adapter.InMemoryUpdateAdapter`)

---

## M21 — BusEventManager (src/core_infrastructure/bus_event)
**Dependencies**: ConfigManager, LoggerManager, ObservabilityManager
**Protocol**: `core_infrastructure.bus_event.ports.BusEventManager`
**Models**: `core_infrastructure.bus_event.models.EventEnvelope`, `core_infrastructure.bus_event.models.BusConfig`, `core_infrastructure.bus_event.models.CloudEvent`

> @ai-directive: publish() is fire-and-forget from the publisher's perspective. Subscriptions are exact-match only (no wildcards for MVP).

> @ai-directive: When adding a new adapter, implement ALL methods. The MemoryBusAdapter is the reference implementation.

| Method | Signature | Returns | Raises | Notes |
|--------|-----------|---------|--------|-------|
| publish | `(event_type: str, payload: dict[str, Any], metadata: dict[str, Any] \| None = None) -> str` (async) | `str` | `ValidationError` | Fire-and-forget; returns UUID4 event_id; payload must be JSON-serializable |
| subscribe | `(event_type: str, handler: Any, subscriber_id: str) -> str` (async) | `str` | — | Handler receives `EventEnvelope`; returns unique subscription_id; exact-match routing |
| unsubscribe | `(subscription_id: str) -> None` (async) | `None` | — | Idempotent — safe to call on unknown IDs |
| list_subscriptions | `() -> list[dict[str, Any]]` (async) | `list[dict[str, Any]]` | — | Each entry: `subscription_id`, `event_type`, `subscriber_id` |
| get_json_schema | `() -> dict[str, Any]` (static) | `dict[str, Any]` | — | JSON Schema of BusConfig; AX discovery |

**Adapters**:
- Dev/Test: `MemoryBusAdapter` (`core_infrastructure.bus_event.adapters.memory_bus_adapter.MemoryBusAdapter`) — in-process asyncio.Queue per event_type
- Production: `RedisBusAdapter` (`core_infrastructure.bus_event.adapters.redis_bus_adapter.RedisBusAdapter`) — Redis Pub/Sub with auto-reconnection
- Production: `NatsBusAdapter` (`core_infrastructure.bus_event.adapters.nats_bus_adapter.NatsBusAdapter`) — NATS JetStream with CloudEvents 1.0 + durable consumers

### Models

#### EventEnvelope
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| event_id | `str` (1–64) | required | UUID4 |
| event_type | `str` (1–256) | required | Routing key (e.g. `"user.created"`) |
| payload | `dict[str, Any]` | `{}` | JSON-serializable event data |
| metadata | `dict[str, Any] \| None` | `None` | Optional trace metadata |

#### BusConfig
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| max_queue_size | `int` (1–10000) | `1000` | Max pending events per event_type before publish blocks |
| default_handler_timeout | `float` (> 0.0) | `30.0` | Max seconds a handler can run before cancellation |

#### CloudEvent
| Field | Type | Default | Notes |
|-------|------|---------|-------|
| specversion | `str` | required | `"1.0"` |
| type | `str` (1–256) | required | Event type |
| source | `str` | required | Event source identifier |
| id | `str` (1–64) | required | Unique event ID |
| time | `str \| None` | `None` | RFC 3339 UTC timestamp |
| datacontenttype | `str` | `"application/json"` | Content type of data |
| data | `dict[str, Any]` | `{}` | Event payload |

---

## Error Taxonomy
| Exception Class | Base | Retryable | When |
|----------------|------|-----------|------|
| `TransientError` | `CenfError` | ✅ | Network timeout, DB deadlock, 503 |
| `PermanentError` | `CenfError` | ❌ | Missing resource, invalid config |
| `ValidationError` | `CenfError` | ❌ | Schema violation (Pydantic) |
| `AuthError` | `CenfError` | ❌ | Expired token, wrong signature |
| `RateLimitError` | `CenfError` | ❌ | Bucket exhausted |

All from: `core_infrastructure.common.errors`

## Context Propagation (contextvars)
| Function | Args | Returns | Notes |
|----------|------|---------|-------|
| `context.set_correlation_id(id)` | `str` | — | Auto-injected into logs |
| `context.set_tenant_id(id)` | `str` | — | Set by AuthManager |
| `context.get_correlation_id()` | — | `str` | "" if not set |
| `context.set_trace_id(id)` | `str` | — | Set by ObservabilityManager |
| `context.set_span_id(id)` | `str` | — | Set by ObservabilityManager |

From: `core_infrastructure.common.context`

## Commit Gate
```
ruff check src/ tests/         # ZERO errors
mypy src/core_infrastructure/ --strict  # ZERO errors
python -m pytest tests/ -q     # ALL green
```
