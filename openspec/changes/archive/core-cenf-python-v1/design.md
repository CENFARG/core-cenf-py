# Technical Design: core-cenf-python-v1

## 1. Architecture Overview

### 1.1 Layer Diagram (Text)

```
┌─────────────────────────────────────────────────────────────┐
│  Domain Layer (out of scope — consumers of this package)   │
├─────────────────────────────────────────────────────────────┤
│  Service Layer (M06-M12)                                   │
│  Auth  Cache  Database  FileStorage  TaskQueue  ExternalAPI  FeatureFlag │
├─────────────────────────────────────────────────────────────┤
│  Cross-Cutting Layer (M02-M05)                             │
│  Logger  Secret  ErrorHandling  Observability                │
├─────────────────────────────────────────────────────────────┤
│  Foundation Layer (M01)                                      │
│  ConfigManager                                               │
├─────────────────────────────────────────────────────────────┤
│  common/context  common/errors  common/lifecycle  bootstrap  │
└─────────────────────────────────────────────────────────────┘
```

Dependency direction: **inward only**. Domain depends on ports. Adapters implement ports. No layer knows about outer layers.

### 1.2 Dependency Graph

```
ConfigManager ──────────────────────────────────────────────────────────────►
    │       │       │       │       │       │       │       │       │       │
    ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼
Logger  Secret  ErrorHandling  Observability  Auth  Cache  Database  FileStorage  TaskQueue  ExternalAPI  FeatureFlag
    │       │       │       │       │       │       │       │       │       │
    └───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘
    
    Auth ───────► ExternalAPI
    Cache ───────► TaskQueue, FeatureFlag
    ExternalAPI ─► FeatureFlag
    Observability ─► All managers (telemetry injection)
```

### 1.3 Module Map

```
src/core_infrastructure/
├── __init__.py                          # Public API re-exports
├── bootstrap.py                         # BootstrapOrchestrator
├── common/
│   ├── __init__.py
│   ├── context.py                       # ContextVar + snapshot helpers
│   ├── errors.py                        # ErrorType + CenfError hierarchy
│   └── lifecycle.py                     # AsyncLifecycle + HealthStatus
├── config/
│   ├── __init__.py
│   ├── ports.py                         # ConfigManager Protocol
│   ├── models.py                        # CoreSettings
│   └── adapters/
│       ├── __init__.py
│       ├── pydantic_settings_adapter.py # Primary adapter
│       └── in_memory_config_adapter.py  # Test double
├── logger/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── structlog_adapter.py
│       └── in_memory_logger_adapter.py
├── secrets/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── vault_adapter.py
│       └── in_memory_secret_adapter.py
├── errors/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── taxonomy_adapter.py
│       └── in_memory_error_adapter.py
├── observability/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── otel_adapter.py
│       └── in_memory_observability_adapter.py
├── auth/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── jose_adapter.py
│       └── in_memory_auth_adapter.py
├── cache/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── redis_adapter.py
│       └── in_memory_cache_adapter.py
├── database/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── sqlalchemy_adapter.py
│       └── in_memory_database_adapter.py
├── filestorage/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── s3_adapter.py
│       └── in_memory_filestorage_adapter.py
├── taskqueue/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── saq_adapter.py
│       └── in_memory_taskqueue_adapter.py
├── external_api/
│   ├── __init__.py
│   ├── ports.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── aiohttp_adapter.py
│       └── in_memory_external_api_adapter.py
└── feature_flags/
    ├── __init__.py
    ├── ports.py
    ├── models.py
    └── adapters/
        ├── __init__.py
        ├── unleash_adapter.py
        └── in_memory_feature_flag_adapter.py
```

---

## 2. Cross-Cutting Modules Design

### 2.1 common/context

**Purpose**: `contextvars` for implicit propagation of `correlation_id`, `tenant_id`, `trace_id`, `span_id`.

**Design**:
```python
from contextvars import ContextVar

# Zero-dependency module — imported by all managers
_correlation_id: ContextVar[str] = ContextVar("cenf_correlation_id", default="system-init")
_tenant_id: ContextVar[str] = ContextVar("cenf_tenant_id", default="global")
_trace_id: ContextVar[str] = ContextVar("cenf_trace_id", default="")
_span_id: ContextVar[str] = ContextVar("cenf_span_id", default="")

def get_correlation_id() -> str: ...
def set_correlation_id(cid: str) -> None: ...
def get_tenant_id() -> str: ...
def set_tenant_id(tid: str) -> None: ...
def get_trace_id() -> str: ...
def set_trace_id(tid: str) -> None: ...
def get_span_id() -> str: ...
def set_span_id(sid: str) -> None: ...
def new_correlation_id() -> str: ...
def get_context_snapshot() -> dict[str, str]: ...
def restore_context_snapshot(snapshot: dict[str, str]) -> None: ...
```

**Rules**:
- All `set_*` functions validate length via `ContextValidation` Pydantic model before assignment.
- `get_context_snapshot()` captures current values for serialization.
- `restore_context_snapshot()` is used when crossing boundary (e.g., SAQ job payload, HTTP request handler).
- Never pass context as function parameters; always read from contextvars.

**Pydantic Model**:
```python
class ContextValidation(BaseModel):
    correlation_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    trace_id: str = Field(default="", max_length=64)
    span_id: str = Field(default="", max_length=64)
```

---

### 2.2 common/errors

**Purpose**: Error taxonomy base classes. All CENF infrastructure errors inherit from `CenfError`.

**Design**:
```python
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

class TransientError(CenfError): ...
class PermanentError(CenfError): ...
class ValidationError(CenfError): ...
class AuthError(CenfError): ...
class RateLimitError(CenfError): ...
```

**Rules**:
- `details` dict is always JSON-serializable (str keys, str values).
- No Pydantic models needed here — errors are pure Python exceptions.
- `ErrorHandlingManager` classifies built-in exceptions (ConnectionError → TRANSIENT, etc.).

---

### 2.3 common/lifecycle

**Purpose**: `AsyncLifecycle` Protocol and `HealthStatus` Pydantic model.

**Design**:
```python
class HealthStatus(BaseModel):
    service: str = Field(..., min_length=1, max_length=128)
    status: Literal["healthy", "degraded", "unhealthy"] = Field(default="healthy")
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, str] = Field(default_factory=dict)
    def is_healthy(self) -> bool: ...

@runtime_checkable
class AsyncLifecycle(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def health(self) -> HealthStatus: ...
```

**Rules**:
- `start()` must be idempotent (track `_started` flag internally).
- `stop()` must be safe to call multiple times (track `_stopped` flag).
- `health()` must NEVER raise; return `degraded` on internal failure.
- All 12 managers implement this Protocol.

---

### 2.4 bootstrap

**Purpose**: `BootstrapOrchestrator` class that wires and starts/stops all managers.

