## Exploration: Eager Import Chain in core-cenf-py

### Current State

The root `core_infrastructure/__init__.py` already has a well-designed lazy import strategy for production adapters: ALL adapter imports that depend on optional libraries are wrapped in `try/except ImportError` blocks, setting the symbol to `None` on failure (lines 170-313).

**The problem**: The root package's try/except blocks NEVER FIRE for certain managers because the crash happens at the SUB-PACKAGE level, before the root `__init__.py` can execute.

#### The Crash Chain

When a consumer does `import core_infrastructure`:

1. Python executes `core_infrastructure/__init__.py`
2. It hits line 76: `from core_infrastructure.database.models import DatabaseConfig, ...`
3. To resolve this, Python must first execute `database/__init__.py` (the sub-package)
4. `database/__init__.py` line 20: `from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter`
5. `sqlalchemy_adapter.py` line 23: `from sqlalchemy import func, select` → **`ModuleNotFoundError` if sqlalchemy is not installed**
6. The root `__init__.py`'s try/except at line 202-205 is NEVER reached — Python already crashed at step 5

Same pattern applies to `filestorage/` (LocalStorageAdapter → aiofiles).

#### Why the root try/except Pattern Works for Most Managers

The root `__init__.py` has TWO import phases:
1. **Lines 34-163**: Eager imports of models, ports, and always-safe adapters (these trigger sub-package `__init__.py` execution)
2. **Lines 169-313**: try/except- wrapped adapter imports

The sub-package `__init__.py` files MUST NOT crash during phase 1. Currently, two of them do.

---

### Managers With Eager Adapter Imports

| Manager | `__init__.py` | Eager adapter imports | Will crash? | Why |
|---------|---------------|----------------------|-------------|-----|
| `database/` | line 20 | `SQLAlchemyAdapter` | **YES** | Imports `sqlalchemy` — optional `[sqlalchemy]` extra only |
| `filestorage/` | line 19 | `LocalStorageAdapter` | **YES** | Imports `aiofiles` — NOT a core dep, only in `[dev]` |
| `auth/` | lines 19-20 | `JwtAuthAdapter`, `StaticAuthAdapter` | No | `jose` is a core dependency (line 34 of pyproject.toml) |
| `secrets/` | lines 18-19 | `EncryptedSecretAdapter` | No | `cryptography` is a core dependency (line 32) |
| `external_api/` | lines 7-12 | `ResilientHTTPAdapter` | No | `aiohttp` is a core dependency (line 28) |
| `permission/` | lines 19-20 | `CasbinPermissionAdapter` | No | `pycasbin` is a core dependency (line 35) |
| `i18n/` | line 19 | `YamlI18nAdapter` | No | `pyyaml` is a core dependency (line 23) |
| `cache/` | line 20 | `RedisCacheAdapter` | No | Uses lazy `import redis.asyncio` inside functions |
| `observability/` | line 22 | `OTelAdapter` | No | Uses lazy `import opentelemetry` inside functions |
| `licence/` | — | No adapters imported in `__init__.py` | No | Only models/ports |
| `update/` | empty | No adapters imported in `__init__.py` | No | Empty file |
| `bus_event/` | empty | No adapters imported in `__init__.py` | No | Empty file |
| `taskqueue/` | line 7 | Only `MemoryTaskQueueAdapter` | No | Zero external deps |
| `feature_flags/` | line 7 | Only `MemoryFeatureFlagAdapter` | No | Zero external deps |
| `ratelimit/` | lines 16-17 | Only in-memory adapters | No | Zero external deps |
| `dependency/` | lines 16-17 | Only importlib + in-memory adapters | No | Zero external deps |
| `dynamic_prompting/` | line 18 | Only `ConditionalPromptAdapter` | No | Zero external deps |
| `state_machine/` | lines 8-13 | Only in-memory + production adapters | No | Zero external deps at module level |
| `alert/` | line 17 | Only `DispatchAlertAdapter` | No | Zero external deps at module level |

**Bottom line**: Only **2 managers** out of 19 have the crash-causing pattern: `database/` and `filestorage/`.

---

### Eager Adapter Files and Their External Dependencies

