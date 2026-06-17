---
Spec_ID: SPEC_05
Title: Workflows
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [bootstrap, lifecycle, startup, shutdown, signals]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_05: Workflows

## Purpose

Define the bootstrap lifecycle: startup order, shutdown reverse order, health aggregation, error recovery state machine, and signal handling for all 16 managers.

## Bootstrap Lifecycle

### Startup Order (16 Managers)

The system SHALL start managers in strict dependency order using `asyncio.TaskGroup`:

| Order | Manager | Dependency Check |
|-------|---------|-----------------|
| 1 | ConfigManager (M01) | None — bootstraps from env vars + YAML |
| 2 | LoggerManager (M02) | M01 healthy |
| 3 | SecretManager (M03) | M01, M02 healthy |
| 4 | ErrorHandlingManager (M04) | M01, M02, M05 healthy |
| 5 | ObservabilityManager (M05) | M01, M02, M03 healthy |
| 6 | AuthManager (M06) | M01, M02, M03, M05 healthy |
| 7 | CacheManager (M07) | M01, M02, M03, M04 healthy |
| 8 | DatabaseManager (M08) | M01-M05 healthy |
| 9 | FileStorageManager (M09) | M01-M04 healthy |
| 10 | TaskQueueManager (M10) | M01-M04, M07 healthy |
| 11 | ExternalAPIManager (M11) | M01-M06, M05 healthy |
| 12 | FeatureFlagManager (M12) | M01-M04, M07, M11 healthy |
| 13 | DependencyManager (M13) | M01, M02, M04 healthy |
| 14 | DynamicPromptingManager (M14) | M01, M02, M04, M05 healthy |
| 15 | AlertManager (M15) | M01-M05, M11, M16 healthy |
| 16 | RateLimiterManager (M16) | M01, M02, M07 healthy |

#### Scenario: Sequential startup with TaskGroup

- GIVEN BootstrapOrchestrator.start_all() is called
- WHEN M01 (ConfigManager) starts successfully
- THEN M02 (LoggerManager) starts
- AND each manager starts only after its dependencies are healthy
- AND `asyncio.TaskGroup` is used (NOT `asyncio.gather`)

### Fail-Fast on Startup Failure

If ANY manager fails during startup:
1. Log the failure at ERROR level with full stack trace
2. Stop ALL already-started managers in REVERSE order
3. Raise `PermanentError` with the failed manager name
4. Exit with non-zero code

#### Scenario: Startup failure cascades to shutdown

- GIVEN M08 (DatabaseManager) fails during start()
- WHEN the failure is detected
- THEN M07, M06, M05, M04, M03, M02, M01 are stopped in reverse order
- AND BootstrapOrchestrator raises `PermanentError("database startup failed")`

## Shutdown Order (Reverse)

Shutdown SHALL proceed in exact reverse order: M16 → M15 → ... → M01.

Each manager's `stop()` method:
1. Flushes pending data (telemetry, logs, transactions)
2. Closes connections (Redis, DB, HTTP sessions)
3. Releases resources (file handles, locks)
4. Sets `_stopped = True`

#### Scenario: Clean shutdown

- GIVEN all 16 managers are running
- WHEN `stop_all()` is called
- THEN RateLimiterManager stops first
- AND ConfigManager stops last
- AND ObservabilityManager.flush() is called before stop completes
- AND all managers report `status="healthy"` during shutdown (graceful)

## Health Aggregation

### Health Check Protocol

The system SHALL aggregate health from all managers:
- `healthy`: All managers report `status="healthy"`
- `degraded`: One or more managers report `status="degraded"`, none report `unhealthy`
- `unhealthy`: One or more managers report `status="unhealthy"`

#### Scenario: Health aggregation with degraded manager

- GIVEN CacheManager reports `status="degraded"` (Redis reconnecting)
- AND all other 15 managers report `status="healthy"`
- WHEN `health_all()` is called
- THEN system health is `degraded`
- AND the response includes which manager is degraded

## Error Recovery State Machine

Each manager SHALL implement a recovery state machine:

```
healthy ──[failure]──► degraded ──[recovery]──► healthy
   │                       │
   │                       └──[timeout]──► unhealthy
   │
   └──[critical failure]──► unhealthy ──[manual intervention]──► healthy
```

### Recovery Rules

- `degraded` → automatic recovery attempt within configurable timeout
- `unhealthy` → requires manual intervention or system restart
- Recovery attempts emit `cenf.{manager}.recovery_attempt_total` counter
- Successful recovery emits `cenf.{manager}.recovery_success_total` counter

## Signal Handling

### POSIX Signals (Linux/macOS)

| Signal | Behavior |
|--------|----------|
| `SIGTERM` | Graceful shutdown: call `stop_all()` then exit(0) |
| `SIGINT` | Graceful shutdown (same as SIGTERM) |
| `SIGHUP` | Hot-reload configuration: call `reload()` on ConfigManager |

### Windows Fallback

Windows does not support SIGTERM/SIGINT natively. The system SHALL:
1. Use `signal.signal(signal.SIGBREAK, handler)` for Ctrl+Break
2. Use `signal.signal(signal.SIGINT, handler)` for Ctrl+C
3. Register a Windows Console Control Handler via `ctypes` for close events

#### Scenario: SIGTERM triggers graceful shutdown

- GIVEN the application is running with all 16 managers
- WHEN SIGTERM is received
- THEN `stop_all()` is called
- AND all managers stop in reverse order
- AND the process exits with code 0