**Design**:
```python
class BootstrapOrchestrator:
    def __init__(self, config: ConfigManager, logger: LoggerManager) -> None: ...
    async def start_all(self) -> dict[str, HealthStatus]: ...
    async def stop_all(self) -> None: ...
    async def health_all(self) -> dict[str, HealthStatus]: ...
    def is_system_healthy(self, statuses: dict[str, HealthStatus]) -> bool: ...
```

**Startup Sequence**:
```
1. ConfigManager.start()         — validate schema, load YAML
2. LoggerManager.start()         — configure structlog profile
3. SecretManager.start()         — warm cache
4. ErrorHandlingManager.start()  — register handlers
5. ObservabilityManager.start()  — init OTel SDK
6. AuthManager.start()           — load JWKS
7. CacheManager.start()           — connect Redis
8. DatabaseManager.start()        — create engine
9. FileStorageManager.start()     — init backend
10. TaskQueueManager.start()      — start SAQ worker
11. ExternalAPIManager.start()    — open HTTP session
12. FeatureFlagManager.start()    — connect Unleash, stream flags
```

**Shutdown**: Reverse order, 12 → 1.

**Implementation**:
- Uses `asyncio.TaskGroup` to start each manager in sequence (not `asyncio.gather` — structured concurrency).
- Fail-fast: if any manager fails, abort immediately and stop already-started managers in reverse.
- Constructor injection: `BootstrapOrchestrator` receives `ConfigManager` and `LoggerManager` first, then constructs all other managers internally using `config.get_section()` for their settings.

---

## 3. Manager Designs (M01–M12)

### 3.1 ConfigManager (M01)

**Port** (`src/core_infrastructure/config/ports.py`):
```python
@runtime_checkable
class ConfigManager(Protocol):
    def get_env(self) -> Env: ...
    def get_string(self, key: str, default_value: str | None = None) -> str: ...
    def get_number(self, key: str, default_value: float | None = None) -> float: ...
    def get_boolean(self, key: str, default_value: bool | None = None) -> bool: ...
    def get_json[T](self, key: str, default_value: T | None = None) -> T: ...
    def get_section[T: dict](self, namespace: str) -> T: ...
    async def reload(self) -> None: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/pydantic_settings_adapter.py`):
- Wraps `pydantic-settings` + `pyyaml`.
- Constructor: `__init__(env_prefix: str = "CENF_", config_path: str | None = None)`.
- Loads YAML file, then overrides with env vars (12-factor precedence).
- Stores values in an internal `dict[str, Any]` protected by `asyncio.Lock` during `reload()`.
- `get_json()` uses `json.loads()` for deserialization.
- `get_json_schema()` returns JSON Schema describing the `CoreSettings` model.

**Models** (`models.py`):
```python
class CoreSettings(BaseModel):
    env: Literal["local", "dev", "staging", "prod"] = Field(default="dev")
    app_name: str = Field(min_length=1, max_length=128, default="cenf-core")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+", default="0.1.0")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
```

**Error Handling**:
- `KeyError` → `ValidationError` (missing key, no default)
- `ValueError` → `ValidationError` (type coercion failure)
- `FileNotFoundError` → `PermanentError` (missing config file)
- `yaml.YAMLError` → `PermanentError` (malformed YAML)

**Testing**:
- **Unit**: `InMemoryConfigAdapter` — stores dict in memory, no I/O.
- **Integration**: `PydanticSettingsAdapter` with temp YAML files and env var overrides.
- **E2E**: Bootstrap fails on invalid YAML.

**File Structure**:
```
config/
├── __init__.py                # Re-exports ConfigManager, CoreSettings, PydanticSettingsAdapter, InMemoryConfigAdapter
├── ports.py                   # ConfigManager Protocol
├── models.py                  # CoreSettings
└── adapters/
    ├── __init__.py
    ├── pydantic_settings_adapter.py    # ~120 lines
    └── in_memory_config_adapter.py     # ~60 lines
```

---

### 3.2 LoggerManager (M02)

**Port** (`src/core_infrastructure/logger/ports.py`):
```python
@runtime_checkable
class LoggerManager(Protocol):
    def debug(self, message: str, **kwargs: Any) -> None: ...
    def info(self, message: str, **kwargs: Any) -> None: ...
    def warn(self, message: str, **kwargs: Any) -> None: ...
    def error(self, message: str, exc: Exception | None = None, **kwargs: Any) -> None: ...
    def bind(self, **kwargs: Any) -> LoggerManager: ...
    def mask(self, value: str, visible_chars: int = 4) -> str: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/structlog_adapter.py`):
- Wraps `structlog`.
- Constructor: `__init__(config: ConfigManager)`.
- Reads `logger.profile` from config to select dev/test/prod processors.
- Injects contextvars (`correlation_id`, `tenant_id`, `trace_id`, `span_id`) via a custom `structlog` processor that reads from `common.context`.
- **Sync-only**: structlog is sync; no `await` needed.
- `mask()` uses `*` padding showing last N chars.

**Models** (`models.py`):
```python
class LoggerSettings(BaseModel):
    profile: Literal["dev", "test", "prod"] = Field(default="dev")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    output_path: str | None = Field(default=None)
    include_timestamp: bool = Field(default=True)
    max_stack_depth: int = Field(default=10, ge=1, le=50)
```

**Error Handling**:
- LoggerManager never raises. It degrades silently.

**Testing**:
- **Unit**: `InMemoryLoggerAdapter` — collects logs in a `list[dict]` for assertions.
- **Integration**: `StructlogAdapter` with JSON output capture (StringIO).
- **E2E**: Verify contextvars auto-injection across async boundaries.

**File Structure**:
```
logger/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── structlog_adapter.py         # ~100 lines
    └── in_memory_logger_adapter.py  # ~50 lines
```

---

### 3.3 SecretManager (M03)

**Port** (`src/core_infrastructure/secrets/ports.py`):
```python
@runtime_checkable
class SecretManager(Protocol):
    async def get_secret(self, key: str) -> str: ...
    async def get_secret_bytes(self, key: str) -> bytes: ...
    async def rotate_secret(self, key: str, new_value: str) -> None: ...
    async def delete_secret(self, key: str) -> None: ...
    async def health_check(self) -> bool: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/vault_adapter.py`):
- Wraps `cryptography` + `hvac` (optional).
- Constructor: `__init__(config: ConfigManager, logger: LoggerManager)`.
- TTL cache using `aiocache` or simple `asyncio.Lock` + `dict`.
- `get_secret()` reads from cache first; if expired or missing, fetches from backend.
- `rotate_secret()` writes to backend and invalidates cache.
- `health_check()` pings backend without retrieving secrets.

**Models** (`models.py`):
```python
class SecretSettings(BaseModel):
    backend: Literal["vault", "local"] = Field(default="local")
    vault_url: str | None = Field(default=None, min_length=1)
    vault_token_path: str | None = Field(default=None)
    ttl_seconds: int = Field(default=300, ge=60, le=3600)
    cache_max_size: int = Field(default=100, ge=10)
    encryption_algorithm: Literal["fernet"] = Field(default="fernet")
```

