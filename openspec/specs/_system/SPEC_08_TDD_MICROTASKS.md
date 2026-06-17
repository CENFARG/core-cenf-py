---
Spec_ID: SPEC_08
Title: TDD Microtasks
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [tdd, tasks, m13-m16, microtasks]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_08: TDD Microtasks

## Purpose

Extend the existing tasks.md (which covers M01-M12 in 21 tasks) with implementation task checklist skeleton for M13-M16 and define the TDD micro-task execution protocol.

## M13: DependencyManager Tasks

### TASK_022: DependencyManager Protocol + Models
- **Files**: `src/core_infrastructure/dependency/__init__.py`, `ports.py`, `models.py`
- **Dependencies**: M01 (ConfigManager), M02 (LoggerManager), M04 (ErrorHandlingManager)
- **RED**: `ImportError` — dependency package does not exist
- **GREEN**: `DependencyManager` Protocol with `resolve_class()`, `register()`, `is_known()`, `list_keys()`, `invalidate_cache()`, `get_json_schema()`; `DependencySettings` Pydantic model with `allowlist_paths`, `cache_max_size`, `entry_points_enabled`; `DependencyCatalog` model for registry entries
- **REFACTOR**: `mypy --strict` zero errors; `ruff check` zero violations; file < 250 lines
- **Verification**: `python -c "from core_infrastructure.dependency.ports import DependencyManager"`

### TASK_023: DependencyManager Adapters (Importlib + InMemory)
- **Files**: `adapters/__init__.py`, `importlib_adapter.py`, `in_memory_dependency_adapter.py`, `tests/unit/test_dependency.py`
- **Dependencies**: TASK_022
- **RED**: `pytest tests/unit/test_dependency.py` fails
- **GREEN**: `ImportlibAdapter` resolves `(module_path, class_name)` via `importlib.import_module` lazily; validates against allowlist before import; caches resolved classes; supports `entry_points` discovery; `get_required_packages()` returns list of runtime package names for Dockerfile; `InMemoryDependencyAdapter` dict-based catalog for tests
- **REFACTOR**: Allowlist validation prevents path traversal; `mypy --strict` zero errors; files < 250 lines
- **Verification**: `python -m pytest tests/unit/test_dependency.py -v`

## M14: DynamicPromptingManager Tasks [SPEC ONLY]

### TASK_024: DynamicPromptingManager Protocol + Models
- **Files**: `src/core_infrastructure/dynamic_prompting/__init__.py`, `ports.py`, `models.py`
- **Dependencies**: M01, M02, M04, M05
- **RED**: `ImportError` — dynamic_prompting package does not exist
- **GREEN**: `DynamicPromptingManager` Protocol with `assemble()`, `validate_expressions()`, `get_json_schema()`; `PromptBlock` Pydantic model with `id`, `condition` (CEL), `content`, `priority`; `PromptAssemblySettings` model with `max_blocks`, `cel_timeout_ms`, `cache_enabled`
- **REFACTOR**: `mypy --strict` zero errors; file < 250 lines
- **Verification**: `python -c "from core_infrastructure.dynamic_prompting.ports import DynamicPromptingManager"`

### TASK_025: DynamicPromptingManager Adapter (CEL Evaluator)
- **Files**: `adapters/__init__.py`, `cel_prompting_adapter.py`, `in_memory_prompting_adapter.py`, `tests/unit/test_dynamic_prompting.py`
- **Dependencies**: TASK_024, common/cel_evaluator
- **RED**: `pytest tests/unit/test_dynamic_prompting.py` fails
- **GREEN**: `CELPromptingAdapter` uses `pycel` for sandboxed CEL evaluation; sorts blocks by priority; concatenates matching blocks to base_prompt; `validate_expressions()` compiles AOT and returns syntax errors; `InMemoryPromptingAdapter` for tests
- **REFACTOR**: No `eval()` or `exec()` used; `mypy --strict` zero errors; files < 250 lines
- **Verification**: `python -m pytest tests/unit/test_dynamic_prompting.py -v`

## M15: AlertManager Tasks [SPEC ONLY]

