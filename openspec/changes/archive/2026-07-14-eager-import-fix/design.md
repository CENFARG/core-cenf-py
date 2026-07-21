# Design: Eager Import Fix

## Technical Approach

Mirror the **proven try/except pattern** already used in `src/core_infrastructure/__init__.py` (lines 170–313) inside the two offending sub-package `__init__.py` files. The fix has three moving parts, all minimal-blast-radius:

1. **Reorder** imports in `database/__init__.py` and `filestorage/__init__.py` so Protocol + model symbols (zero optional deps) load **before** any adapter.
2. **Wrap** each adapter import that transitively pulls an optional third-party package (`sqlalchemy`, `aiofiles`) in `try: import …; except ImportError: Name = None`. Symbol stays in `__all__` either way, so `from X import Y` keeps working and resolves to `None` when the dep is absent.
3. **Add `aiofiles`** as a named `[local-storage]` extra in `pyproject.toml`, giving consumers who want `LocalStorageAdapter` a clean install path (`pip install "core-cenf[local-storage]"`).

This is the same defensive-import strategy the root package already ships; the bug was that the sub-packages were never updated to match.

## Architecture Decisions

| # | Decision | Chosen | Rejected | Rationale |
|---|----------|--------|----------|-----------|
| D1 | Import strategy | **try/except in sub-package `__init__.py`** | `__getattr__` lazy (PEP 562) | Proven in root `__init__.py` already (lines 170–313). 2-file change. `__getattr__` breaks `from X import Y`, breaks mypy static analysis, and is unfamiliar to most contributors. |
| D2 | Symbol shape when dep absent | **`Name = None` + keep in `__all__`** | Remove from `__all__` | `hasattr(module, "X")` and `module.X is None` both work; callers get a single, checkable contract. Removing from `__all__` would break star-imports and make the symbol "disappear", requiring defensive `getattr`. |
| D3 | Use `DependencyManager` (M13) | **No** | Resolve adapters at runtime via `DependencyManager.resolve_class(...)` | Massive overkill for a packaging bug. DependencyManager needs a runtime instance at import time — chicken-and-egg. Reserve M13 for true late-binding plugin discovery. |
| D4 | `aiofiles` packaging | **New `[local-storage]` extra; add to `all`** | Add to core `dependencies` | Mirrors existing `sqlalchemy`, `s3`, `gcs`, `azure` extras. Core stays lean; opt-in storage backends stay opt-in. |
| D5 | Extra name for SQLAlchemy | **Keep existing `sqlalchemy`** (do NOT add `[database]` alias) | Add `[database]` synonym | Minimal change. Spec scenario text mentions `[database]` as an alternate spelling; we honor intent by keeping the working `[sqlalchemy]` extra and documenting it. No rename churn. |
| D6 | Wrap `Memory*` adapters too | **Yes — wrap in try/except** | Assume always importable | Matches root pattern (lines 196–200, 236–239). Defense in depth: if a memory adapter gains a dep later, import safety is preserved. Spec scenario asserts `MemoryDatabaseAdapter is not None` when sqlalchemy absent — wrap is harmless because its import succeeds. |

## Data Flow — Import Chain

### Current (BROKEN)

```
import core_infrastructure
  │
  ├─ from .database.models import DatabaseConfig          # triggers…
  │     └─ executes database/__init__.py FIRST
  │           ├─ from .adapters.memory_database_adapter import MemoryDatabaseAdapter  ✓
  │           ├─ from .adapters.sqlalchemy_adapter   import SQLAlchemyAdapter
  │           │       └─ import sqlalchemy  ❌ ModuleNotFoundError  → ENTIRE import crashes
  │           └─ (models/ports never reached)
  └─ from .filestorage.models import FileRef             # same pattern
        └─ executes filestorage/__init__.py FIRST
              ├─ from .adapters.local_storage_adapter import LocalStorageAdapter
              │       └─ import aiofiles  ❌ ModuleNotFoundError
              └─ (never reached)
```

### Proposed (FIXED)

