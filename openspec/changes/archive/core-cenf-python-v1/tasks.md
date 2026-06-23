# Tasks: CENF Core Infrastructure — 12 Horizontal Managers (Python 3.12+)

> **Execution**: Auto (A2) | **Delivery**: Chained PRs C3 | **Chain**: stacked-to-main
> **Budget**: 400 lines/review | **TDD**: strict RED → GREEN → REFACTOR

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Total estimated changed lines | ~6,200 (88 files: 63 source + 25 test) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Number of PR slices | 5 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Chained PR Plan

| Slice | Goal | Lines | Base | Depends On | Verification |
|-------|------|-------|------|------------|-------------|
| PR #1 | Foundation — common + ConfigManager | ~780 | `main` | None | `pytest tests/unit/test_config.py tests/unit/test_context.py tests/unit/test_lifecycle.py -v` |
| PR #2 | Cross-Cutting — Logger, Obs, Secret, Error, Auth | ~2,060 | `main` | PR #1 merged | `pytest tests/unit/test_logger.py tests/unit/test_observability.py tests/unit/test_secret.py tests/unit/test_error_handling.py tests/unit/test_auth.py -v` |
| PR #3 | Data — Cache, Database, FileStorage | ~1,130 | `main` | PR #1, #2 merged | `pytest tests/unit/test_cache.py tests/unit/test_database.py tests/unit/test_filestorage.py -v` |
| PR #4 | Service — TaskQueue, ExternalAPI, FeatureFlag | ~1,130 | `main` | PR #1, #2, #3 merged | `pytest tests/unit/test_taskqueue.py tests/unit/test_external_api.py tests/unit/test_feature_flag.py -v` |
| PR #5 | Bootstrap + E2E + Finalize | ~860 | `main` | All merged | `pytest tests/ -v --cov=core_infrastructure --cov-report=term` |

---

## PR #1: Foundation — common + ConfigManager (~780 lines, 6 tasks)

### TASK_001: Context Propagation Module
- **PR Slice**: PR #1
- **Files to create**: `src/core_infrastructure/common/__init__.py`, `src/core_infrastructure/common/context.py`, `tests/unit/test_context.py`
- **Dependencies**: None (zero-dependency module)
- **Estimated lines**: ~150 (10 + 80 + 60)
- **RED behavior**: `pytest tests/unit/test_context.py` fails with `ModuleNotFoundError`
- **GREEN behavior**: Four `ContextVar[str]` with get/set accessors; `ContextValidation` model validates min/max length; `get_context_snapshot()`/`restore_context_snapshot()` roundtrip; `new_correlation_id()` uses UUID4; contextvars propagate across `await` in same task
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; Google-style docstrings with `@ai-directive`; file < 250 lines
- **Git commit message**: `feat(common): add contextvars propagation via common.context`
- **Verification**: `python -m pytest tests/unit/test_context.py -v`

### TASK_002: Error Taxonomy Base Classes
- **PR Slice**: PR #1
- **Files to create**: `src/core_infrastructure/common/errors.py`
- **Dependencies**: None
- **Estimated lines**: ~70
- **RED behavior**: `ImportError` — module does not exist
- **GREEN behavior**: `ErrorType` enum (TRANSIENT, PERMANENT, VALIDATION, AUTH, RATE_LIMIT); `CenfError(Exception)` with `error_type`, `retryable`, `details: dict[str,str]`; 5 concrete subclasses; `details` values are JSON-serializable strings; no Pydantic models (pure Python)
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations
- **Git commit message**: `feat(common): add CenfError taxonomy with ErrorType enum`
- **Verification**: `python -c "from core_infrastructure.common.errors import ErrorType, CenfError; e = CenfError('test', details={'k':'v'}); assert e.error_type == ErrorType.PERMANENT"`

