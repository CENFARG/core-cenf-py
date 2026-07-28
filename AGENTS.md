# AGENTS.md — Core-CENF Python Agent Instructions

> **For AI coding agents**: Read this FIRST before writing any code that uses core-cenf-py.
> Total read time: ~90 seconds. Total managers: 23. All infrastructure, zero domain logic.

---

## What is core-cenf?

A reusable infrastructure library for Python 3.12+ providing 23 horizontal transversal managers following Clean Architecture (Ports & Adapters). Every CENF program — backend APIs, AI agents, workflows, UIs — uses these managers for all cross-cutting concerns. You never write config loading, logging, error handling, or observability from scratch again.

## Golden Rule

**Every manager has exactly one Protocol (interface) and one or more Adapters (implementations). Your code depends on the Protocol. The adapter is injected at startup.**

```python
# ✅ CORRECT: depend on Protocol
from core_infrastructure.config.ports import ConfigManager
def my_function(config: ConfigManager):
    db_host = config.get_string("db.host")

# ❌ WRONG: depend on adapter directly
from core_infrastructure.config.adapters.pydantic_config_adapter import PydanticConfigAdapter
```

---

## The 23 Managers — Quick Reference

| # | Manager | What it does | Key method | Test adapter |
|---|---------|-------------|------------|-------------|
| M01 | **ConfigManager** | Read-only config from YAML+env | `get_string(key)` | `InMemoryConfigAdapter` |
| M02 | **LoggerManager** | Structured logging (dev/test/prod) | `logger.info(msg, **ctx)` | `InMemoryLoggerAdapter` |
| M03 | **SecretManager** | Encrypted credential storage | `get_secret(key)` → masked | `InMemorySecretAdapter` |
| M04 | **ErrorHandlingManager** | Classify & report errors | `@handle_errors` decorator | `CapturingErrorAdapter` |
| M05 | **ObservabilityManager** | OTel RED metrics & tracing | `increment_counter(name)` | `InMemoryObservabilityAdapter` |
| M06 | **AuthManager** | JWT validation (HS256) | `validate_token(token)` → claims | `StaticAuthAdapter` |
| M07 | **CacheManager** | KV cache with stampede protection | `get_or_set(key, factory, ttl)` | `MemoryCacheAdapter` |
| M08 | **DatabaseManager** | Transactions + generic repos | `transaction()` context mgr | `MemoryDatabaseAdapter` |
| M09 | **FileStorageManager** | Multi-cloud blob storage | `upload(bucket, key, data)` | `MemoryStorageAdapter` |
| M10 | **TaskQueueManager** | Async jobs with DLQ | `enqueue(queue, payload)` | `MemoryTaskQueueAdapter` |
| M11 | **ExternalAPIManager** | Resilient HTTP with circuit breaker | `get(url)` / `post(url, body)` | `MockHTTPAdapter` |
| M12 | **FeatureFlagManager** | Runtime toggles (YAML→Unleash) | `is_enabled(flag, context)` | `MemoryFeatureFlagAdapter` |
| M13 | **DependencyManager** | Lazy safe import resolution | `resolve_class(module, class)` | `InMemoryDependencyAdapter` |
| M14 | **DynamicPromptingManager** | Conditional prompt assembly | `assemble(base, blocks, ctx)` | (use real adapter) |
| M15 | **AlertManager** | Slack/Discord/Email alerts | `send_alert(level, title, msg)` | (use real adapter) |
| M16 | **RateLimiterManager** | Token bucket rate limiting | `is_allowed(bucket_key)` | `InMemoryRateLimitAdapter` |
| M17 | **I18nManager** | Multi-language translations | `t(key, **params)` | `InMemoryI18nAdapter` |
| M18 | **PermissionManager** | RBAC+ABAC access control | `check_permission(...)` | `InMemoryPermissionAdapter` |
| M19 | **LicenceManager** | Signed licence validation | `load_license_from_string(...)` | `InMemoryLicenceAdapter` |
| M20 | **UpdateManager** | Desktop/CLI/Web/Android auto-update + rollback | `check_for_updates(...)` | `InMemoryUpdateAdapter` | `HttpUpdateAdapter`, `PipUpdateAdapter`, `WebUpdateAdapter`, `GitHubReleaseAdapter`, `AndroidUpdateAdapter` |
| M21 | **BusEventManager** | Decoupled pub/sub messaging | `publish(event_type, payload)` | `MemoryBusAdapter` |
| M22 | **StateMachineManager** | State machine with guards, hooks, error strategies | `run(ctx)` → StateMachineStatus | `InMemoryStateMachineAdapter` |
| M23 | **FileReaderPort** | Local filesystem reads | `read_file(path)` → str | `LocalFileReaderAdapter` |

