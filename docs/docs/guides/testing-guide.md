---
sidebar_position: 2
---

# Testing Guide

How to test CENF managers using in-memory adapters — isolated, fast, deterministic. Every manager has a test adapter that implements the same Protocol but eliminates external I/O. This guide covers fixture patterns, error testing, authorization testing, and the TDD workflow.

## In-Memory Adapters — The Pattern

Every CENF manager has at least one in-memory test adapter. These adapters:

- Implement the same Protocol as the production adapter
- Store all state in local Python dicts / lists
- Never touch filesystem, network, or external services
- Are deterministic — same input always produces same output
- Support state inspection for assertions

### Test Adapter Map

| Manager | Test Adapter | Key Inspection Method |
|---------|-------------|----------------------|
| ConfigManager | `InMemoryConfigAdapter` | `get_string(key)` |
| LoggerManager | `InMemoryLoggerAdapter` | `get_logs()` |
| SecretManager | `InMemorySecretAdapter` | `set_secret()` / `get_secret()` |
| ObservabilityManager | `InMemoryObservabilityAdapter` | `get_metrics()`, `get_spans()` |
| ErrorHandlingManager | `CapturingErrorAdapter` | `get_captured()` |
| AuthManager | `StaticAuthAdapter` | TokenClaims injected at construction |
| CacheManager | `MemoryCacheAdapter` | `get(key)`, `exists(key)` |
| DatabaseManager | `MemoryDatabaseAdapter` | `get_repository()` |
| FileStorageManager | `MemoryStorageAdapter` | `download()`, `exists()` |
| TaskQueueManager | `MemoryTaskQueueAdapter` | `enqueue()`, `dequeue()`, `get_dlq_jobs()` |
| ExternalAPIManager | `MockHTTPAdapter` | `set_response()`, `get_circuit_state()` |
| FeatureFlagManager | `MemoryFeatureFlagAdapter` | `set_flag()`, `is_enabled()` |
| DependencyManager | `InMemoryDependencyAdapter` | `register()`, `resolve_class()` |
| DynamicPromptingManager | `ConditionalPromptAdapter` | `assemble()`, `validate_blocks()` |
| AlertManager | `DispatchAlertAdapter` | `register_rule()`, `evaluate_and_alert()` |
| RateLimiterManager | `InMemoryRateLimitAdapter` | `is_allowed()`, `configure_bucket()` |
| I18nManager | `InMemoryI18nAdapter` | `t(key)`, `set_locale()` |
| PermissionManager | `InMemoryPermissionAdapter` | `set_decision()`, `check_permission()` |
| LicenceManager | `InMemoryLicenceAdapter` | `load_license_from_claims()`, `is_feature_enabled()` |
| UpdateManager | `InMemoryUpdateAdapter` | `set_available_release()`, `check_for_updates()`, `apply_update()` |

## Fixture Patterns

### Basic Fixture (from `tests/conftest.py`)

Every manager fixture wraps the adapter with `_LifecycleWrapper` so it satisfies both the manager Protocol AND `AsyncLifecycle` (required by `BootstrapOrchestrator`):

```python
import pytest
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.common.lifecycle import AsyncLifecycle, HealthStatus

class _LifecycleWrapper:
    """Adds AsyncLifecycle (start/stop/health) to any adapter via composition."""
    def __init__(self, adapter, service_name):
        self._adapter = adapter
        self._service_name = service_name

    def __getattr__(self, name):
        return getattr(self._adapter, name)

    async def start(self): ...
    async def stop(self): ...
    async def health(self) -> HealthStatus: ...

@pytest.fixture
def config_manager() -> AsyncLifecycle:
    adapter = InMemoryConfigAdapter()
    return _LifecycleWrapper(adapter, "config")
```

### Dependency Injection in Fixtures

Managers with dependencies wire them through the fixture graph:

```python
@pytest.fixture
def error_manager(config_manager, logger_manager, observability_manager) -> AsyncLifecycle:
    adapter = ClassificationAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        observability=observability_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "error")
```