### TASK_003: AsyncLifecycle Protocol + HealthStatus
- **PR Slice**: PR #1
- **Files to create**: `src/core_infrastructure/common/lifecycle.py`, `tests/unit/test_lifecycle.py`
- **Dependencies**: TASK_001 (`common/__init__.py` exists)
- **Estimated lines**: ~120 (60 + 60)
- **RED behavior**: `pytest tests/unit/test_lifecycle.py` fails due to `ModuleNotFoundError`
- **GREEN behavior**: `HealthStatus(BaseModel)` with `service`, `status: Literal["healthy","degraded","unhealthy"]`, `version`, `timestamp`, `details`, `is_healthy()` method; `AsyncLifecycle` `@runtime_checkable` Protocol with `start()`/`stop()`/`health()`; `start()` idempotent via `_started` flag; `stop()` safe to call multiple times; `health()` never raises
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; file < 250 lines
- **Git commit message**: `feat(common): add AsyncLifecycle Protocol and HealthStatus model`
- **Verification**: `python -m pytest tests/unit/test_lifecycle.py -v`

### TASK_004: ConfigManager Protocol + CoreSettings Model
- **PR Slice**: PR #1
- **Files to create**: `src/core_infrastructure/config/__init__.py`, `src/core_infrastructure/config/ports.py`, `src/core_infrastructure/config/models.py`, `src/core_infrastructure/config/adapters/__init__.py`
- **Dependencies**: TASK_001, TASK_002, TASK_003 (`common/` package exists)
- **Estimated lines**: ~105 (15 + 50 + 30 + 10)
- **RED behavior**: `ImportError` — config package does not exist
- **GREEN behavior**: `ConfigManager` runtime-checkable Protocol with `get_env()`, `get_string()`, `get_number()`, `get_boolean()`, `get_json[T]()`, `get_section[T]()`, `reload()`, `get_json_schema()`; `CoreSettings(BaseModel)` with `env`, `app_name`, `version`, `log_level` fields and validation; `get_json_schema()` returns valid JSON Schema
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; Google-style docstrings
- **Git commit message**: `feat(config): add ConfigManager Protocol and CoreSettings Pydantic model`
- **Verification**: `python -c "from core_infrastructure.config.ports import ConfigManager; from core_infrastructure.config.models import CoreSettings; import json; json.dumps(CoreSettings.model_json_schema())"`

### TASK_005: ConfigManager Adapters (Pydantic + InMemory)
- **PR Slice**: PR #1
- **Files to create**: `src/core_infrastructure/config/adapters/pydantic_settings_adapter.py`, `src/core_infrastructure/config/adapters/in_memory_config_adapter.py`, `tests/unit/test_config.py`
- **Dependencies**: TASK_004 (protocols and models exist)
- **Estimated lines**: ~300 (120 + 60 + 120)
- **RED behavior**: `pytest tests/unit/test_config.py` fails — no adapter satisfies Protocol
- **GREEN behavior**: `PydanticSettingsAdapter` loads YAML + env vars (12-factor precedence), validates via CoreSettings, protects reload with `asyncio.Lock`; `InMemoryConfigAdapter` dict-based; all `get_*` return correct types; `KeyError`→`ValidationError`, `FileNotFoundError`→`PermanentError`, `yaml.YAMLError`→`PermanentError`; `get_json_schema()` returns valid schema
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; adapter < 250 lines; test covers error paths and reload concurrency; `InMemoryConfigAdapter` injectable for downstream tests
- **Git commit message**: `feat(config): add PydanticSettingsAdapter and InMemoryConfigAdapter`
- **Verification**: `python -m pytest tests/unit/test_config.py -v`

### TASK_006: Package Exports Update (Foundation)
- **PR Slice**: PR #1
- **Files to modify**: `src/core_infrastructure/__init__.py`
- **Dependencies**: TASK_004, TASK_005
- **Estimated lines**: ~40 (modify existing 36-line file)
- **RED behavior**: `from core_infrastructure import ConfigManager, CoreSettings` fails
- **GREEN behavior**: `ConfigManager`, `CoreSettings`, `PydanticSettingsAdapter`, `InMemoryConfigAdapter`, `CenfError`, `AsyncLifecycle`, `HealthStatus` in `__all__`; public re-exports work; no circular imports
- **REFACTOR criteria**: `ruff check` clean; `mypy --strict` passes on modified file
- **Git commit message**: `chore: update package exports for Foundation (PR #1)`
- **Verification**: `python -c "from core_infrastructure import ConfigManager, CoreSettings, PydanticSettingsAdapter, CenfError, AsyncLifecycle, HealthStatus"`

---

## PR #2: Core Cross-Cutting — Logger, Observability, Secret, Error, Auth (~2,060 lines, 5 tasks)