---

## Import Safety & Lazy Loading (MANDATORY)

**`import core_infrastructure` NEVER crashes due to missing optional dependencies.**

Optional adapters gracefully degrade to `None` when their dependencies are absent:

```python
from core_infrastructure.database import SQLAlchemyAdapter, MemoryDatabaseAdapter

if SQLAlchemyAdapter is None:
    # sqlalchemy not installed — use MemoryDatabaseAdapter for dev/testing
    db = MemoryDatabaseAdapter(config, logger)
else:
    db = SQLAlchemyAdapter(config, logger)  # type: ignore[assignment]
```

### The Contract

| Symbol | When it's `None` | Install to resolve |
|--------|-------------------|-------------------|
| `SQLAlchemyAdapter` | `sqlalchemy` not installed | `pip install "core-cenf[sqlalchemy]"` |
| `LocalStorageAdapter` | `aiofiles` not installed | `pip install "core-cenf[local-storage]"` |
| `RedisCacheAdapter` | `redis` not installed | `pip install "core-cenf[all]"` |
| `S3StorageAdapter` | `aioboto3` not installed | `pip install "core-cenf[s3]"` |
| `GcsStorageAdapter` | `gcloud` not installed | `pip install "core-cenf[gcs]"` |
| `AzureStorageAdapter` | `azure-storage-blob` not installed | `pip install "core-cenf[azure]"` |
| `JwtAuthAdapter` | `python-jose` not installed | `pip install "core-cenf[all]"` (core dep) |
| `EncryptedSecretAdapter` | `cryptography` not installed | `pip install "core-cenf[all]"` (core dep) |
| `ResilientHTTPAdapter` | `aiohttp` not installed | `pip install "core-cenf[all]"` (core dep) |
| `OTelAdapter` | `opentelemetry` not installed | `pip install "core-cenf[all]"` (core dep) |
| `CasbinPermissionAdapter` | `pycasbin` not installed | `pip install "core-cenf[all]"` (core dep) |
| `LocalFileReaderAdapter` | `aiofiles` not installed | `pip install "core-cenf[local-storage]"` |

**Rule**: ALWAYS check `is None` before using an optional adapter. Never assume it resolves.

### How It Works

core-cenf-py uses **two-layer lazy import protection**:

1. **Root level** (`core_infrastructure/__init__.py`): all ~25 optional adapter imports are wrapped in `try/except ImportError: Adapter = None`
2. **Sub-package level** (`database/__init__.py`, `filestorage/__init__.py`): same pattern, ensuring imports succeed even when only models/ports are needed

This means **every manager Protocol, model, and in-memory test adapter** is always importable with zero optional dependencies. Only production adapters that need extra libraries degrade.

---

## Bootstrap Pattern (ALWAYS use this)

```python
import asyncio
from core_infrastructure.bootstrap import BootstrapOrchestrator
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
# ... import ALL adapters you need

async def main():
    # 1. Config FIRST (root, zero dependencies)
    config = InMemoryConfigAdapter({"app.name": "my-app", "app.env": "dev"})
    
    # 2. Wire managers in dependency order
    logger = InMemoryLoggerAdapter(config_manager=config)
    secrets = InMemorySecretAdapter(config_manager=config, logger_manager=logger)
    # ... wire ALL managers
    
    # 3. Bootstrap orchestrator handles lifecycle
    orchestrator = BootstrapOrchestrator(config, logger, secrets, ...)
    await orchestrator.run()  # startup → wait for signal → shutdown

asyncio.run(main())
```