### Bootstrap Orchestrator Fixture

The full orchestrator fixture wires all managers:

```python
@pytest.fixture
def bootstrap_orchestrator(
    config_manager, logger_manager, secret_manager, observability_manager,
    error_manager, auth_manager, cache_manager, database_manager,
    filestorage_manager, taskqueue_manager, external_api_manager,
    feature_flag_manager,
) -> BootstrapOrchestrator:
    return BootstrapOrchestrator(
        config_manager, logger_manager, secret_manager, observability_manager,
        error_manager, auth_manager, cache_manager, database_manager,
        filestorage_manager, taskqueue_manager, external_api_manager,
        feature_flag_manager,
    )
```

## Testing Patterns

### 1. State Inspection

Use adapter-specific inspection methods to verify correct behavior:

```python
def test_config_values(config_manager):
    config = InMemoryConfigAdapter({"db.host": "localhost", "db.port": "5432"})
    assert config.get_string("db.host") == "localhost"
    assert config.get_number("db.port") == 5432.0
```

```python
def test_logger_output(logger_manager):
    logger = InMemoryLoggerAdapter()
    logger.info("test message", key="value")
    logs = logger.get_logs()
    assert logs[0]["event"] == "test message"
    assert logs[0]["key"] == "value"
```

```python
def test_observability_counters(observability_manager):
    obs = InMemoryObservabilityAdapter()
    obs.increment_counter("requests_total", value=1.0)
    metrics = obs.get_metrics()
    assert metrics[0]["name"] == "requests_total"
    assert metrics[0]["value"] == 1.0
```

### 2. Testing Error Handling with `CapturingErrorAdapter`

`CapturingErrorAdapter` captures errors instead of re-raising — perfect for testing error paths:

```python
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.common.errors import ValidationError

def test_error_capture(config_manager, logger_manager, observability_manager):
    error_handler = CapturingErrorAdapter(config_manager, logger_manager, observability_manager)

    @error_handler.handle_errors()
    def process_document(doc_id: str) -> dict:
        if not doc_id:
            raise ValidationError("Document ID must not be empty")
        return {"status": "processed"}

    # Happy path
    result = process_document("doc-001")
    assert result["status"] == "processed"

    # Error path — CapturingErrorAdapter returns None, does NOT raise
    failed = process_document("")
    assert failed is None

    captured = error_handler.get_captured()
    assert len(captured) == 1
    assert isinstance(captured[0], ValidationError)
```

### 3. Testing Authorization with `InMemoryPermissionAdapter`

Pre-configure allow/deny decisions and test authorization gates:

```python
from core_infrastructure.permission.adapters.in_memory_permission_adapter import InMemoryPermissionAdapter
from core_infrastructure.permission.models import PermissionConfig

async def test_permission_deny():
    perm_mgr = InMemoryPermissionAdapter(config=PermissionConfig())

    # Configure: user-123 can READ doc-001 but cannot DELETE it
    perm_mgr.set_decision("cntrs", "user-123", "document", "doc-001",
                          "read", allowed=True, reason="rbac_allow")
    perm_mgr.set_decision("cntrs", "user-123", "document", "doc-001",
                          "delete", allowed=False, reason="rbac_deny")

    read = await perm_mgr.check_permission(
        tenant_id="cntrs", principal_id="user-123", principal_type="human",
        resource_type="document", resource_id="doc-001", action="read",
    )
    assert read.is_allowed() is True

    delete = await perm_mgr.check_permission(
        tenant_id="cntrs", principal_id="user-123", principal_type="human",
        resource_type="document", resource_id="doc-001", action="delete",
    )
    assert delete.is_allowed() is False
    assert delete.reason() == "rbac_deny"
```

### 4. Testing External API Calls with `MockHTTPAdapter`