> **Implementation order**: TASK_007 → TASK_008 → TASK_009 → TASK_010 → TASK_011 (respects bootstrap sequence M02→M05→M03→M04→M06)

### TASK_007: LoggerManager (ports + models + Structlog + InMemory + tests)
- **PR Slice**: PR #2
- **Files to create**: `src/core_infrastructure/logger/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/structlog_adapter.py`, `adapters/in_memory_logger_adapter.py`, `tests/unit/test_logger.py`
- **Dependencies**: PR #1 merged (ConfigManager, common modules available)
- **Estimated lines**: ~345 (15 + 40 + 30 + 10 + 100 + 50 + 100)
- **RED behavior**: `pytest tests/unit/test_logger.py` fails with `ModuleNotFoundError`
- **GREEN behavior**: `LoggerManager` Protocol with `debug()`/`info()`/`warn()`/`error()`/`bind()`/`mask()`/`get_json_schema()`; `StructlogAdapter` reads `LoggerSettings` from Config, selects dev/test/prod processors, injects contextvars (`correlation_id`, `tenant_id`, `trace_id`, `span_id`) via custom structlog processor; `InMemoryLoggerAdapter` collects logs in list for assertions; `mask()` shows last N chars; LoggerManager never raises
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; all files < 250 lines
- **Git commit message**: `feat(logger): add LoggerManager Protocol with Structlog and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_logger.py -v`

### TASK_008: ObservabilityManager (ports + models + OTel + InMemory + tests)
- **PR Slice**: PR #2
- **Files to create**: `src/core_infrastructure/observability/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/otel_adapter.py`, `adapters/in_memory_observability_adapter.py`, `tests/unit/test_observability.py`
- **Dependencies**: PR #1 merged, TASK_007 (LoggerManager)
- **Estimated lines**: ~445 (15 + 50 + 30 + 10 + 150 + 90 + 100)
- **RED behavior**: `pytest tests/unit/test_observability.py` fails
- **GREEN behavior**: `ObservabilityManager` Protocol with `increment_counter()`/`record_histogram()`/`start_span()`/`get_current_span()`/`get_trace_id()`/`flush()`/`get_json_schema()`; `OTelAdapter` initializes `TracerProvider` + `MeterProvider` + `W3CTraceContextPropagator` in `start()`, lazy if no `exporter_endpoint`; `InMemoryObservabilityAdapter` collects spans/metrics in memory; `flush()` called on `stop()`; `trace_id`/`span_id` synced to contextvars
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; `REDMetrics` counters use `cenf.*` namespace
- **Git commit message**: `feat(observability): add ObservabilityManager with OTel SDK and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_observability.py -v`

### TASK_009: SecretManager (ports + models + Vault + InMemory + tests)
- **PR Slice**: PR #2
- **Files to create**: `src/core_infrastructure/secrets/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/vault_adapter.py`, `adapters/in_memory_secret_adapter.py`, `tests/unit/test_secret.py`
- **Dependencies**: PR #1 merged, TASK_007 (LoggerManager)
- **Estimated lines**: ~415 (15 + 40 + 30 + 10 + 140 + 80 + 100)
- **RED behavior**: `pytest tests/unit/test_secret.py` fails
- **GREEN behavior**: `SecretManager` Protocol with `get_secret()`/`get_secret_bytes()`/`rotate_secret()`/`delete_secret()`/`health_check()`/`get_json_schema()`; `VaultAdapter` with TTL cache (`asyncio.Lock` + dict), reads from backend on miss; `InMemorySecretAdapter` dict-based with TTL simulation; `KeyError`→`ValidationError`, `ConnectionError`→`TransientError`, `Forbidden`→`AuthError`; `rotate_secret()` invalidates cache; `health_check()` pings without retrieving
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; TTL expiration verified
- **Git commit message**: `feat(secrets): add SecretManager Protocol with Vault and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_secret.py -v`