---

## @ai-directive Reference

Every manager Protocol includes `@ai-directive` annotations. Here are the critical ones:

| Manager | @ai-directive |
|---------|--------------|
| **ConfigManager** | Never access `os.environ` directly. Always use `config.get_string()`. |
| **LoggerManager** | Methods are SYNC only. Use `logger.mask()` before logging any credential. |
| **SecretManager** | `SecretValue.__repr__` is auto-masked. Never log raw `.value`. |
| **ErrorHandlingManager** | `@handle_errors` NEVER swallows — always re-raises. Use `CapturingErrorAdapter` in tests. |
| **ObservabilityManager** | If OTel export fails, degrade gracefully — never throw. |
| **AuthManager** | Set `tenant_id` and `principal_id` contextvars after validation. |
| **CacheManager** | `get_or_set()` uses XFetch stampede mitigation. Cache miss is NOT an error. |
| **DatabaseManager** | Always use `async with db.transaction() as tx:` — never raw sessions. |
| **FileStorageManager** | Never infer MIME type from file extension. |
| **TaskQueueManager** | Payloads MUST be JSON-serializable. |
| **ExternalAPIManager** | Circuit breaker protects by host. Timeouts are mandatory. |
| **FeatureFlagManager** | NEVER throw on evaluation failure — return default. |
| **DependencyManager** | Never pass `module_path` from user input. Always validate against allowlist. |
| **DynamicPromptingManager** | Conditions are dict-based equality. No CEL parser needed for MVP. |
| **AlertManager** | Fire-and-forget. Never block main flow if alert dispatch fails. |
| **RateLimiterManager** | Use `is_allowed()` before any rate-limited operation. |
| **BusEventManager** | Usar BusEventManager para comunicación desacoplada entre componentes. publish() is fire-and-forget. Subscriptions are exact-match only (no wildcards for MVP). |
| **FileReaderPort** | All paths are resolved relative to the adapter's root directory. Never pass absolute user-supplied paths without validation. |

---

## Context Propagation (IMPLICIT — never explicit)

```python
from core_infrastructure.common import context

# SET (done by AuthManager, middleware, etc.)
context.set_correlation_id("req-123")
context.set_tenant_id("cntrs")

# GET (done by LoggerManager, FeatureFlagManager, etc.)
cid = context.get_correlation_id()  # "req-123" — automatically injected into logs
```

**Rule**: NEVER pass context as function arguments. Always use contextvars.

---

## Error Taxonomy

```python
from core_infrastructure.common.errors import TransientError, PermanentError, ValidationError, AuthError, RateLimitError

# TransientError: retryable (network timeout, DB deadlock)
# PermanentError: not retryable (missing resource, invalid config)
# ValidationError: schema violation (Pydantic)
# AuthError: expired token, wrong signature
# RateLimitError: bucket exhausted
```

---

## Testing Patterns

```python
# 1. Use in-memory adapters for unit tests
config = InMemoryConfigAdapter({"db.host": "localhost"})
logger = InMemoryLoggerAdapter(config_manager=config)

# 2. Check captured state
assert "error" in logger.get_logs()[0]["event"]
assert config.get_string("db.host") == "localhost"

# 3. Test error handling
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
error_mgr = CapturingErrorAdapter(config_manager=config, logger_manager=logger, observability_manager=obs)
# ... errors are captured, not re-raised
```

---

## Commit Gate (BEFORE every commit — MANDATORY)

```bash
ruff check src/ tests/         # ZERO errors
mypy src/core_infrastructure/ --strict  # ZERO errors
python -m pytest tests/ -q     # ALL green
```

Any commit that fails ANY of these MUST be reverted and fixed. The CI/CD pipeline enforces these same gates on push.

---

## Pre-Commit Hooks (auto-enforced)

```bash
pre-commit install
```