```
import core_infrastructure
  │
  ├─ from .database.models import DatabaseConfig          # triggers…
  │     └─ executes database/__init__.py (REORDERED)
  │           ├─ from .models  import DatabaseConfig, ...   ✓ (core-only)
  │           ├─ from .ports   import DatabaseManager, ...  ✓ (core-only)
  │           ├─ try: from .adapters.memory_database_adapter import MemoryDatabaseAdapter
  │           │   except ImportError: MemoryDatabaseAdapter = None        ✓ (passes)
  │           └─ try: from .adapters.sqlalchemy_adapter import SQLAlchemyAdapter
  │               except ImportError: SQLAlchemyAdapter = None           ✓ (graceful)
  └─ from .filestorage.models import FileRef             # same pattern
        └─ executes filestorage/__init__.py (REORDERED)
              ├─ from .models  import FileRef, StorageConfig, UploadResult ✓
              ├─ from .ports   import FileStorageManager                  ✓
              ├─ try: LocalStorageAdapter …  except ImportError: = None   ✓
              └─ try: MemoryStorageAdapter … except ImportError: = None   ✓
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/core_infrastructure/database/__init__.py` | Modify | Reorder (models/ports before adapters); wrap `MemoryDatabaseAdapter` and `SQLAlchemyAdapter` each in `try/except ImportError → None`. |
| `src/core_infrastructure/filestorage/__init__.py` | Modify | Reorder (models/ports before adapters); wrap `LocalStorageAdapter` and `MemoryStorageAdapter` each in `try/except ImportError → None`. |
| `pyproject.toml` | Modify | Add `local-storage = ["aiofiles>=24.0"]` extra; add `local-storage` to the `all` aggregate extra. |
| `tests/test_import_safety.py` | Create | Regression test asserting the graceful-degradation contract from the spec. |

### Key diff — `database/__init__.py` (imports block only)

```python
# Safe imports — zero optional deps
from core_infrastructure.database.models import DatabaseConfig, PaginatedResult, RepositoryQuery
from core_infrastructure.database.ports import DatabaseManager, GenericRepository, TransactionScope

# Optional adapters — gracefully degrade if optional deps missing
try:
    from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
except ImportError:
    MemoryDatabaseAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter
except ImportError:
    SQLAlchemyAdapter = None  # type: ignore[assignment,misc]
```

`filestorage/__init__.py` follows the identical shape (see Data Flow diagram). `__all__` is unchanged in both files — symbols remain listed even when `None`.

### Key diff — `pyproject.toml`

```toml
local-storage = ["aiofiles>=24.0"]
# …
all = [
    "core-cenf[sqlalchemy,postgres,s3,gcs,azure,saq,nats,local-storage]",
]
```

## Interfaces / Contracts

No new public symbols. Existing contract tightened:

```python
# Every adapter symbol in a sub-package __all__ is now EITHER a class OR None.
# Callers MUST treat None as "dependency not installed":
from core_infrastructure.database import SQLAlchemyAdapter
if SQLAlchemyAdapter is None:
    raise RuntimeError("Install with: pip install 'core-cenf[sqlalchemy]'")
```

This matches the root-package contract already documented in `src/core_infrastructure/__init__.py:25-29`.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Core import succeeds without optional deps | `tests/test_import_safety.py`: import `core_infrastructure`, assert no raise; assert `SQLAlchemyAdapter is None` and `LocalStorageAdapter is None` when the deps are absent; assert `MemoryDatabaseAdapter is not None` and `MemoryStorageAdapter is not None` (core-only deps). |
| Unit | Symbols present in `__all__` regardless of dep presence | Static check: every name in `__all__` resolves (possibly to `None`). |
| Integration | Adapter resolves when extra installed | Skipped in dev env if extra present; assert `SQLAlchemyAdapter`/`LocalStorageAdapter` are classes when the corresponding packages are importable. |
| Regression gate | Future adapters can't silently reintroduce eager imports | Test imports the package in a subprocess with `sqlalchemy` and `aiofiles` masked via `sys.modules` shim — fails CI if any new eager import sneaks in. |

The regression test must run in the **default CI matrix** (not gated behind an extra), so the core-only path is enforced on every push.

## Migration / Rollout

No migration required. Pure additive/defensive change:

- **Backward compatible**: existing `import core_infrastructure` calls that worked before still work.
- **Forward compatible**: previously-crashing calls in minimal envs now succeed.
- **Behavior change for direct sub-package importers**: `from core_infrastructure.database import SQLAlchemyAdapter` no longer raises at import time; it returns `None` if `sqlalchemy` is absent. Documented in module docstring + release notes.
- **No data migration, no feature flags, no phased rollout.** Ship in next patch release (0.1.2).

## Open Questions

- [ ] Confirm `MemoryDatabaseAdapter` and `MemoryStorageAdapter` have **zero** optional-dep imports (spec assumes this; verify during apply). If they import an optional dep, the `try/except` wraps it safely anyway.
- [ ] Decide whether to backport the `# type: ignore[assignment,misc]` comment style vs. a module-level `# noqa` — root package uses the `type: ignore` form; we follow that convention.