### TASK_010: ErrorHandlingManager (ports + models + Taxonomy + InMemory + tests)
- **PR Slice**: PR #2
- **Files to create**: `src/core_infrastructure/errors/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/taxonomy_adapter.py`, `adapters/in_memory_error_adapter.py`, `tests/unit/test_error_handling.py`
- **Dependencies**: PR #1 merged, TASK_007 (Logger), TASK_008 (Observability — uses `InMemoryObservabilityAdapter` in tests)
- **Estimated lines**: ~425 (15 + 50 + 30 + 10 + 130 + 70 + 120)
- **RED behavior**: `pytest tests/unit/test_error_handling.py` fails
- **GREEN behavior**: `ErrorHandlingManager` Protocol with `classify()`/`handle_errors()` (decorator)/`unpack_group()`/`register_handler()`/`get_pending_count()`/`get_json_schema()`; `TaxonomyAdapter` maps built-in exceptions to ErrorType via registry dict; `handle_errors()` decorator uses tenacity for TRANSIENT/RATE_LIMIT retry; `unpack_group()` flattens ExceptionGroup (PEP 654); `register_handler()` stores callbacks per ErrorType; RED metrics `cenf.error.classified_total` + `cenf.error.pending_count` gauge
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; ParamSpec + TypeVar for decorator typing; every error path classified correctly
- **Git commit message**: `feat(errors): add ErrorHandlingManager with taxonomy and tenacity retry decorator`
- **Verification**: `python -m pytest tests/unit/test_error_handling.py -v`

### TASK_011: AuthManager (ports + models + JOSE + InMemory + tests)
- **PR Slice**: PR #2
- **Files to create**: `src/core_infrastructure/auth/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/jose_adapter.py`, `adapters/in_memory_auth_adapter.py`, `tests/unit/test_auth.py`
- **Dependencies**: PR #1 merged, TASK_007 (Logger), TASK_008 (Observability), TASK_009 (SecretManager)
- **Estimated lines**: ~435 (15 + 40 + 30 + 10 + 140 + 80 + 120)
- **RED behavior**: `pytest tests/unit/test_auth.py` fails
- **GREEN behavior**: `AuthManager` Protocol with `validate_token()`/`check_scope()`/`issue_m2m_token()`/`refresh_jwks()`/`decode_token_unsafe()`/`get_json_schema()`; `JoseAdapter` validates JWT signature + `exp`/`iss`/`aud`, fetches JWKS on key mismatch; `issue_m2m_token()` signs with secret from SecretManager; `decode_token_unsafe()` uses unverified claims; `AuthError`→invalid signature/expired/missing scope; `TransientError`→JWKS unreachable; `InMemoryAuthAdapter` hardcoded keys for tests
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; JWT clock-skew tolerance verified; `python-jose` imports guarded
- **Git commit message**: `feat(auth): add AuthManager Protocol with JOSE JWT and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_auth.py -v`

---

## PR #3: Data Layer — Cache, Database, FileStorage (~1,130 lines, 3 tasks)

### TASK_012: CacheManager (ports + models + Redis + InMemory + tests)
- **PR Slice**: PR #3
- **Files to create**: `src/core_infrastructure/cache/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/redis_adapter.py`, `adapters/in_memory_cache_adapter.py`, `tests/unit/test_cache.py`
- **Dependencies**: PR #1 + #2 merged (Config, Logger, ErrorHandling available)
- **Estimated lines**: ~370 (15 + 40 + 30 + 10 + 150 + 100 + 120)
- **RED behavior**: `pytest tests/unit/test_cache.py` fails
- **GREEN behavior**: `CacheManager` Protocol with `get()`/`set()`/`delete()`/`exists()`/`get_or_fetch()`/`clear()`/`get_json_schema()`; `RedisAdapter` wraps `redis`+`aiocache` with per-key `asyncio.Lock` stampede mitigation + XFetch probabilistic early expiration; `InMemoryCacheAdapter` dict with TTL simulation; graceful degradation on Redis failure (return None); `TransientError`→connection lost; `ValidationError`→non-serializable value; namespace prefix on all keys
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; `get_or_fetch()` concurrent access verified with 100 parallel calls → single fetch
- **Git commit message**: `feat(cache): add CacheManager Protocol with Redis/aiocache and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_cache.py -v`