### TASK_026: AlertManager Protocol + Models
- **Files**: `src/core_infrastructure/alert/__init__.py`, `ports.py`, `models.py`
- **Dependencies**: M01, M03, M02, M04, M05, M11, M16
- **RED**: `ImportError` — alert package does not exist
- **GREEN**: `AlertManager` Protocol with `send_alert()`, `register_rule()`, `evaluate_and_alert()`, `get_json_schema()`; `AlertLevel` StrEnum (INFO, WARNING, CRITICAL); `AlertRule` model with `rule_id`, `condition_cel`, `level`, `channels`; `AlertSettings` model with channel configs
- **REFACTOR**: `mypy --strict` zero errors; file < 250 lines
- **Verification**: `python -c "from core_infrastructure.alert.ports import AlertManager"`

### TASK_027: AlertManager Adapters (Slack/Discord/Email)
- **Files**: `adapters/__init__.py`, `multi_channel_adapter.py`, `in_memory_alert_adapter.py`, `tests/unit/test_alert.py`
- **Dependencies**: TASK_026
- **RED**: `pytest tests/unit/test_alert.py` fails
- **GREEN**: `MultiChannelAlertAdapter` dispatches to Slack (webhook), Discord (webhook), Email (SMTP); uses ExternalAPIManager for HTTP I/O; integrates RateLimiterManager per channel; fire-and-forget with error logging; `InMemoryAlertAdapter` collects alerts in list for tests
- **REFACTOR**: Alert failures do NOT block main flow; `mypy --strict` zero errors; files < 250 lines
- **Verification**: `python -m pytest tests/unit/test_alert.py -v`

## M16: RateLimiterManager Tasks [SPEC ONLY]

### TASK_028: RateLimiterManager Protocol + Models
- **Files**: `src/core_infrastructure/ratelimit/__init__.py`, `ports.py`, `models.py`
- **Dependencies**: M01, M02, M07
- **RED**: `ImportError` — ratelimit package does not exist
- **GREEN**: `RateLimiterManager` Protocol with `is_allowed()`, `get_remaining()`, `get_reset_time()`, `configure_bucket()`, `get_json_schema()`; `RateLimitSettings` model with `default_capacity`, `default_refill_rate`, `backend` (memory/redis); `BucketConfig` model with `capacity`, `refill_rate`, `window_type`
- **REFACTOR**: `mypy --strict` zero errors; file < 250 lines
- **Verification**: `python -c "from core_infrastructure.ratelimit.ports import RateLimiterManager"`

### TASK_029: RateLimiterManager Adapters (Token Bucket + Sliding Window)
- **Files**: `adapters/__init__.py`, `token_bucket_adapter.py`, `sliding_window_adapter.py`, `in_memory_ratelimit_adapter.py`, `tests/unit/test_ratelimit.py`
- **Dependencies**: TASK_028
- **RED**: `pytest tests/unit/test_ratelimit.py` fails
- **GREEN**: `TokenBucketAdapter` implements token bucket algorithm with configurable capacity and refill rate; `SlidingWindowAdapter` implements sliding window log for precision; Redis backend for distributed state; returns standard headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`; `InMemoryRateLimitAdapter` for tests
- **REFACTOR**: `mypy --strict` zero errors; files < 250 lines; OTel metrics `cenf.ratelimit.allowed_total` and `cenf.ratelimit.denied_total` emitted
- **Verification**: `python -m pytest tests/unit/test_ratelimit.py -v`

## TDD Micro-Task Execution Protocol

### RED Phase
1. Write a failing test that exercises ONE requirement
2. Run `pytest` — confirm it fails with expected error
3. Do NOT write implementation code yet

### GREEN Phase
1. Write MINIMUM implementation to make the test pass
2. Run `pytest` — confirm it passes
3. Do NOT refactor yet

### REFACTOR Phase
1. Clean up code while keeping tests green
2. Run `mypy --strict` — zero errors required
3. Run `ruff check` — zero violations required
4. Verify file size < 250 lines

### Completion Criteria
- All tests pass: `pytest tests/unit/test_{manager}.py -v`
- Type checking: `mypy --strict src/core_infrastructure/`
- Linting: `ruff check src/core_infrastructure/`
- Coverage: >90% per manager