| Adapter file | External import | Where imported eagerly | Dep type |
|-------------|----------------|----------------------|----------|
| `database/adapters/sqlalchemy_adapter.py:23-25` | `from sqlalchemy import func, select` | `database/__init__.py:20` | optional `[sqlalchemy]` |
| `filestorage/adapters/local_storage_adapter.py:23-24` | `import aiofiles` | `filestorage/__init__.py:19` | only in `[dev]` optional |

**These are the only two crash points.** All other adapter files with optional deps are either:
- Only imported via the root `__init__.py`'s try/except blocks (safe), OR
- Imported eagerly but their deps ARE core dependencies (safe), OR
- Use lazy imports internally (safe)

Adapters protected by root try/except (NOT in sub-package `__init__.py`):
- `auth/adapters/jwt_auth_adapter.py` (jose — but also eagerly imported in `auth/__init__.py`)
- `licence/adapters/jwt_licence_adapter.py` (jose)
- `cache/adapters/redis_cache_adapter.py` (lazy redis)
- `secrets/adapters/encrypted_secret_adapter.py` (cryptography — but also eagerly imported in `secrets/__init__.py`)
- `observability/adapters/otel_adapter.py` (lazy opentelemetry)
- `external_api/adapters/resilient_http_adapter.py` (aiohttp — but also eagerly imported in `external_api/__init__.py`)
- `filestorage/adapters/s3_storage_adapter.py` (aiobotocore)
- `filestorage/adapters/gcs_storage_adapter.py` (gcloud)
- `filestorage/adapters/azure_storage_adapter.py` (azure)
- `taskqueue/adapters/saq_adapter.py` (saq)
- `feature_flags/adapters/file_feature_flag_adapter.py` (yaml)
- `update/adapters/http_update_adapter.py` (packaging)
- `permission/adapters/casbin_permission_adapter.py` (casbin — but also eagerly imported in `permission/__init__.py`)

---

### Approaches

#### 1. Option A: try/except in each `__init__.py` — Minimal, follows existing pattern

Move adapter imports AFTER models/ports in `database/__init__.py` and `filestorage/__init__.py`, wrapping them in `try/except ImportError: AdapterName = None`.

- **Pros**:
  - Matches the EXACT same pattern already established in root `__init__.py` (lines 170-313)
  - Zero new concepts or abstractions
  - Only affects 2 files (database/__init__.py and filestorage/__init__.py)
  - Fixes the crash AND restores graceful degradation
  - Understood by every Python developer
  - No changes to adapter code

- **Cons**:
  - Duplicates the try/except pattern already in root `__init__.py` (both levels would have it)
  - Doesn't solve the root cause (sub-packages shouldn't eagerly import optional adapters at all)
  - Fragile — future contributors might add new eager imports without try/except

- **Effort**: Low (2 files, ~10 lines changed each)

#### 2. Option B: `__getattr__` lazy loading at module level

Use Python 3.7+ `__getattr__` at module level (PEP 562) to defer adapter resolution until the symbol is actually accessed.

```python
# _module_lazy.py
_imports = {
    "SQLAlchemyAdapter": ("core_infrastructure.database.adapters.sqlalchemy_adapter", "SQLAlchemyAdapter"),
    "MemoryDatabaseAdapter": ("core_infrastructure.database.adapters.memory_database_adapter", "MemoryDatabaseAdapter"),
}

def __getattr__(name):
    if name in _imports:
        mod_path, cls_name = _imports[name]
        import importlib
        mod = importlib.import_module(mod_path)
        cls = getattr(mod, cls_name)
        globals()[name] = cls
        return cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__():
    return list(_imports.keys())
```

- **Pros**:
  - Elegant zero-cost-for-what-you-don't-use pattern
  - Eliminates the import chain problem entirely at the mechanism level
  - Single pattern for all sub-packages
  - `__dir__()` preserves IDE autocomplete

- **Cons**:
  - Unfamiliar to most Python developers — cognitive overhead
  - `mypy --strict` won't understand `__getattr__` exports without `__all__` + type stubs
  - Breaks `from module import Symbol` at the sub-package level (PEP 562 only defers `module.Symbol` access)
  - If a consumer does `from core_infrastructure.database import SQLAlchemyAdapter`, Python still resolves the import eagerly — `__getattr__` is only for `getattr(module, "name")` or `module.name`, NOT for `from X import Y`
  - Needs `__dir__` for `dir()` and potentially `__all__` for mypy