### TASK_013: DatabaseManager (ports + models + SQLAlchemy + InMemory + tests)
- **PR Slice**: PR #3
- **Files to create**: `src/core_infrastructure/database/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/sqlalchemy_adapter.py`, `adapters/in_memory_database_adapter.py`, `tests/unit/test_database.py`
- **Dependencies**: PR #1 + #2 merged (Config, Secret, Logger, Observability, ErrorHandling)
- **Estimated lines**: ~415 (15 + 60 + 30 + 10 + 180 + 120 + 120)
- **RED behavior**: `pytest tests/unit/test_database.py` fails
- **GREEN behavior**: `DatabaseManager` Protocol + `TransactionScope` Protocol (`commit()`/`rollback()`) + `GenericRepository[T]` Protocol (`find_by_id()`/`find_many()`/`insert()`/`update()`/`delete()`); `SQLAlchemyAdapter` wraps `sqlalchemy[asyncio]`+`asyncpg`, creates async engine in `start()`, `transaction()` returns `AsyncSession` wrapper; `InMemoryDatabaseAdapter` dict-backed with transaction rollback support; `health_check()` runs `SELECT 1`; `TransientError`→connection lost/deadlock, `PermanentError`→schema mismatch, `ValidationError`→constraint violation; OTel spans on each query
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; repository generics typed correctly with `TypeVar[T]`
- **Git commit message**: `feat(database): add DatabaseManager with SQLAlchemy async and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_database.py -v`

### TASK_014: FileStorageManager (ports + models + S3 + InMemory + tests)
- **PR Slice**: PR #3
- **Files to create**: `src/core_infrastructure/filestorage/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/s3_adapter.py`, `adapters/in_memory_filestorage_adapter.py`, `tests/unit/test_filestorage.py`
- **Dependencies**: PR #1 + #2 merged (Config, Secret, Logger, ErrorHandling)
- **Estimated lines**: ~365 (15 + 50 + 30 + 10 + 160 + 100 + 100)
- **RED behavior**: `pytest tests/unit/test_filestorage.py` fails
- **GREEN behavior**: `FileStorageManager` Protocol with `upload()`/`upload_stream()`/`download()`/`download_stream()`/`delete()`/`exists()`/`generate_presigned_url()`/`get_json_schema()`; `S3Adapter` wraps `aiofiles`(local)+`aioboto3`(S3), backend selected via settings; streaming uses `AsyncIterator[bytes]` to bound memory; `InMemoryFileStorageAdapter` dict of bytes; `FileNotFoundError`→`ValidationError`, `TransientError`→S3 throttling, `PermanentError`→invalid bucket, `NotImplementedError`→presigned on local
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; streaming verified with bounded-memory assertions
- **Git commit message**: `feat(filestorage): add FileStorageManager with S3/local and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_filestorage.py -v`

---

## PR #4: Service Layer — TaskQueue, ExternalAPI, FeatureFlag (~1,130 lines, 3 tasks)

### TASK_015: TaskQueueManager (ports + models + SAQ + InMemory + tests)
- **PR Slice**: PR #4
- **Files to create**: `src/core_infrastructure/taskqueue/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/saq_adapter.py`, `adapters/in_memory_taskqueue_adapter.py`, `tests/unit/test_taskqueue.py`
- **Dependencies**: PR #1, #2, #3 merged (Config, Cache, Logger, ErrorHandling available)
- **Estimated lines**: ~390 (15 + 50 + 30 + 10 + 160 + 110 + 120)
- **RED behavior**: `pytest tests/unit/test_taskqueue.py` fails
- **GREEN behavior**: `TaskQueueManager` Protocol with `enqueue()`/`enqueue_scheduled()`/`get_job_status()`/`cancel_job()`/`get_dlq_depth()`/`reprocess_dlq()`/`get_json_schema()`; `SAQAdapter` wraps `saq`, stores job payload as JSON in Redis; `InMemoryTaskQueueAdapter` dict-based with async scheduling simulation; DLQ support: `get_dlq_depth()` returns count, `reprocess_dlq()` moves jobs back; `ValidationError`→non-serializable payload, `TransientError`→Redis connection lost, `KeyError`→job not found; contextvars snapshot restored per job
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; context propagation across job boundaries verified
- **Git commit message**: `feat(taskqueue): add TaskQueueManager with SAQ/Redis and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_taskqueue.py -v`