**Error Handling**:
- `KeyError` → `ValidationError` (secret not found)
- `ConnectionError` → `TransientError` (backend unreachable)
- `hvac.exceptions.Forbidden` → `AuthError` (token expired)
- `PermanentError` (misconfiguration)

**Testing**:
- **Unit**: `InMemorySecretAdapter` — dict-based with TTL simulation.
- **Integration**: `VaultAdapter` with local Vault container or mock.
- **E2E**: Secret rotation end-to-end, verify no secrets in logs.

**File Structure**:
```
secrets/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── vault_adapter.py             # ~140 lines
    └── in_memory_secret_adapter.py  # ~80 lines
```

---

### 3.4 ErrorHandlingManager (M04)

**Port** (`src/core_infrastructure/errors/ports.py`):
```python
P = ParamSpec("P")
R = TypeVar("R")

@runtime_checkable
class ErrorHandlingManager(Protocol):
    def classify(self, error: Exception) -> ErrorType: ...
    def handle_errors(
        self,
        *,
        retryable_types: set[ErrorType] | None = None,
        max_retries: int = 3,
        on_error: Callable[[Exception], None] | None = None,
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...
    def unpack_group(self, group: BaseExceptionGroup) -> list[Exception]: ...
    def register_handler(self, error_type: ErrorType, handler: Callable[[Exception], None]) -> None: ...
    def get_pending_count(self) -> int: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/taxonomy_adapter.py`):
- Pure Python, no external library.
- Constructor: `__init__(config: ConfigManager, logger: LoggerManager, observability: ObservabilityManager)`.
- `classify()` maps built-in exceptions to `ErrorType` via a registry dict.
- `handle_errors()` decorator uses `tenacity` for retry logic (sync path) or custom async retry loop.
- `unpack_group()` recursively flattens `ExceptionGroup` (PEP 654).
- `register_handler()` stores callbacks in a `dict[ErrorType, list[Callable]]`.

**Models** (`models.py`):
```python
class ErrorHandlingSettings(BaseModel):
    max_retries_default: int = Field(default=3, ge=1, le=10)
    retry_backoff_base: float = Field(default=2.0, ge=0.5)
    retry_backoff_max: float = Field(default=30.0, ge=5.0)
    buffer_max_size: int = Field(default=1000, ge=100)
    include_stack_trace: bool = Field(default=True)
```

**Error Handling**:
- This manager consumes errors, it does not raise its own.

**Testing**:
- **Unit**: `InMemoryErrorAdapter` — same as taxonomy adapter but with no OTel dependency.
- **Integration**: `TaxonomyAdapter` with real `ObservabilityManager` in-memory.
- **E2E**: Error metrics emission.

**File Structure**:
```
errors/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── taxonomy_adapter.py           # ~130 lines
    └── in_memory_error_adapter.py    # ~70 lines
```

---

### 3.5 ObservabilityManager (M05)

**Port** (`src/core_infrastructure/observability/ports.py`):
```python
@runtime_checkable
class ObservabilityManager(Protocol):
    def increment_counter(self, name: str, value: float = 1.0, attributes: dict[str, Any] | None = None) -> None: ...
    def record_histogram(self, name: str, value: float, attributes: dict[str, Any] | None = None) -> None: ...
    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> OtelSpan: ...
    def get_current_span(self) -> OtelSpan | None: ...
    def get_trace_id(self) -> str: ...
    async def flush(self) -> None: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/otel_adapter.py`):
- Wraps `opentelemetry-sdk` + `opentelemetry-exporter-otlp`.
- Constructor: `__init__(config: ConfigManager, logger: LoggerManager)`.
- `start()` sets up:
  - `TracerProvider` with `BatchSpanProcessor` and `OTLPSpanExporter`.
  - `MeterProvider` with `PeriodicExportingMetricReader`.
  - `W3CTraceContextPropagator` for HTTP header propagation.
- `start_span()` returns an OTel `Span` usable as async context manager.
- `get_trace_id()` reads from `trace.get_current_span().get_span_context().trace_id`.
- `flush()` calls `force_flush()` on provider.

**Models** (`models.py`):
```python
class ObservabilitySettings(BaseModel):
    service_name: str = Field(min_length=1, max_length=128, default="cenf-core")
    exporter_endpoint: str | None = Field(default=None)
    exporter_protocol: Literal["grpc", "http"] = Field(default="grpc")
    sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    batch_size: int = Field(default=512, ge=1, le=8192)
    flush_interval_seconds: int = Field(default=5, ge=1, le=60)
```

**Error Handling**:
- `ValueError` → `ValidationError` (invalid metric name)
- `TransientError` → exporter unreachable
- `PermanentError` → SDK misconfiguration

**Testing**:
- **Unit**: `InMemoryObservabilityAdapter` — in-memory span/metric collector.
- **Integration**: `OTelAdapter` with `InMemorySpanExporter`.
- **E2E**: Context propagation across `TaskGroup` boundaries.

**File Structure**:
```
observability/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── otel_adapter.py                  # ~150 lines
    └── in_memory_observability_adapter.py # ~90 lines
```

---

### 3.6 AuthManager (M06)

**Port** (`src/core_infrastructure/auth/ports.py`):
```python
@runtime_checkable
class AuthManager(Protocol):
    async def validate_token(self, token: str) -> dict: ...
    async def check_scope(self, token: str, required_scopes: list[str]) -> bool: ...
    async def issue_m2m_token(self, client_id: str, client_secret: str, scopes: list[str], ttl_seconds: int = 3600) -> str: ...
    async def refresh_jwks(self) -> None: ...
    def decode_token_unsafe(self, token: str) -> dict: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/jose_adapter.py`):
- Wraps `python-jose` + `aiohttp` for JWKS fetch.
- Constructor: `__init__(config: ConfigManager, secret: SecretManager, logger: LoggerManager, observability: ObservabilityManager)`.
- `validate_token()` verifies signature, `exp`, `iss`, `aud`.
- `refresh_jwks()` fetches JWKS from `jwks_uri` on key ID mismatch.
- `issue_m2m_token()` signs JWT with secret from `SecretManager`.
- `decode_token_unsafe()` uses `jwt.get_unverified_claims()` — debug only.

**Models** (`models.py`):
```python
class AuthSettings(BaseModel):
    oidc_issuer: str = Field(min_length=1)
    jwks_uri: str | None = Field(default=None)
    jwks_cache_ttl_seconds: int = Field(default=3600, ge=60)
    m2m_enabled: bool = Field(default=False)
    m2m_secret_path: str | None = Field(default=None)
    audience: str = Field(min_length=1, default="cenf-core")
    clock_skew_seconds: int = Field(default=30, ge=0, le=120)
```

