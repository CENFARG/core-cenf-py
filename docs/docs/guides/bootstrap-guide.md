---
sidebar_position: 1
---

# Bootstrap Guide

How to wire all 20 infrastructure managers in dependency order using `BootstrapOrchestrator`. This guide walks through the full wiring pattern: ConfigManager first (zero dependencies), then each manager in dependency order, culminating in the orchestrator handling startup, signal-based shutdown, and health aggregation.

## Dependency Order

The manager dependency graph dictates the wiring order. Each manager depends only on managers that appear BEFORE it in this list:

```
 1. ConfigManager          — root, zero dependencies
 2. LoggerManager          — reads config
 3. SecretManager           — reads config + logger
 4. ObservabilityManager    — reads config
 5. ErrorHandlingManager    — config + logger + observability
 6. AuthManager             — config + secrets + logger
 7. CacheManager            — config + logger + error_handler
 8. DatabaseManager         — config + logger + observability + error_handler
 9. FileStorageManager      — config (+ storage backend)
10. TaskQueueManager        — config (+ queue backend)
11. ExternalAPIManager      — standalone (auth headers injected by caller)
12. FeatureFlagManager      — config + logger + error_handler
13. DependencyManager       — config + logger + error_handler
14. DynamicPromptingManager — config + logger + error_handler
15. AlertManager            — config + secrets + logger + external_api + error_handler
16. RateLimiterManager      — config + logger + error_handler (+ cache for Redis)
17. I18nManager             — config + logger
18. PermissionManager       — config (model.conf + policy.csv paths)
19. LicenceManager          — config + secret_manager
20. UpdateManager           — config + external_api
```

## Step-by-Step Wiring

### Step 1: ConfigManager — Bootstrap configuration

ConfigManager is the root — zero dependencies. Wire it first.

```python
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter

config = InMemoryConfigAdapter(initial_data={
    "app": {"name": "my-app", "version": "0.1.0"},
    "env": "dev",
    "log_level": "DEBUG",
    "cache": {"default_ttl": 300, "max_size": 1000, "backend": "memory"},
    "database": {"host": "localhost", "port": 5432, "max_connections": 10},
    "alert": {"channels": {"slack": {"webhook_url": "https://hooks.slack.com/xxx"}}},
    "dynamic_prompting": {"max_blocks": 16, "default_priority": 10},
    "ratelimit": {"default_capacity": 100, "default_refill_rate": 10.0},
    "i18n": {"locale": "en", "translations_dir": "translations", "fallback_locale": "en"},
    "feature_flags": {"file_path": "flags.yaml", "default_all": False},
    "dependency": {"allowlist_mode": "strict", "allowlist_paths": ["openai."]},
})
```

### Step 2: LoggerManager — Structured logging

```python
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter

logger = InMemoryLoggerAdapter(
    initial_context={"service": "my-app", "env": config.get_env()}
)
logger.info("Logger initialized", step="bootstrap")
```

### Step 3: SecretManager — Credential storage

```python
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter
from core_infrastructure.secrets.models import SecretConfig

secrets = InMemorySecretAdapter(config=SecretConfig(cache_ttl_seconds=30))
secrets.set_secret("auth_signing_key", "demo-hs256-key")
secrets.set_secret("api_key", "sk-demo-key")
```

### Step 4: ObservabilityManager — Metrics and tracing

```python
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)

observability = InMemoryObservabilityAdapter()
```

### Step 5: ErrorHandlingManager — Error classification

```python
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter

error_handler = CapturingErrorAdapter(config, logger, observability)
```

### Steps 6–17: Wire remaining managers

```python
# 6. AuthManager
from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
from core_infrastructure.auth.models import TokenClaims
auth = StaticAuthAdapter(default_claims=TokenClaims(
    sub="svc-my-app", iss="cenf", aud="my-app", exp=9999999999, iat=1
))

# 7. CacheManager
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
cache = MemoryCacheAdapter(config=config, logger=logger, error_handler=error_handler)

# 8. DatabaseManager
from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
db = MemoryDatabaseAdapter(config, logger, observability, error_handler)

# 9. FileStorageManager
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
storage = MemoryStorageAdapter()

# 10. TaskQueueManager
from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import MemoryTaskQueueAdapter
task_queue = MemoryTaskQueueAdapter()

# 11. ExternalAPIManager
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter
http_client = MockHTTPAdapter()

# 12. FeatureFlagManager
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FlagConfig
feature_flags = MemoryFeatureFlagAdapter(config=FlagConfig())

# 13. DependencyManager
from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import (
    InMemoryDependencyAdapter,
)
dependency_mgr = InMemoryDependencyAdapter()

# 14. DynamicPromptingManager
from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import (
    ConditionalPromptAdapter,
)
prompt_assembler = ConditionalPromptAdapter(config, logger, error_handler)

# 15. AlertManager
from core_infrastructure.alert.adapters.dispatch_alert_adapter import DispatchAlertAdapter
alert_mgr = DispatchAlertAdapter(config, secrets, logger, http_client, error_handler)

# 16. RateLimiterManager
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import (
    InMemoryRateLimitAdapter,
)
rate_limiter = InMemoryRateLimitAdapter(mode="always_allow")

# 17. I18nManager
from core_infrastructure.i18n.adapters.in_memory_i18n_adapter import InMemoryI18nAdapter
i18n = InMemoryI18nAdapter(default_locale="en", fallback_locale="en")
```