### TASK_016: ExternalAPIManager (ports + models + Aiohttp + InMemory + tests)
- **PR Slice**: PR #4
- **Files to create**: `src/core_infrastructure/external_api/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/aiohttp_adapter.py`, `adapters/in_memory_external_api_adapter.py`, `tests/unit/test_external_api.py`
- **Dependencies**: PR #1, #2 merged (Config, Auth, Logger, Observability, ErrorHandling)
- **Estimated lines**: ~415 (15 + 60 + 30 + 10 + 180 + 120 + 120)
- **RED behavior**: `pytest tests/unit/test_external_api.py` fails
- **GREEN behavior**: `ExternalAPIManager` Protocol with `get()`/`post()`/`put()`/`delete()`/`get_circuit_state()`/`reset_circuit()`/`get_json_schema()`; `CircuitState` enum (CLOSED/OPEN/HALF_OPEN); `AiohttpAdapter` wraps `aiohttp`+`tenacity`, per-host circuit breaker dict, retries TRANSIENT with exponential backoff + jitter; `ClientSession` created in `start()`, closed in `stop()`; context propagation injects `traceparent`+`baggage` headers; `InMemoryExternalAPIAdapter` mock responses with circuit state; error classification: 503/504/timeout→TRANSIENT, 404/400→PERMANENT, 401/403→AUTH, 429→RATE_LIMIT
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; circuit breaker state machine verified (CLOSED→OPEN→HALF_OPEN→CLOSED)
- **Git commit message**: `feat(external_api): add ExternalAPIManager with circuit breaker and Aiohttp adapter`
- **Verification**: `python -m pytest tests/unit/test_external_api.py -v`

### TASK_017: FeatureFlagManager (ports + models + Unleash + InMemory + tests)
- **PR Slice**: PR #4
- **Files to create**: `src/core_infrastructure/feature_flags/__init__.py`, `ports.py`, `models.py`, `adapters/__init__.py`, `adapters/unleash_adapter.py`, `adapters/in_memory_feature_flag_adapter.py`, `tests/unit/test_feature_flag.py`
- **Dependencies**: PR #1, #2, #3, TASK_016 (ExternalAPI needed for Unleash communication)
- **Estimated lines**: ~365 (15 + 50 + 40 + 10 + 140 + 80 + 100)
- **RED behavior**: `pytest tests/unit/test_feature_flag.py` fails
- **GREEN behavior**: `FeatureFlagManager` Protocol with `is_enabled()`/`get_variant()`/`get_all_flags()`/`refresh()`/`health_check()`/`get_json_schema()`; `FeatureFlagContext` Protocol + `FeatureFlagContextModel` (hashed user_id for PII safety); `UnleashAdapter` reads from local cache (<1ms), `refresh()` fetches via ExternalAPI, streaming pushes to cache; `InMemoryFeatureFlagAdapter` dict-based with context evaluation; unknown flag→`False` (fail-safe); `TransientError`→Unleash unreachable, `AuthError`→invalid token; no PII in outgoing requests
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; files < 250 lines; PII safety verified in test (user_id hashed)
- **Git commit message**: `feat(feature_flags): add FeatureFlagManager with Unleash and InMemory adapters`
- **Verification**: `python -m pytest tests/unit/test_feature_flag.py -v`

---

## PR #5: Bootstrap + Integration + E2E + Finalize (~860 lines, 4 tasks)

### TASK_018: BootstrapOrchestrator
- **PR Slice**: PR #5
- **Files to create**: `src/core_infrastructure/bootstrap.py`, `tests/unit/test_bootstrap.py`
- **Dependencies**: All previous PRs merged (all 12 managers available)
- **Estimated lines**: ~280 (180 + 100)
- **RED behavior**: `pytest tests/unit/test_bootstrap.py` fails
- **GREEN behavior**: `BootstrapOrchestrator` class with constructor injection of ConfigManager + LoggerManager; `start_all()` wires and starts all 12 managers in order using `asyncio.TaskGroup` (not `asyncio.gather`), fail-fast on any manager failure (stop already-started in reverse); `stop_all()` stops in reverse order (12→1); `health_all()` returns `dict[str, HealthStatus]`; `is_system_healthy()` returns True only if all `status == "healthy"`; ConfigManager bootstraps itself from env vars + hardcoded YAML path before wiring remaining managers
- **REFACTOR criteria**: `mypy --strict` zero errors; `ruff check` zero violations; file < 250 lines; startup/shutdown ordering matches SPEC acyclic graph
- **Git commit message**: `feat(bootstrap): add BootstrapOrchestrator with TaskGroup lifecycle`
- **Verification**: `python -m pytest tests/unit/test_bootstrap.py -v`