**Error Handling**:
- `AuthError` → invalid signature, expired token, missing scopes
- `TransientError` → JWKS endpoint unreachable
- `PermanentError` → OIDC misconfiguration

**Testing**:
- **Unit**: `InMemoryAuthAdapter` — mock JWT with hardcoded keys.
- **Integration**: `JoseAdapter` with mock OIDC server.
- **E2E**: Full M2M flow: issue → validate → check scope.

**File Structure**:
```
auth/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── jose_adapter.py              # ~140 lines
    └── in_memory_auth_adapter.py    # ~80 lines
```

---

### 3.7 CacheManager (M07)

**Port** (`src/core_infrastructure/cache/ports.py`):
```python
@runtime_checkable
class CacheManager(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def get_or_fetch(self, key: str, fetcher: Callable[[], Awaitable[T]], ttl_seconds: int = 300) -> T: ...
    async def clear(self) -> None: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/redis_adapter.py`):
- Wraps `redis` + `aiocache`.
- Constructor: `__init__(config: ConfigManager, logger: LoggerManager, error_handling: ErrorHandlingManager)`.
- `get_or_fetch()` uses `asyncio.Lock` per key for stampede mitigation + probabilistic early expiration (XFetch).
- Graceful degradation: if Redis fails, return `None` (cache miss) and log error.

**Models** (`models.py`):
```python
class CacheSettings(BaseModel):
    backend: Literal["memory", "redis"] = Field(default="memory")
    redis_url: str | None = Field(default=None)
    default_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    max_key_length: int = Field(default=256, ge=32)
    max_value_size_bytes: int = Field(default=1048576, ge=1024)
    stampede_probability: float = Field(default=0.1, ge=0.0, le=1.0)
    namespace: str = Field(min_length=1, max_length=64, default="cenf")
```

**Error Handling**:
- `TransientError` → Redis connection lost
- `ValueError` → `ValidationError` (non-serializable value)
- `PermanentError` → misconfiguration

**Testing**:
- **Unit**: `InMemoryCacheAdapter` — dict with TTL simulation.
- **Integration**: `RedisAdapter` with testcontainers Redis.
- **E2E**: 100 concurrent `get_or_fetch` calls, verify single fetch.

**File Structure**:
```
cache/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── redis_adapter.py             # ~150 lines
    └── in_memory_cache_adapter.py   # ~100 lines
```

---

### 3.8 DatabaseManager (M08)

**Port** (`src/core_infrastructure/database/ports.py`):
```python
@runtime_checkable
class TransactionScope(Protocol):
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

@runtime_checkable
class GenericRepository[T](Protocol):
    async def find_by_id(self, id: str) -> T | None: ...
    async def find_many(self, filters: dict[str, Any], limit: int = 100, offset: int = 0) -> Sequence[T]: ...
    async def insert(self, entity: T) -> str: ...
    async def update(self, id: str, entity: T) -> bool: ...
    async def delete(self, id: str) -> bool: ...

@runtime_checkable
class DatabaseManager(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[TransactionScope]: ...
    def get_repository[T: dict](self, table_name: str) -> GenericRepository[T]: ...
    async def health_check(self) -> bool: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/sqlalchemy_adapter.py`):
- Wraps `sqlalchemy[asyncio]` + `asyncpg`.
- Constructor: `__init__(config: ConfigManager, secret: SecretManager, logger: LoggerManager, observability: ObservabilityManager, error_handling: ErrorHandlingManager)`.
- `transaction()` returns `AsyncSession` wrapper with `commit()` and `rollback()`.
- `get_repository()` returns a generic repository using SQLAlchemy `Table` reflection.
- `health_check()` runs `SELECT 1`.

**Models** (`models.py`):
```python
class DatabaseSettings(BaseModel):
    url: str = Field(min_length=1)
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=20, ge=0, le=100)
    pool_timeout: int = Field(default=30, ge=1, le=120)
    pool_recycle: int = Field(default=3600, ge=300)
    pool_pre_ping: bool = Field(default=True)
    echo: bool = Field(default=False)
```

**Error Handling**:
- `TransientError` → connection lost, deadlock
- `PermanentError` → schema mismatch, table not found
- `ValidationError` → constraint violation

**Testing**:
- **Unit**: `InMemoryDatabaseAdapter` — dict-backed transaction scope.
- **Integration**: `SQLAlchemyAdapter` with PostgreSQL testcontainer.
- **E2E**: Concurrent transactions, deadlock detection.

**File Structure**:
```
database/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── sqlalchemy_adapter.py        # ~180 lines
    └── in_memory_database_adapter.py # ~120 lines
```

---

### 3.9 FileStorageManager (M09)

**Port** (`src/core_infrastructure/filestorage/ports.py`):
```python
@runtime_checkable
class FileStorageManager(Protocol):
    async def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str: ...
    async def upload_stream(self, key: str, stream: AsyncIterator[bytes], content_type: str = "application/octet-stream") -> str: ...
    async def download(self, key: str) -> bytes: ...
    async def download_stream(self, key: str) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def generate_presigned_url(self, key: str, expiry: timedelta = timedelta(hours=1), http_method: str = "GET") -> str: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/s3_adapter.py`):
- Wraps `aiofiles` (local) + `aioboto3` (S3).
- Constructor: `__init__(config: ConfigManager, secret: SecretManager, logger: LoggerManager, error_handling: ErrorHandlingManager)`.
- Backend selection via `FileStorageSettings.backend`.
- Streaming uses `AsyncIterator` to bound memory.

**Models** (`models.py`):
```python
class FileStorageSettings(BaseModel):
    backend: Literal["local", "s3", "gcs"] = Field(default="local")
    local_root: str | None = Field(default=None)
    s3_bucket: str | None = Field(default=None, min_length=3, max_length=63)
    s3_region: str | None = Field(default="us-east-1")
    gcs_bucket: str | None = Field(default=None)
    max_file_size_bytes: int = Field(default=104857600, ge=1048576)
    presigned_url_default_hours: int = Field(default=1, ge=1, le=168)
```

**Error Handling**:
- `FileNotFoundError` → `ValidationError` (key missing)
- `TransientError` → network error, S3 throttling
- `PermanentError` → invalid bucket, expired credentials
- `NotImplementedError` → pre-signed URL on local backend

**Testing**:
- **Unit**: `InMemoryFileStorageAdapter` — dict of bytes.
- **Integration**: `S3Adapter` with `moto` mock.
- **E2E**: Streaming 100MB file, verify bounded memory.

**File Structure**:
```
filestorage/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── s3_adapter.py                 # ~160 lines
    └── in_memory_filestorage_adapter.py # ~100 lines
```

---

### 3.10 TaskQueueManager (M10)

