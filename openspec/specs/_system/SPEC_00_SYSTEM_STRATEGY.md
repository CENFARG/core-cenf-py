---
Spec_ID: SPEC_00
Title: System Strategy
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [architecture, strategy, principles]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_00: System Strategy

## Purpose

Define the vision, core architectural principles, bounded contexts, and strategic constraints for the CENF Core Infrastructure — the foundational layer every CENF project depends on.

## Vision

Build a sovereign, resilient, and highly observable infrastructure platform over Python 3.12+ with async-first design, enabling rapid development of agentic applications on the Agno framework while maintaining strict separation between infrastructure and domain logic.

## Core Principles

### P01: Clean Architecture / Hexagonal

The system SHALL enforce unidirectional dependency flow inward. Domain logic depends on ports. Adapters implement ports. No layer imports from outer layers.

#### Scenario: Dependency direction enforcement

- GIVEN a manager adapter in `src/core_infrastructure/cache/adapters/`
- WHEN the adapter imports from another manager
- THEN it MUST import only from `ports.py`, never from `adapters/` of another manager
- AND `mypy --strict` MUST fail if an adapter imports an outer-layer module

### P02: Zero-Trust Security

All credentials SHALL be managed through SecretManager. No direct `os.environ` access outside ConfigManager. No secrets in logs, error messages, or telemetry.

#### Scenario: No direct env access

- GIVEN any manager adapter code
- WHEN the code attempts to read `os.environ` directly
- THEN the adapter SHALL be rejected in code review
- AND the correct pattern is `config.get_string("key")` via ConfigManager

### P03: Agent Experience (AX) Discoverability

Every manager SHALL expose `get_json_schema()` returning a valid JSON Schema for LLM agent function calling. Agents MUST be able to discover and invoke manager capabilities without alucination.

#### Scenario: Schema discovery

- GIVEN an LLM agent needs to use CacheManager
- WHEN the agent calls `cache_manager.get_json_schema()`
- THEN it receives a valid JSON Schema describing all available methods
- AND the agent can construct valid function calls from the schema

### P04: Event-Loop Safety

Blocking synchronous I/O (time.sleep, requests, synchronous file reads) SHALL NOT appear in async paths. All async managers SHALL use `asyncio.TaskGroup` for structured concurrency — `asyncio.gather` is prohibited for infrastructure operations.

#### Scenario: No blocking I/O

- GIVEN an async manager method
- WHEN the code contains `time.sleep()` or `requests.get()`
- THEN `ruff check` with ASYNC rules SHALL flag the violation
- AND the correct pattern is `asyncio.sleep()` or `aiohttp` respectively

### P05: Fail-Fast Bootstrap

Configuration validation SHALL occur at startup. If CoreSettings fails Pydantic validation, bootstrap exits immediately. No manager starts with invalid configuration.

#### Scenario: Bootstrap fails on invalid config

- GIVEN a YAML config file with `env: "invalid_value"`
- WHEN BootstrapOrchestrator calls `start_all()`
- THEN CoreSettings validation fails
- AND bootstrap exits with non-zero code before any manager starts

## Bounded Contexts

| Context | Responsibility | Managers |
|---------|---------------|----------|
| **Infrastructure** | Core horizontal services | M01-M16 (all managers) |
| **Domain** | Business entities and rules | Out of scope — consumers |
| **Agentic** | LLM/Tool/Memory management | Agno runtime — out of scope |

## Strategic Constraints

1. **Python 3.12+ only** — PEP 695 type parameters, ExceptionGroup, asyncio.TaskGroup required.
2. **No DI framework** — Manual constructor injection only.
3. **All external libraries MUST be MIT or Apache 2.0** — No LGPL (psycopg3 prohibited, use asyncpg).
4. **No hardcoded values** — All configuration externalized via ConfigManager.
5. **No domain imports in infrastructure** — Managers know nothing about business entities.
6. **Async-first** — All I/O-bound operations are async. Sync-only where the underlying library is sync (structlog).

## Dependency Graph (Acyclic)

```
ConfigManager (M01) ──► LoggerManager (M02) ──► SecretManager (M03)
    │                       │                       │
    ▼                       ▼                       ▼
ErrorHandling (M04)   Observability (M05)      AuthManager (M06)
    │                       │                       │
    ▼                       ▼                       ▼
CacheManager (M07)    DatabaseManager (M08)     FileStorage (M09)
    │                       │                       │
    ▼                       ▼                       ▼
TaskQueue (M10)       ExternalAPI (M11)        FeatureFlag (M12)
    │                       │                       │
    ▼                       ▼                       ▼
Dependency (M13)      DynamicPrompting (M14)    AlertManager (M15)
                                                │
                                                ▼
                                        RateLimit (M16)
```

## Non-Goals

- Domain logic or business entities
- AI/LLM-specific managers (handled by Agno)
- TypeScript/Node.js implementations (later phase)
- Production deployment pipelines (separate change)
- GraphQL or gRPC transport layers