### TASK_019: Shared Test Fixtures (conftest.py)
- **PR Slice**: PR #5
- **Files to create**: `tests/conftest.py`
- **Dependencies**: All previous PRs (needs all InMemory adapters)
- **Estimated lines**: ~120
- **RED behavior**: `pytest --collect-only` shows no fixtures
- **GREEN behavior**: Shared fixtures: `in_memory_config`, `in_memory_logger`, `in_memory_secret`, `in_memory_observability`, `in_memory_error`, `in_memory_auth`, `in_memory_cache`, `in_memory_database`, `in_memory_filestorage`, `in_memory_taskqueue`, `in_memory_external_api`, `in_memory_feature_flag`; `event_loop` fixture with function scope for async; all fixtures follow naming convention `{type}_{manager}`; fixtures are session-scoped where appropriate (no-state adapters)
- **REFACTOR criteria**: `ruff check` clean on test files; no fixture collisions
- **Git commit message**: `test: add shared conftest.py with InMemory adapter fixtures`
- **Verification**: `python -m pytest tests/ --collect-only -q`

### TASK_020: E2E + Integration Tests
- **PR Slice**: PR #5
- **Files to create**: `tests/e2e/test_full_lifecycle.py`, `tests/e2e/test_context_propagation.py`, `tests/e2e/test_error_taxonomy.py`, `tests/integration/test_redis.py`, `tests/integration/test_postgres.py`, `tests/integration/test_vault.py`, `tests/integration/test_http.py`
- **Dependencies**: TASK_018, TASK_019 (Bootstrap + fixtures exist)
- **Estimated lines**: ~560 (100+80+80 + 80+80+60+80)
- **RED behavior**: All E2E/integration tests fail or skip (no containers)
- **GREEN behavior**: E2E: `test_full_lifecycle` starts all 12 managers→assert all healthy→stop_all→verify clean shutdown; `test_context_propagation` sets contextvars→calls through 5 managers→verify same correlation_id in logs+spans; `test_error_taxonomy` injects failures per manager→verify ErrorHandlingManager classifies correctly→verify RED metrics emitted; `test_health_state_machine` degrades one manager→verify `is_system_healthy()`=False→recover→verify True. Integration: Redis (cache+tasks with testcontainers), PostgreSQL (transactions+repos), Vault (secret retrieval+rotation), HTTP (circuit breaker recovery cycle). All integration tests use `pytest.mark.integration` and skip if container unavailable
- **REFACTOR criteria**: `ruff check` clean; `mypy --strict` zero errors on test files; integration tests isolated (no cross-contamination); E2E tests < 5s each
- **Git commit message**: `test: add E2E lifecycle, context, error taxonomy and integration tests`
- **Verification**: `python -m pytest tests/e2e/ -v` + `python -m pytest tests/integration/ -v -m "integration" --no-header`

### TASK_021: Package Finalization
- **PR Slice**: PR #5
- **Files to modify**: `src/core_infrastructure/__init__.py`
- **Dependencies**: All previous tasks
- **Estimated lines**: ~30 (modify)
- **RED behavior**: `from core_infrastructure import BootstrapOrchestrator` fails
- **GREEN behavior**: `__all__` updated with all 12 manager exports + `BootstrapOrchestrator` + `CenfError` hierarchy + `AsyncLifecycle` + `HealthStatus`; `__version__` bumped to `0.1.0`; all `__init__.py` files have proper re-exports; AX JSON schemas importable via `manager.get_json_schema()`; `ruff check` passes; `mypy --strict` passes on entire package
- **REFACTOR criteria**: `python -m pytest tests/ -v --cov=core_infrastructure --cov-report=term` passes with >90% coverage; no circular imports detected; package imports in <500ms
- **Git commit message**: `chore: finalize package exports, bump to 0.1.0`
- **Verification**: `python -m pytest tests/ -v --cov=core_infrastructure --cov-report=term --cov-fail-under=90`