**Port** (`src/core_infrastructure/taskqueue/ports.py`):
```python
@runtime_checkable
class TaskQueueManager(Protocol):
    async def enqueue(self, job_name: str, payload: dict[str, Any], *, queue: str = "default", delay_seconds: int = 0, max_retries: int = 3) -> str: ...
    async def enqueue_scheduled(self, job_name: str, payload: dict[str, Any], scheduled_at: datetime, *, queue: str = "default", max_retries: int = 3) -> str: ...
    async def get_job_status(self, job_id: str) -> dict[str, Any]: ...
    async def cancel_job(self, job_id: str) -> bool: ...
    async def get_dlq_depth(self, queue: str = "default") -> int: ...
    async def reprocess_dlq(self, queue: str = "default", limit: int = 10) -> int: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/saq_adapter.py`):
- Wraps `saq`.
- Constructor: `__init__(config: ConfigManager, cache: CacheManager, logger: LoggerManager, error_handling: ErrorHandlingManager)`.
- `enqueue()` serializes payload to JSON, stores in Redis via SAQ.
- `get_job_status()` queries SAQ job metadata.
- `reprocess_dlq()` moves jobs from DLQ queue back to main queue.

**Models** (`models.py`):
```python
class TaskQueueSettings(BaseModel):
    redis_url: str = Field(min_length=1, default="redis://localhost:6379")
    queue_name: str = Field(min_length=1, max_length=64, default="default")
    worker_concurrency: int = Field(default=10, ge=1, le=100)
    max_retries_default: int = Field(default=3, ge=1, le=10)
    backoff_base_seconds: float = Field(default=2.0, ge=0.5)
    backoff_max_seconds: float = Field(default=300.0, ge=10.0)
    dlq_enabled: bool = Field(default=True)
    job_timeout_seconds: int = Field(default=300, ge=10, le=3600)
```

**Error Handling**:
- `ValueError` → `ValidationError` (non-serializable payload)
- `TransientError` → Redis connection lost
- `PermanentError` → worker misconfiguration
- `KeyError` → job not found

**Testing**:
- **Unit**: `InMemoryTaskQueueAdapter` — dict of job states with async scheduling.
- **Integration**: `SAQAdapter` with Redis testcontainer.
- **E2E**: Scheduled job timing, DLQ reprocessing.

**File Structure**:
```
taskqueue/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── saq_adapter.py                # ~160 lines
    └── in_memory_taskqueue_adapter.py # ~110 lines
```

---

### 3.11 ExternalAPIManager (M11)

**Port** (`src/core_infrastructure/external_api/ports.py`):
```python
class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@runtime_checkable
class ExternalAPIManager(Protocol):
    async def get(self, url: str, *, headers: dict[str, str] | None = None, timeout_seconds: float = 30.0, params: dict[str, str] | None = None) -> dict[str, Any]: ...
    async def post(self, url: str, *, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout_seconds: float = 30.0) -> dict[str, Any]: ...
    async def put(self, url: str, *, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout_seconds: float = 30.0) -> dict[str, Any]: ...
    async def delete(self, url: str, *, headers: dict[str, str] | None = None, timeout_seconds: float = 30.0) -> dict[str, Any]: ...
    def get_circuit_state(self, host: str) -> CircuitState: ...
    async def reset_circuit(self, host: str) -> None: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/aiohttp_adapter.py`):
- Wraps `aiohttp` + `tenacity`.
- Constructor: `__init__(config: ConfigManager, auth: AuthManager, logger: LoggerManager, observability: ObservabilityManager, error_handling: ErrorHandlingManager)`.
- `aiohttp.ClientSession` created in `start()`, closed in `stop()`.
- Per-host circuit breaker using a `dict[str, CircuitBreaker]`.
- Retry via `tenacity` with exponential backoff + jitter on `TransientError`.
- Context propagation: injects `traceparent` and `baggage` headers from `common.context`.

**Models** (`models.py`):
```python
class ExternalAPISettings(BaseModel):
    default_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    max_retries: int = Field(default=3, ge=1, le=10)
    backoff_base_seconds: float = Field(default=2.0, ge=0.5)
    backoff_max_seconds: float = Field(default=30.0, ge=5.0)
    circuit_failure_threshold_pct: float = Field(default=50.0, ge=10.0, le=100.0)
    circuit_recovery_timeout_seconds: float = Field(default=30.0, ge=5.0)
    circuit_min_requests: int = Field(default=10, ge=1, le=100)
    circuit_half_open_max_requests: int = Field(default=3, ge=1, le=10)
    propagate_context: bool = Field(default=True)
```

**Error Handling**:
- `TransientError` → 503, 504, connection refused, timeout
- `PermanentError` → 404, 400, invalid URL, circuit OPEN
- `AuthError` → 401, 403
- `RateLimitError` → 429

**Testing**:
- **Unit**: `InMemoryExternalAPIAdapter` — mock responses with circuit state.
- **Integration**: `AiohttpAdapter` with local HTTP server (`pytest-httpserver`).
- **E2E**: Circuit breaker recovery cycle.

**File Structure**:
```
external_api/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── aiohttp_adapter.py             # ~180 lines
    └── in_memory_external_api_adapter.py # ~120 lines
```

---

### 3.12 FeatureFlagManager (M12)

**Port** (`src/core_infrastructure/feature_flags/ports.py`):
```python
@runtime_checkable
class FeatureFlagContext(Protocol):
    user_id: str | None
    session_id: str | None
    environment: str
    custom_properties: dict[str, str]

@runtime_checkable
class FeatureFlagManager(Protocol):
    def is_enabled(self, flag_name: str, context: FeatureFlagContext | None = None) -> bool: ...
    def get_variant(self, flag_name: str, context: FeatureFlagContext | None = None) -> dict[str, Any]: ...
    def get_all_flags(self) -> dict[str, bool]: ...
    async def refresh(self) -> None: ...
    async def health_check(self) -> bool: ...
    def get_json_schema(self) -> dict[str, Any]: ...
```

**Adapter** (`adapters/unleash_adapter.py`):
- Wraps `unleash-client`.
- Constructor: `__init__(config: ConfigManager, cache: CacheManager, external_api: ExternalAPIManager, logger: LoggerManager, error_handling: ErrorHandlingManager)`.
- `is_enabled()` reads from local cache (fast, <1ms). Uses `cache.get()` for offline fallback.
- `refresh()` fetches latest flags from Unleash via `ExternalAPIManager`.
- Streaming updates pushed to cache via `cache.set()`.
- PII safety: `FeatureFlagContext` uses hashed `user_id` only.

**Models** (`models.py`):
```python
class FeatureFlagSettings(BaseModel):
    unleash_url: str = Field(min_length=1)
    unleash_api_token: str | None = Field(default=None, min_length=1)
    app_name: str = Field(min_length=1, max_length=128, default="cenf-core")
    environment: str = Field(min_length=1, max_length=64, default="development")
    refresh_interval_seconds: int = Field(default=10, ge=5, le=300)
    streaming_enabled: bool = Field(default=True)
    fallback_enabled: bool = Field(default=True)

class FeatureFlagContextModel(BaseModel):
    user_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    environment: str = Field(min_length=1, max_length=64)
    custom_properties: dict[str, str] = Field(default_factory=dict)
```