### Steps 18–20: Permission, Licence, Update

```python
# 18. PermissionManager
from core_infrastructure.permission.adapters.in_memory_permission_adapter import (
    InMemoryPermissionAdapter,
)
from core_infrastructure.permission.models import PermissionConfig
permission_mgr = InMemoryPermissionAdapter(config=PermissionConfig())

# 19. LicenceManager
from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
    InMemoryLicenceAdapter,
)
from core_infrastructure.licence.models import LicenceConfig
licence_mgr = InMemoryLicenceAdapter(config=LicenceConfig(grace_period_days=7))

# 20. UpdateManager
from core_infrastructure.update.adapters.in_memory_update_adapter import (
    InMemoryUpdateAdapter,
)
from core_infrastructure.update.models import UpdateConfig
update_mgr = InMemoryUpdateAdapter(config=UpdateConfig(
    update_url="https://updates.example.com",
    public_key="ed25519-hex-key",
    current_version="1.0.0",
))
```

## BootstrapOrchestrator — Lifecycle Management

`BootstrapOrchestrator` coordinates startup, signal-based shutdown, and health checks for all managers. It accepts manager instances that implement the `AsyncLifecycle` Protocol (`start()`, `stop()`, `health()`).

### Full Wiring Example

```python
import asyncio
from core_infrastructure.bootstrap import BootstrapOrchestrator

async def main():
    # Wire all managers (in dependency order)
    config = InMemoryConfigAdapter({"env": "dev", "app.name": "my-app"})
    logger = InMemoryLoggerAdapter()
    secrets = InMemorySecretAdapter()
    observability = InMemoryObservabilityAdapter()
    error_handler = CapturingErrorAdapter(config, logger, observability)
    auth = StaticAuthAdapter(default_claims=TokenClaims(...))
    cache = MemoryCacheAdapter(config=config, logger=logger, error_handler=error_handler)
    db = MemoryDatabaseAdapter(config, logger, observability, error_handler)
    storage = MemoryStorageAdapter()
    task_queue = MemoryTaskQueueAdapter()
    http_client = MockHTTPAdapter()
    feature_flags = MemoryFeatureFlagAdapter(config=FlagConfig())
    dependency_mgr = InMemoryDependencyAdapter()
    prompt_assembler = ConditionalPromptAdapter(config, logger, error_handler)
    alert_mgr = DispatchAlertAdapter(config, secrets, logger, http_client, error_handler)
    rate_limiter = InMemoryRateLimitAdapter()
    i18n = InMemoryI18nAdapter()
    permission_mgr = InMemoryPermissionAdapter(config=PermissionConfig())
    licence_mgr = InMemoryLicenceAdapter(config=LicenceConfig())
    update_mgr = InMemoryUpdateAdapter(config=UpdateConfig(
        update_url="https://updates.example.com",
        public_key="key...",
        current_version="1.0.0",
    ))

    # Bootstrap orchestrator — handles startup → signal → shutdown
    orchestrator = BootstrapOrchestrator(
        config, logger, secrets, observability, error_handler,
        auth, cache, db, storage, task_queue,
        http_client, feature_flags, dependency_mgr,
        prompt_assembler, alert_mgr, rate_limiter,
        i18n, permission_mgr, licence_mgr, update_mgr,
    )

    # Run the full lifecycle
    await orchestrator.run()

asyncio.run(main())
```

### Startup

`BootstrapOrchestrator.startup()` initializes all managers in dependency order using `asyncio.TaskGroup`. If ANY manager's `start()` raises, the TaskGroup cancels all remaining starts and the first exception propagates as an `ExceptionGroup` (Python 3.11+).

### Shutdown

`BootstrapOrchestrator.shutdown()` performs graceful shutdown in REVERSE dependency order. Each manager's `stop()` is called sequentially — exceptions are logged and discarded, never preventing remaining managers from shutting down.

### Health

`BootstrapOrchestrator.health()` collects health status from every registered manager. If a manager's `health()` raises, a synthetic `unhealthy` status is recorded. Returns `list[HealthStatus]` in registration order.

### Signal Handling

`BootstrapOrchestrator.run()` registers SIGTERM and SIGINT handlers that trigger the shutdown event. After startup, the orchestrator blocks until a signal is received, then performs a graceful shutdown. On Windows (where `add_signal_handler` is not supported), it falls back to `signal.signal()`.

## Full Demo

The complete wiring of all managers is demonstrated in `examples/full_demo.py`. Run it to see every manager working together:

```bash
python examples/full_demo.py
```

Expected output: a summary table showing all 20 managers exercised with their key patterns.

## Related

- [ConfigManager](../managers/config-manager.md) — root manager, no dependencies
- [Testing Guide](testing-guide.md) — using in-memory adapters with `_LifecycleWrapper`
- `examples/full_demo.py` — complete end-to-end integration demo
- `tests/conftest.py` — pytest fixtures for all managers