Hooks check: ruff format, mypy strict, no `r' +'` regex, no bare `asyncio.gather`, no hardcoded `C:\` paths, files ≤250 lines.

---

## CI/CD Pipeline

Every push to `main` and every PR runs:
1. **Lint + Type Check + Test** (ruff, mypy strict, pytest full suite)
2. **Security Scan** (Trivy — blocks CRITICAL/HIGH CVEs)
3. **SBOM Generation** (CycloneDX — software bill of materials)
4. **Stress Tests** (reserved, not yet implemented)

Pipeline: `.github/workflows/ci.yml`

---

## Project Infrastructure

| File | Purpose |
|------|---------|
| `.pre-commit-config.yaml` | Pre-commit hooks (ruff, mypy, CENF rules) |
| `.github/workflows/ci.yml` | CI/CD pipeline |
| `.github/workflows/publish.yml` | GitHub Packages publishing (on release) |
| `sbom.xml` | Generated SBOM (CycloneDX) |
| `migrations/` | Alembic database migrations |
| `.codegraph/` | CodeGraph knowledge graph (local, regenerated with `codegraph index`) |
| `examples/full_demo.py` | Golden path: all 21 managers working together |

---

## Installation (for CENF projects)

```bash
# Option 1: Minimal install (M01-M05 + core + in-memory test adapters)
pip install git+https://github.com/CENFARG/core-cenf-py.git

# Option 2: With production database support
pip install "core-cenf[sqlalchemy] @ git+https://github.com/CENFARG/core-cenf-py.git"

# Option 3: With local file storage
pip install "core-cenf[local-storage] @ git+https://github.com/CENFARG/core-cenf-py.git"

# Option 4: All optional extras
pip install "core-cenf[all] @ git+https://github.com/CENFARG/core-cenf-py.git"

# Option 5: Local development
git clone https://github.com/CENFARG/core-cenf-py.git
cd core-cenf
uv venv .venv && uv pip install -e ".[dev]"
```

### Available Optional Extras

| Extra | What it installs | Enables |
|-------|-----------------|---------|
| `sqlalchemy` | SQLAlchemy 2.0+ | `SQLAlchemyAdapter` |
| `local-storage` | aiofiles 24.0+ | `LocalStorageAdapter` |
| `s3` | aioboto3 14.0+ | `S3StorageAdapter` |
| `gcs` | gcloud-aio-storage 9.0+ | `GcsStorageAdapter` |
| `azure` | azure-storage-blob 12.0+ | `AzureStorageAdapter` |
| `saq` | SAQ 0.15+ | SAQ task queue adapter |
| `postgres` | asyncpg + psycopg[binary] 3.2+ | PostgreSQL support |
| `nats` | nats-py 2.0+ | NATS bus adapter |
| `dev` | pytest, ruff, mypy, faker, etc. | Development & testing |
| `all` | All optional extras combined | Full functionality |

---

## Reference Files

- Full demo: `examples/full_demo.py`
- All specs: `openspec/specs/`
- Bootstrap example: `src/core_infrastructure/bootstrap.py`
- Test fixtures: `tests/conftest.py`
- CI/CD pipeline: `.github/workflows/ci.yml`
- Docusaurus expert prompt: Engram `tools/docusaurus-expert-cenf`
- LLM-optimized index: `llms.txt`

---

## Anti-Patterns — What Agents Should NEVER Do

| ❌ Anti-Pattern | ✅ Correct |
|---|---|
| Import adapter directly in business logic | Import Protocol (port) only |
| Access `os.environ` directly | Use `config.get_string()` |
| Pass context as function arguments | Use `contextvars` (implicit) |
| Assume optional adapter is always available | Check `is None` before use |
| Log raw `SecretValue` | Use `logger.mask()` or `SecretValue.__repr__` (auto-masked) |
| Call model without `@handle_errors` decorator | Always wrap LLM calls with error handler |
| Hardcode paths (`C:\...`) | Use `config.get_path()` or `pathlib` |
| Write sync code in async context | Use `asyncio.to_thread()` for blocking I/O |
| Skip the commit gate | ALWAYS run `ruff + mypy + pytest` before commit |