**Error Handling**:
- `TransientError` → Unleash API unreachable
- `PermanentError` → URL misconfiguration
- `AuthError` → invalid token
- Unknown flag → returns `False` (fail-safe), no error

**Testing**:
- **Unit**: `InMemoryFeatureFlagAdapter` — dict of flags with context evaluation.
- **Integration**: `UnleashAdapter` with mock Unleash server.
- **E2E**: Verify no PII in outgoing requests.

**File Structure**:
```
feature_flags/
├── __init__.py
├── ports.py
├── models.py
└── adapters/
    ├── __init__.py
    ├── unleash_adapter.py               # ~140 lines
    └── in_memory_feature_flag_adapter.py # ~80 lines
```

---

## 4. System-Level Concerns

### 4.1 Dependency Injection Pattern

**Choice**: Manual constructor injection. No DI framework.

**Rationale**:
- Frameworks like `dependency-injector` add magic and complicate static analysis.
- Constructor injection is explicit, testable, and mypy-friendly.
- Each adapter declares its dependencies in `__init__` — type checker validates the graph.

**Wiring Pattern** (in `bootstrap.py`):
```python
async def build_managers(config: ConfigManager) -> dict[str, Any]:
    logger = StructlogAdapter(config)
    secret = VaultAdapter(config, logger)
    error_handling = TaxonomyAdapter(config, logger, InMemoryObservabilityAdapter(config, logger))
    observability = OTelAdapter(config, logger)
    # ... continue in dependency order
    return {"config": config, "logger": logger, ...}
```

**Rules**:
- Each manager receives ONLY the managers it depends on (per SPEC_00 dependency graph).
- No manager imports another manager's adapter directly; only ports.
- `InMemory*` adapters are used for unit tests; they receive minimal dependencies.

---

### 4.2 Configuration Bootstrap Sequence

**The Chicken-and-Egg Problem**: ConfigManager is needed to configure all other managers, but ConfigManager itself needs configuration.

**Resolution**:
1. `BootstrapOrchestrator` creates `ConfigManager` first using **only** environment variables and a hardcoded default YAML path (the ONLY exception to "no direct env access").
2. `ConfigManager.start()` validates `CoreSettings` via Pydantic.
3. If validation fails, bootstrap exits immediately (fail-fast).
4. Once `ConfigManager` is healthy, all other managers read their settings from `config.get_section("manager_name")`.

**Code sketch**:
```python
class BootstrapOrchestrator:
    async def start_all(self) -> dict[str, HealthStatus]:
        # Step 1: ConfigManager bootstraps itself
        raw_config = PydanticSettingsAdapter(
            env_prefix="CENF_",
            config_path=os.getenv("CENF_CONFIG_PATH", "config.yaml"),
        )
        await raw_config.start()
        # Step 2: wire remaining managers
        managers = await self._build_managers(raw_config)
        # Step 3: start remaining managers in order
        ...
```

---

### 4.3 Context Propagation Design

**Mechanism**: `contextvars` from `common.context`.

**Producer/Consumer Flow**:
```
HTTP handler / Job worker
    └─► new_correlation_id()          # Producer
    └─► set_tenant_id(claims["tid"])  # Producer (AuthManager)
    └─► await logger.info("...")        # Consumer (reads correlation_id)
    └─► await db.transaction()          # Consumer (reads tenant_id)
    └─► await external_api.get("...")   # Consumer (injects traceparent header)
    └─► await observability.start_span() # Producer (sets trace_id, span_id)
```

**Rules**:
- Contextvars are set at the entry point (HTTP request, SAQ job, CLI command).
- All managers read contextvars implicitly. No `context` parameter in any function signature.
- `restore_context_snapshot()` is called when crossing boundaries (e.g., inside SAQ job execution or before `TaskGroup` sub-tasks).
- `contextvars` automatically propagate across `await` boundaries in the same task.

---

### 4.4 Error Taxonomy Routing

**Classification**:
```
ConnectionError, TimeoutError, asyncio.TimeoutError → TRANSIENT
ValueError, KeyError, TypeError (input) → VALIDATION
PermissionError, authentication failures → AUTH
HTTP 429 → RATE_LIMIT
FileNotFoundError (config), NotImplementedError, schema mismatch → PERMANENT
```

**Routing**:
1. `ErrorHandlingManager.classify(error)` returns `ErrorType`.
2. `ErrorHandlingManager.handle_errors()` decorator inspects the classified type:
   - `TRANSIENT` / `RATE_LIMIT` → retry with tenacity
   - `VALIDATION` / `AUTH` / `PERMANENT` → log and re-raise immediately
3. `register_handler()` allows custom handlers (e.g., `AuthError` → notify security team).
4. `unpack_group()` flattens `ExceptionGroup` so each inner exception is classified independently.

**Metrics**:
- `cenf.error.classified_total` with label `error_type`.
- `cenf.error.pending_count` gauge.

---

### 4.5 OpenTelemetry Initialization

**Sequence** (inside `ObservabilityManager.start()`):
```python
async def start(self) -> None:
    settings = ObservabilitySettings.model_validate(
        self._config.get_section("observability")
    )
    # TracerProvider
    tracer_provider = TracerProvider(
        sampler=TraceIdRatioBased(settings.sampling_rate)
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.exporter_endpoint,
                protocol=settings.exporter_protocol,
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)
    # MeterProvider
    meter_provider = MeterProvider(
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(
                    endpoint=settings.exporter_endpoint,
                    protocol=settings.exporter_protocol,
                ),
                export_interval_millis=settings.flush_interval_seconds * 1000,
            )
        ]
    )
    metrics.set_meter_provider(meter_provider)
    # Propagator
    set_global_textmap(W3CTraceContextPropagator())
```

**Rules**:
- OTel setup is lazy: if no `exporter_endpoint` is configured, use `InMemorySpanExporter` for tests.
- `flush()` is called during `ObservabilityManager.stop()` to prevent span loss.
- `trace_id` and `span_id` are synced to `contextvars` so `LoggerManager` can inject them.

---

## 5. Testing Architecture

### 5.1 Test Doubles Catalog

