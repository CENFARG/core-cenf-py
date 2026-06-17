---
Spec_ID: SPEC_LIFECYCLE
Title: Common Lifecycle Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [lifecycle, health, startup, shutdown, async]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_LIFECYCLE: Common Lifecycle

## Purpose

Define the `AsyncLifecycle` Protocol for startup/shutdown/health-check coordination and the `HealthStatus` Pydantic model. Includes `LifecycleManager` aggregator for batch health checks.

## Python API

```python
from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable
from pydantic import BaseModel, Field

class HealthStatus(BaseModel):
    service: str = Field(..., min_length=1, max_length=128)
    status: Literal["healthy", "degraded", "unhealthy"] = Field(default="healthy")
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, str] = Field(default_factory=dict)
    def is_healthy(self) -> bool: ...

@runtime_checkable
class AsyncLifecycle(Protocol):
    """@ai-directive: start() MUST be idempotent. stop() MUST be safe to call multiple times."""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def health(self) -> HealthStatus: ...

class LifecycleManager:
    def __init__(self) -> None: ...
    def register(self, service: AsyncLifecycle) -> None: ...
    async def health_all(self) -> dict[str, HealthStatus]: ...
    async def is_system_healthy(self) -> bool: ...
```

## Gherkin Scenarios

### Scenario: start() is idempotent

- GIVEN a manager with `_started = False`
- WHEN `start()` is called
- THEN `_started` becomes `True` and resources are initialized
- WHEN `start()` is called again
- THEN nothing happens (idempotent — no double initialization)

### Scenario: stop() is safe to call multiple times

- GIVEN a manager with `_stopped = False`
- WHEN `stop()` is called
- THEN `_stopped` becomes `True` and resources are released
- WHEN `stop()` is called again
- THEN nothing happens (safe — no double-close errors)

### Scenario: health() never raises

- GIVEN a manager with an internal error condition
- WHEN `health()` is called
- THEN it returns `HealthStatus(status="degraded", details={"error": "..."})`
- AND it does NOT raise an exception

### Scenario: LifecycleManager health_all aggregates

- GIVEN 3 services registered: config, logger, cache
- WHEN `health_all()` is called
- THEN it returns a dict with 3 entries
- AND each entry's key is the service name from `HealthStatus.service`

### Scenario: is_system_healthy requires all healthy

- GIVEN config=healthy, logger=healthy, cache=degraded
- WHEN `is_system_healthy()` is called
- THEN it returns `False` (not ALL are healthy)

### Scenario: HealthStatus details must not contain secrets

- GIVEN a manager's health check
- WHEN `health()` returns a HealthStatus
- THEN `details` dict MUST NOT contain secrets or credentials
- AND it MAY contain diagnostic info like "connection_pool_size: 10"

## Error Classification

This module does not raise errors. `health()` catches internal errors and returns `degraded` status.

## RED Metrics

None — this module defines the lifecycle contract. Individual managers emit metrics during start/stop/health.

## Test Requirements

- **Unit**: Test idempotency of start()/stop(), health() never raises.
- **Integration**: LifecycleManager registers and health-checks multiple services.
- **E2E**: BootstrapOrchestrator uses LifecycleManager for system-wide health.

## Do's and Don'ts

**Do**:
- Track `_started` and `_stopped` flags for idempotency
- Return `status="degraded"` on internal health check failures
- Exclude secrets from HealthStatus.details

**Don't**:
- Add new methods to AsyncLifecycle without updating all 16 managers
- Let health() raise exceptions (always return a HealthStatus)
- Include credentials or PII in health check details
