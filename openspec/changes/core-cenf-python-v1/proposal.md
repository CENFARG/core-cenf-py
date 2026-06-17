# Proposal: CENF Core Infrastructure — 12 Horizontal Managers (Python 3.12+)

## Intent

Build the foundational infrastructure layer that every future CENF project depends on. This change delivers 12 transversal managers implementing Clean Architecture / Hexagonal (Ports & Adapters) with async-first Python 3.12+, providing configuration, logging, secrets, error handling, observability, auth, caching, database, file storage, task queues, external API, and feature flag capabilities — all with implicit context propagation, RED metrics, and boundary validation.

## Scope

### In Scope
- 12 managers: Config, Logger, Secret, ErrorHandling, Observability, Auth, Cache, Database, FileStorage, TaskQueue, ExternalAPI, FeatureFlag
- Cross-cutting modules: `common/context.py`, `common/errors.py`, `common/lifecycle.py`, `bootstrap.py`
- Protocol ports + adapter implementations per manager
- Pydantic V2 boundary validation at every I/O edge
- OpenTelemetry RED metrics (namespace: `cenf.*`) per manager
- `get_json_schema()` on every manager for Agent Experience (AX)
- AsyncLifecycle protocol (start/stop/health) on all managers
- Unit + integration test suites (pytest-asyncio, testcontainers)
- Manual constructor dependency injection (no DI framework)

### Out of Scope
- Domain logic or business entities
- AI/LLM-specific managers (handled by Agno runtime)
- TypeScript/Node.js implementations (later phase)
- Production deployment pipelines (separate change)
- GraphQL or gRPC transport layers

## Capabilities

### New Capabilities
- `config-manager`: Environment resolution, hot-reload, 12-factor precedence
- `logger-manager`: Structured logging with dev/test/prod profiles
- `secret-manager`: Credential management with TTL cache and Vault adapter
- `error-handling-manager`: Exception taxonomy, ExceptionGroup unwrapping, classification
- `observability-manager`: OpenTelemetry tracing, RED metrics, span management
- `auth-manager`: JWT/OIDC validation, M2M token issuance
- `cache-manager`: KV abstraction with stampede mitigation (aiocache + redis)
- `database-manager`: SQLAlchemy 2.0 async, transaction scopes, generic repositories
- `file-storage-manager`: Async blob operations (aiofiles + aioboto3)
- `task-queue-manager`: SAQ-based async job queue with DLQ support
- `external-api-manager`: Resilient HTTP client with circuit breaker + tenacity retries
- `feature-flag-manager`: Unleash integration with local cache and streaming
- `common-context`: contextvars for correlation_id, tenant_id, trace_id, span_id
- `common-lifecycle`: AsyncLifecycle protocol for startup/shutdown orchestration
- `bootstrap`: Startup ordering with asyncio.TaskGroup

### Modified Capabilities
- None (greenfield project)

## Approach

Each manager follows the same structural pattern:
1. `ports.py` — Python `Protocol` defining the contract
2. `adapters/` — Concrete implementations using OSS libraries
3. `__init__.py` — Public API surface

Bootstrap order (acyclic dependency graph): M01→M02→M03→M05→M04/M06→M07/M08/M09→M10→M11→M12. All managers implement `AsyncLifecycle` for coordinated startup/shutdown via `asyncio.TaskGroup`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/core_infrastructure/config/` | New | ConfigManager port + pydantic-settings adapter |
| `src/core_infrastructure/logger/` | New | LoggerManager port + structlog adapter |
| `src/core_infrastructure/secrets/` | New | SecretManager port + cryptography/hvac adapters |
| `src/core_infrastructure/errors/` | New | ErrorHandlingManager port + taxonomy |
| `src/core_infrastructure/observability/` | New | ObservabilityManager port + OTel SDK adapter |
| `src/core_infrastructure/auth/` | New | AuthManager port + python-jose adapter |
| `src/core_infrastructure/cache/` | New | CacheManager port + redis/aiocache adapter |
| `src/core_infrastructure/database/` | New | DatabaseManager port + SQLAlchemy async adapter |
| `src/core_infrastructure/filestorage/` | New | FileStorageManager port + aiofiles/aioboto3 adapter |
| `src/core_infrastructure/taskqueue/` | New | TaskQueueManager port + SAQ adapter |
| `src/core_infrastructure/external_api/` | New | ExternalAPIManager port + aiohttp/tenacity adapter |
| `src/core_infrastructure/feature_flags/` | New | FeatureFlagManager port + Unleash adapter |
| `src/core_infrastructure/common/` | New | contextvars, error taxonomy, lifecycle protocol |
| `src/core_infrastructure/bootstrap.py` | New | Startup orchestration |
| `tests/unit/` | New | Unit tests per manager |
| `tests/integration/` | New | Integration tests with testcontainers |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Dependency version conflicts (63 packages) | Medium | UV lockfile pinning, CI matrix testing |
| Async complexity in bootstrap ordering | Medium | Strict acyclic graph validation, integration tests |
| OTel SDK initialization overhead | Low | Lazy initialization, configurable exporters |
| SAQ Redis dependency for task queue | Low | Graceful degradation, mock adapter for tests |
| File size >250 lines per module | High | Strict module splitting enforced by ruff |

## Rollback Plan

1. Revert the entire `src/core_infrastructure/` directory (single package, no downstream consumers yet)
2. Delete `openspec/changes/core-cenf-python-v1/` directory
3. No database migrations to rollback (greenfield)
4. No external infrastructure affected (all adapters configurable)

## Dependencies

- Python 3.12+ (PEP 695 type parameters, ExceptionGroup, asyncio.TaskGroup)
- 63 dev dependencies already installed via UV (pyproject.toml)
- Redis server (optional, for cache/task queue integration tests)
- PostgreSQL 16+ (optional, for database integration tests)
- Vault server (optional, for secrets integration tests)
- Unleash server (optional, for feature flag integration tests)

## Success Criteria

- [ ] All 12 managers pass unit tests with >90% coverage
- [ ] All integration tests pass with testcontainers (Redis, PostgreSQL)
- [ ] `mypy --strict` passes with zero errors across all modules
- [ ] `ruff check` passes with zero violations
- [ ] `bootstrap.py` starts and stops all managers in correct order
- [ ] Each manager exposes `get_json_schema()` returning valid JSON Schema
- [ ] No hardcoded values — all config externalized via ConfigManager
- [ ] No blocking I/O in async paths (ruff ASYNC rules pass)
- [ ] RED metrics emitted for all 12 managers under `cenf.*` namespace
- [ ] Error taxonomy correctly classifies TRANSIENT, PERMANENT, VALIDATION, AUTH, RATE_LIMIT