```python
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter
from core_infrastructure.external_api.models import CircuitState

async def test_mock_http():
    http = MockHTTPAdapter()

    # Configure response
    http.set_response("GET", "https://api.example.com/status",
                      status_code=200, body={"ok": True})

    resp = await http.get("https://api.example.com/status")
    assert resp.status_code == 200
    assert resp.body == {"ok": True}

    # Circuit breaker testing
    http.set_circuit_state("api.example.com", CircuitState.OPEN)
    resp = await http.get("https://api.example.com/data")
    assert resp.status_code == 503  # Circuit open

    # Response sequences for retry testing
    http.set_response_sequence("GET", "https://api.example.com/unstable", [
        (503, {"error": "unavailable"}),
        (200, {"ok": True}),
    ])
```

### 5. Testing Feature Flags

```python
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FlagConfig, FeatureFlag, FlagContext

def test_feature_flags():
    flags = MemoryFeatureFlagAdapter(config=FlagConfig(default_all=False))

    flags.set_flag(FeatureFlag(key="new_feature", enabled=True))
    flags.set_flag(FeatureFlag(key="staging_only", enabled=True, rules=[
        {"attribute": "environment", "operator": "eq", "value": "staging"},
    ]))

    ctx = FlagContext(environment="dev")
    assert flags.is_enabled("new_feature", context=ctx) is True
    assert flags.is_enabled("staging_only", context=ctx) is False
    assert flags.is_enabled("nonexistent", context=ctx) is False  # fail-safe
```

### 6. Testing Rate Limiting

```python
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import (
    InMemoryRateLimitAdapter,
)

async def test_rate_limiting():
    limiter = InMemoryRateLimitAdapter(mode="always_allow")
    assert await limiter.is_allowed("api:test") is True

    deny_limiter = InMemoryRateLimitAdapter(mode="always_deny")
    assert await deny_limiter.is_allowed("api:test") is False
```

## TDD Workflow

The CENF project follows a RED → GREEN → REFACTOR cycle with in-memory adapters:

### RED — Write a failing test

```python
# tests/test_feature_flags.py
def test_unknown_flag_returns_false():
    """Unknown flags must return False (fail-safe)."""
    flags = MemoryFeatureFlagAdapter(config=FlagConfig(default_all=False))
    assert flags.is_enabled("nonexistent") is False  # RED: this should pass
```

### GREEN — Implement the protocol method

```python
# src/core_infrastructure/feature_flags/adapters/memory_feature_flag_adapter.py
def is_enabled(self, flag_key: str, context=None) -> bool:
    flag = self._flags.get(flag_key)
    if flag is None:
        return False  # GREEN: unknown → False
    return flag.enabled
```

### REFACTOR — Clean up without changing behavior

```python
# Extract rule evaluation to a private method
def _evaluate_rules(self, flag_def, context):
    rules = flag_def.get("rules", [])
    if not rules:
        return True
    # ... match conditions against context
```

### Commit Gate

Before every commit, run the full gate:

```bash
ruff check src/ tests/         # ZERO errors
mypy src/core_infrastructure/ --strict  # ZERO errors
python -m pytest tests/ -q     # ALL green
```

## Key Testing Principles

1. **Always depend on the Protocol, inject the test adapter.** Never import production adapters in test files.
2. **Use `_LifecycleWrapper`** when testing with `BootstrapOrchestrator`. The wrapper adds `start()`, `stop()`, `health()` to any adapter.
3. **Inspect state, not side effects.** Call `get_logs()`, `get_metrics()`, `get_captured()` — never mock or patch.
4. **Isolate with in-memory adapters.** No Docker, no Redis, no filesystem. Tests run in milliseconds.
5. **Test error paths explicitly.** Use `CapturingErrorAdapter` to verify error classification without crashing.
6. **Test fail-safe behavior.** Unknown flags return `False`. Missing translations return `[missing: key]`. Circuit open returns 503.

## Related

- [Bootstrap Guide](bootstrap-guide.md) — full wiring pattern
- `tests/conftest.py` — all pytest fixtures
- `examples/full_demo.py` — integration demo exercising all managers