- **Effort**: Medium (needs careful testing with mypy, IDE, and all import styles)

#### 3. Option C: DependencyManager (M13) for lazy resolution

Use the existing `ImportlibDependencyAdapter` (M13) to register and resolve adapter classes lazily. Each `__init__.py` would pre-register adapter entries and use `dependency_manager.resolve_class("module.path", "ClassName")` for lazy imports.

- **Pros**:
  - Uses existing infrastructure — M13 DependencyManager already exists
  - Security via allowlist validation
  - Caching via internal lru_cache
  - Can report required packages via `get_required_packages()`

- **Cons**:
  - **Massive overkill** — DependencyManager is designed for plugin/class resolution where module_paths come from external configuration and need allowlist security. Here, we're importing well-known internal adapters at fixed paths.
  - Creates a circular dependency risk: DependencyManager itself needs ConfigManager (which is fine), but now every sub-package needs a configured DependencyManager instance just to import its own adapters
  - Module-level code can't depend on a runtime instance — requires a global singleton or `__init__` trickery
  - `resolve_class()` requires a pre-configured adapter instance, which doesn't exist at import time
  - Adds complexity for what is fundamentally a simple `try/except ImportError` problem
  - If DependencyManager is not configured/available, imports fail entirely

- **Effort**: High (new pattern, wiring across all sub-packages, testing, circular dependency considerations)

---

### Recommendation

**Option A: try/except in each `__init__.py`** is the right choice. Here's why:

1. **Problem size**: Only 2 managers (`database/`, `filestorage/`) have the crash-causing pattern. Fixing 2 files is trivial.

2. **Pattern consistency**: The root `__init__.py` already uses this exact pattern for ~25 adapter imports (lines 170-313). Extending it to sub-packages doesn't introduce anything new.

3. **Minimal change, maximal fix**: Adding `try/except ImportError` blocks in `database/__init__.py` and `filestorage/__init__.py` completely eliminates the crash with ~10 lines of change.

4. **No new abstractions**: Options B and C introduce mechanisms that solve a problem that doesn't exist at scale. The sub-packages that DON'T crash don't need fixing. Creating a library-wide pattern for 2 offenders is overengineering.

5. **Testability**: `None`-assignment is already tested in root `__init__.py` — same pattern, already proven.

6. **Migration path**: If more optional-dependent adapters are added to these sub-packages in the future, the try/except pattern is already in place.

**Specific fix for `database/__init__.py`**:
```python
# Move adapter imports AFTER models/ports (lines 21-22 before 19-20)
from core_infrastructure.database.models import DatabaseConfig, PaginatedResult, RepositoryQuery
from core_infrastructure.database.ports import DatabaseManager, GenericRepository, TransactionScope

# Optional adapters — graceful degradation
try:
    from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter
except ImportError:
    SQLAlchemyAdapter = None  # type: ignore[assignment,misc]

from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
```

**Specific fix for `filestorage/__init__.py`**:
```python
# Move adapter imports AFTER models/ports
from core_infrastructure.filestorage.models import FileRef, StorageConfig, UploadResult
from core_infrastructure.filestorage.ports import FileStorageManager

# Optional adapters — graceful degradation
try:
    from core_infrastructure.filestorage.adapters.local_storage_adapter import LocalStorageAdapter
except ImportError:
    LocalStorageAdapter = None  # type: ignore[assignment,misc]

from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
```

---

### Risks

- **Risk 1: `aiofiles` is not listed as an optional dependency in `pyproject.toml`**. Currently, `aiofiles` only appears as `types-aiofiles` in `[dev]`. If `filestorage/__init__.py` wraps the import in try/except, `LocalStorageAdapter` will always be `None` unless the user manually installs `aiofiles`. Consider adding `aiofiles` as either a core dep or a new `[local-storage]` optional extra so the graceful degradation has a path to resolution.

- **Risk 2: Incomplete fix if new adapters are added**. If a new manager sub-package is created that eagerly imports an optional-dependent adapter, this bug will recur. Mitigation: add a test that verifies `import core_infrastructure` succeeds with only core deps installed.

- **Risk 3: `__all__` must be updated** to include `SQLAlchemyAdapter` and `LocalStorageAdapter` even when they might be `None`, matching the pattern used in the root `__init__.py`.

---

### Ready for Proposal

Yes