| Manager | Test Double | Location | Capabilities |
|---------|-------------|----------|--------------|
| Config | `InMemoryConfigAdapter` | `config/adapters/` | Dict-based, no I/O |
| Logger | `InMemoryLoggerAdapter` | `logger/adapters/` | Collects logs in list |
| Secret | `InMemorySecretAdapter` | `secrets/adapters/` | Dict with TTL simulation |
| Error | `InMemoryErrorAdapter` | `errors/adapters/` | Pure taxonomy, no OTel |
| Observability | `InMemoryObservabilityAdapter` | `observability/adapters/` | In-memory spans/metrics |
| Auth | `InMemoryAuthAdapter` | `auth/adapters/` | Hardcoded JWT keys |
| Cache | `InMemoryCacheAdapter` | `cache/adapters/` | Dict with stampede simulation |
| Database | `InMemoryDatabaseAdapter` | `database/adapters/` | Dict transactions |
| FileStorage | `InMemoryFileStorageAdapter` | `filestorage/adapters/` | Dict of bytes |
| TaskQueue | `InMemoryTaskQueueAdapter` | `taskqueue/adapters/` | Async dict scheduling |
| ExternalAPI | `InMemoryExternalAPIAdapter` | `external_api/adapters/` | Mock responses + circuit |
| FeatureFlag | `InMemoryFeatureFlagAdapter` | `feature_flags/adapters/` | Dict of flags |

### 5.2 Integration Test Strategy

| Service | Container | Manager Adapter | Test Focus |
|---------|-----------|-----------------|------------|
| Redis | `testcontainers.redis.RedisContainer` | `RedisAdapter` | Cache ops, TaskQueue, FeatureFlag |
| PostgreSQL | `testcontainers.postgres.PostgresContainer` | `SQLAlchemyAdapter` | Transactions, repositories |
| Vault | `testcontainers.hashicorp.VaultContainer` | `VaultAdapter` | Secret retrieval, rotation |
| HTTP | `pytest-httpserver` | `AiohttpAdapter` | Circuit breaker, retries, timeouts |

**Test Organization**:
```
tests/
├── unit/              # 1 file per manager: test_<manager>.py
├── integration/       # 1 file per external service: test_<service>.py
├── e2e/               # test_bootstrap.py, test_full_lifecycle.py
└── conftest.py        # Shared fixtures (in-memory adapters, event_loop)
```

### 5.3 E2E Test Strategy

1. **Bootstrap E2E**: `start_all()` → verify all 12 managers report healthy → `stop_all()` → verify clean shutdown.
2. **Context Propagation E2E**: Set contextvars → call through 5 managers → verify same correlation_id in logs and spans.
3. **Error Taxonomy E2E**: Inject failures in each manager → verify `ErrorHandlingManager` classifies correctly and metrics are emitted.
4. **Health State Machine E2E**: Degrade one manager → verify system health = false → recover → verify health = true.

---

## 6. File Manifest

