# Proposal: Fix Eager Import Chain in core-cenf-py

## Intent

`import core_infrastructure` crashes with `ModuleNotFoundError` when optional dependencies (`sqlalchemy`, `aiofiles`) are absent. The root `__init__.py` already wraps adapter imports in `try/except ImportError`, but the sub-package `__init__.py` files for `database/` and `filestorage/` eagerly import optional-dependent adapters BEFORE the root's protective blocks can execute. Consumers are forced to install libraries they never use, breaking the library's promise of graceful degradation.

## Scope

### In Scope

- Wrap optional-dependent adapter imports in `try/except ImportError` inside `database/__init__.py` and `filestorage/__init__.py`, matching the established root `__init__.py` pattern.
- Reorder imports so models/ports load before optional adapters in both sub-package files.
- Add `aiofiles` as an optional `[local-storage]` extra in `pyproject.toml` (currently only present as `types-aiofiles` in `[dev]`).
- Add a regression test asserting `import core_infrastructure` succeeds with only core deps installed.
- Update `__all__` in both files to include the optional symbols even when `None`.

### Out of Scope

- Applying the same pattern proactively to all 19 managers (only the 2 crashing ones are in scope).
- PEP 562 `__getattr__` lazy loading (Option B from exploration).
- DependencyManager (M13) lazy resolution (Option C from exploration).
- Changes to adapter implementations themselves.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None.

> This is a pure internal refactor of import mechanics. No manager's runtime behavior, Protocol surface, or spec-level requirement changes.

## Approach

Apply **Option A** from the exploration report: minimal `try/except ImportError` blocks inside the two offending sub-package `__init__.py` files. This mirrors the exact pattern already proven across ~25 adapter imports in the root `__init__.py` (lines 170-313). Each optional adapter symbol becomes `None` (with `# type: ignore[assignment,misc]`) when its dependency is missing, restoring graceful degradation. `aiofiles` is promoted to a named optional extra so users who want local storage have a clean install path.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/core_infrastructure/database/__init__.py` | Modified | Reorder imports; wrap `SQLAlchemyAdapter` in try/except |
| `src/core_infrastructure/filestorage/__init__.py` | Modified | Reorder imports; wrap `LocalStorageAdapter` in try/except |
| `pyproject.toml` | Modified | Add `[local-storage]` optional extra with `aiofiles` |
| `tests/test_import_safety.py` | New | Regression test for core-only import success |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| New future adapter added eagerly without try/except | Low | Regression test fails on any such regression |
| `__all__` / mypy strict complains about `None` assignment | Low | Use `# type: ignore[assignment,misc]` per established root pattern |
| Users unaware of new `[local-storage]` extra | Low | Document in README install section |

## Rollback Plan

Revert the 2 `__init__.py` files and `pyproject.toml` change. The regression test can remain (it will simply document the pre-fix crash). Single-commit revert — no data or migration concerns.

## Dependencies

- None new at runtime. `aiofiles` becomes opt-in via `[local-storage]` extra.

## Success Criteria

- [ ] `pip install core-cenf && python -c "import core_infrastructure"` succeeds without `sqlalchemy` or `aiofiles` installed.
- [ ] `SQLAlchemyAdapter` is `None` when sqlalchemy absent; resolves to the class when present.
- [ ] `LocalStorageAdapter` is `None` when aiofiles absent; resolves to the class when present.
- [ ] Existing `mypy --strict` and `ruff check` gates remain green.
- [ ] Regression test `test_import_safety.py` passes in a core-deps-only environment.
