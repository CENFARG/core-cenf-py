# Tasks: Eager Import Fix

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~82 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | pending (single slice resolves at apply) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Safe import contract for `database` + `filestorage` sub-packages | PR 1 | Single PR; touches 2 sub-packages + pyproject + 1 new test file |

## Phase 1: Package Config (`pyproject.toml`)

- [x] 1.1 Add `local-storage = ["aiofiles>=24.0"]` to `[project.optional-dependencies]`
- [x] 1.2 Add `local-storage` to the `all` aggregate extra list
- [x] 1.3 Bump version `0.1.1` → `0.1.2` (patch release per design rollout)

## Phase 2: Fix `src/core_infrastructure/database/__init__.py`

- [x] 2.1 Reorder imports: `models` + `ports` first, then adapter `try/except` blocks
- [x] 2.2 Wrap `MemoryDatabaseAdapter` import in `try/except ImportError → None` with `# type: ignore[assignment,misc]`
- [x] 2.3 Wrap `SQLAlchemyAdapter` import in `try/except ImportError → None` with `# type: ignore[assignment,misc]`
- [x] 2.4 Leave `__all__` unchanged (symbols listed even when `None`)

## Phase 3: Fix `src/core_infrastructure/filestorage/__init__.py`

- [x] 3.1 Reorder imports: `models` + `ports` first, then adapter `try/except` blocks
- [x] 3.2 Wrap `LocalStorageAdapter` import in `try/except ImportError → None`
- [x] 3.3 Wrap `MemoryStorageAdapter` import in `try/except ImportError → None`
- [x] 3.4 Leave `__all__` unchanged

## Phase 4: Regression Test (`tests/test_import_safety.py`)

- [x] 4.1 `test_core_import_succeeds_without_optional_deps` — `import core_infrastructure` does not raise
- [x] 4.2 `test_database_subpackage_safe_without_sqlalchemy` — `SQLAlchemyAdapter is None` when dep absent; `MemoryDatabaseAdapter` resolves
- [x] 4.3 `test_filestorage_subpackage_safe_without_aiofiles` — `LocalStorageAdapter is None` when dep absent; `MemoryStorageAdapter` resolves
- [x] 4.4 `test_optional_adapters_resolve_when_deps_present` — skip via `importlib.util.find_spec` if dep installed; assert it is a class
- [x] 4.5 `test_local_storage_extra_metadata` — read wheel metadata, assert `[local-storage]` lists `aiofiles`
- [x] 4.6 `test_regression_subprocess_sys_modules_shim` — `subprocess` + `sys.modules` shim masks `sqlalchemy` + `aiofiles`; assert subprocess exits 0
- [x] 4.7 Run commit gates: `ruff check src/ tests/`, `mypy src/core_infrastructure/ --strict`, `python -m pytest tests/ -q` — all green

## Out of Scope (Do NOT Touch)

- Any adapter implementation in `src/core_infrastructure/*/adapters/`
- Any other sub-package `__init__.py` (only `database` + `filestorage` are in scope)
- `core_infrastructure/__init__.py` root file (already correct)
- `__all__` lists beyond the two in-scope files