| File | Action | Est. Lines | Description |
|------|--------|------------|-------------|
| `src/core_infrastructure/__init__.py` | Modify | 40 | Update public re-exports |
| `src/core_infrastructure/bootstrap.py` | Create | 180 | BootstrapOrchestrator |
| `src/core_infrastructure/common/__init__.py` | Create | 10 | Common re-exports |
| `src/core_infrastructure/common/context.py` | Create | 80 | ContextVar + snapshot helpers |
| `src/core_infrastructure/common/errors.py` | Create | 70 | ErrorType + CenfError hierarchy |
| `src/core_infrastructure/common/lifecycle.py` | Create | 60 | AsyncLifecycle + HealthStatus |
| `src/core_infrastructure/config/__init__.py` | Create | 15 | Config re-exports |
| `src/core_infrastructure/config/ports.py` | Create | 50 | ConfigManager Protocol |
| `src/core_infrastructure/config/models.py` | Create | 30 | CoreSettings |
| `src/core_infrastructure/config/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/config/adapters/pydantic_settings_adapter.py` | Create | 120 | Primary config adapter |
| `src/core_infrastructure/config/adapters/in_memory_config_adapter.py` | Create | 60 | Test double |
| `src/core_infrastructure/logger/__init__.py` | Create | 15 | Logger re-exports |
| `src/core_infrastructure/logger/ports.py` | Create | 40 | LoggerManager Protocol |
| `src/core_infrastructure/logger/models.py` | Create | 30 | LoggerSettings |
| `src/core_infrastructure/logger/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/logger/adapters/structlog_adapter.py` | Create | 100 | Primary logger adapter |
| `src/core_infrastructure/logger/adapters/in_memory_logger_adapter.py` | Create | 50 | Test double |
| `src/core_infrastructure/secrets/__init__.py` | Create | 15 | Secret re-exports |
| `src/core_infrastructure/secrets/ports.py` | Create | 40 | SecretManager Protocol |
| `src/core_infrastructure/secrets/models.py` | Create | 30 | SecretSettings |
| `src/core_infrastructure/secrets/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/secrets/adapters/vault_adapter.py` | Create | 140 | Primary secret adapter |
| `src/core_infrastructure/secrets/adapters/in_memory_secret_adapter.py` | Create | 80 | Test double |
| `src/core_infrastructure/errors/__init__.py` | Create | 15 | Error re-exports |
| `src/core_infrastructure/errors/ports.py` | Create | 50 | ErrorHandlingManager Protocol |
| `src/core_infrastructure/errors/models.py` | Create | 30 | ErrorHandlingSettings |
| `src/core_infrastructure/errors/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/errors/adapters/taxonomy_adapter.py` | Create | 130 | Primary error adapter |
| `src/core_infrastructure/errors/adapters/in_memory_error_adapter.py` | Create | 70 | Test double |
| `src/core_infrastructure/observability/__init__.py` | Create | 15 | Observability re-exports |
| `src/core_infrastructure/observability/ports.py` | Create | 50 | ObservabilityManager Protocol |
| `src/core_infrastructure/observability/models.py` | Create | 30 | ObservabilitySettings |
| `src/core_infrastructure/observability/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/observability/adapters/otel_adapter.py` | Create | 150 | Primary observability adapter |
| `src/core_infrastructure/observability/adapters/in_memory_observability_adapter.py` | Create | 90 | Test double |
| `src/core_infrastructure/auth/__init__.py` | Create | 15 | Auth re-exports |
| `src/core_infrastructure/auth/ports.py` | Create | 40 | AuthManager Protocol |
| `src/core_infrastructure/auth/models.py` | Create | 30 | AuthSettings |
| `src/core_infrastructure/auth/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/auth/adapters/jose_adapter.py` | Create | 140 | Primary auth adapter |
| `src/core_infrastructure/auth/adapters/in_memory_auth_adapter.py` | Create | 80 | Test double |
| `src/core_infrastructure/cache/__init__.py` | Create | 15 | Cache re-exports |
| `src/core_infrastructure/cache/ports.py` | Create | 40 | CacheManager Protocol |
| `src/core_infrastructure/cache/models.py` | Create | 30 | CacheSettings |
| `src/core_infrastructure/cache/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/cache/adapters/redis_adapter.py` | Create | 150 | Primary cache adapter |
| `src/core_infrastructure/cache/adapters/in_memory_cache_adapter.py` | Create | 100 | Test double |
| `src/core_infrastructure/database/__init__.py` | Create | 15 | Database re-exports |
| `src/core_infrastructure/database/ports.py` | Create | 60 | DatabaseManager + TransactionScope + GenericRepository Protocols |
| `src/core_infrastructure/database/models.py` | Create | 30 | DatabaseSettings |
| `src/core_infrastructure/database/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/database/adapters/sqlalchemy_adapter.py` | Create | 180 | Primary database adapter |
| `src/core_infrastructure/database/adapters/in_memory_database_adapter.py` | Create | 120 | Test double |
| `src/core_infrastructure/filestorage/__init__.py` | Create | 15 | FileStorage re-exports |
| `src/core_infrastructure/filestorage/ports.py` | Create | 50 | FileStorageManager Protocol |
| `src/core_infrastructure/filestorage/models.py` | Create | 30 | FileStorageSettings |
| `src/core_infrastructure/filestorage/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/filestorage/adapters/s3_adapter.py` | Create | 160 | Primary file storage adapter |
| `src/core_infrastructure/filestorage/adapters/in_memory_filestorage_adapter.py` | Create | 100 | Test double |
| `src/core_infrastructure/taskqueue/__init__.py` | Create | 15 | TaskQueue re-exports |
| `src/core_infrastructure/taskqueue/ports.py` | Create | 50 | TaskQueueManager Protocol |
| `src/core_infrastructure/taskqueue/models.py` | Create | 30 | TaskQueueSettings |
| `src/core_infrastructure/taskqueue/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/taskqueue/adapters/saq_adapter.py` | Create | 160 | Primary task queue adapter |
| `src/core_infrastructure/taskqueue/adapters/in_memory_taskqueue_adapter.py` | Create | 110 | Test double |
| `src/core_infrastructure/external_api/__init__.py` | Create | 15 | ExternalAPI re-exports |
| `src/core_infrastructure/external_api/ports.py` | Create | 60 | ExternalAPIManager Protocol |
| `src/core_infrastructure/external_api/models.py` | Create | 30 | ExternalAPISettings |
| `src/core_infrastructure/external_api/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/external_api/adapters/aiohttp_adapter.py` | Create | 180 | Primary external API adapter |
| `src/core_infrastructure/external_api/adapters/in_memory_external_api_adapter.py` | Create | 120 | Test double |
| `src/core_infrastructure/feature_flags/__init__.py` | Create | 15 | FeatureFlag re-exports |
| `src/core_infrastructure/feature_flags/ports.py` | Create | 50 | FeatureFlagManager Protocol |
| `src/core_infrastructure/feature_flags/models.py` | Create | 40 | FeatureFlagSettings + FeatureFlagContextModel |
| `src/core_infrastructure/feature_flags/adapters/__init__.py` | Create | 10 | Adapter re-exports |
| `src/core_infrastructure/feature_flags/adapters/unleash_adapter.py` | Create | 140 | Primary feature flag adapter |
| `src/core_infrastructure/feature_flags/adapters/in_memory_feature_flag_adapter.py` | Create | 80 | Test double |
| `tests/unit/test_config.py` | Create | 120 | ConfigManager unit tests |
| `tests/unit/test_logger.py` | Create | 100 | LoggerManager unit tests |
| `tests/unit/test_secret.py` | Create | 100 | SecretManager unit tests |
| `tests/unit/test_error_handling.py` | Create | 120 | ErrorHandlingManager unit tests |
| `tests/unit/test_observability.py` | Create | 100 | ObservabilityManager unit tests |
| `tests/unit/test_auth.py` | Create | 120 | AuthManager unit tests |
| `tests/unit/test_cache.py` | Create | 120 | CacheManager unit tests |
| `tests/unit/test_database.py` | Create | 120 | DatabaseManager unit tests |
| `tests/unit/test_filestorage.py` | Create | 100 | FileStorageManager unit tests |
| `tests/unit/test_taskqueue.py` | Create | 120 | TaskQueueManager unit tests |
| `tests/unit/test_external_api.py` | Create | 120 | ExternalAPIManager unit tests |
| `tests/unit/test_feature_flag.py` | Create | 100 | FeatureFlagManager unit tests |
| `tests/unit/test_context.py` | Create | 60 | Context propagation unit tests |
| `tests/unit/test_lifecycle.py` | Create | 60 | AsyncLifecycle unit tests |
| `tests/unit/test_bootstrap.py` | Create | 100 | Bootstrap unit tests |
| `tests/integration/test_redis.py` | Create | 80 | Redis integration tests |
| `tests/integration/test_postgres.py` | Create | 80 | PostgreSQL integration tests |
| `tests/integration/test_vault.py` | Create | 60 | Vault integration tests |
| `tests/integration/test_http.py` | Create | 80 | HTTP/circuit breaker integration tests |
| `tests/e2e/test_full_lifecycle.py` | Create | 100 | E2E bootstrap lifecycle |
| `tests/e2e/test_context_propagation.py` | Create | 80 | E2E context propagation |
| `tests/e2e/test_error_taxonomy.py` | Create | 80 | E2E error classification |
| `tests/conftest.py` | Create | 120 | Shared fixtures |

**Total estimated new lines**: ~5,500  
**Total files to create**: 88 (1 modified + 87 new)

**Review Budget Assessment**: This exceeds the 400-line review budget. The `sdd-tasks` phase MUST decompose this into chained PR slices:
1. **Slice 1**: Cross-cutting + Config + Logger (foundation)
2. **Slice 2**: Secret + ErrorHandling + Observability (cross-cutting)
3. **Slice 3**: Auth + Cache + Database (data layer)
4. **Slice 4**: FileStorage + TaskQueue + ExternalAPI + FeatureFlag (service layer)
5. **Slice 5**: Bootstrap + E2E tests + integration tests

Each slice should be a standalone PR under 400 lines.

---

## Design Decisions

| Decision | Choice | Alternatives Rejected | Rationale |
|----------|--------|----------------------|-----------|
| DI approach | Manual constructor injection | `dependency-injector`, `inject` | Explicit, mypy-friendly, zero magic |
| Config bootstrap | Env vars + hardcoded YAML path | Config from DB | ConfigManager must be self-bootstrapping; env vars are the only pre-existing source |
| Context propagation | `contextvars` | Explicit `context` parameter | Matches spec; zero boilerplate; propagates across `await` |
| Error taxonomy | Enum + exception hierarchy | Integer codes | Type-safe; mypy validates `error_type` |
| OTel setup | SDK init in `ObservabilityManager.start()` | Manual span creation everywhere | Centralized; consistent RED metrics across all managers |
| Test doubles | In-memory adapters per manager | Mocks (unittest.mock) | In-memory adapters exercise real port contracts; faster than mocks |
| Structured concurrency | `asyncio.TaskGroup` | `asyncio.gather` | PEP 654 alignment; clean cancellation; fail-fast |
| File size limit | < 250 lines | Larger files | SPEC_00 requirement; enforced by ruff |
