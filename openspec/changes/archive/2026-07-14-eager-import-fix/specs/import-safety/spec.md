# Delta for import-safety

## ADDED Requirements

### Requirement: Core Import SHALL Succeed Without Optional Dependencies

Importing the `core_infrastructure` package MUST NOT raise when optional
third-party dependencies (`sqlalchemy`, `aiofiles`) are absent. Every
sub-package `__init__.py` that re-exports an adapter with an optional
dependency SHALL wrap that import in a `try/except ImportError` block so the
import degrades gracefully to `None`, mirroring the pattern already proven in
the root `src/core_infrastructure/__init__.py` (lines 170-313).

#### Scenario: Import succeeds with only core dependencies

- GIVEN a Python environment where `core-cenf` is installed and `sqlalchemy`
  and `aiofiles` are NOT installed
- WHEN the statement `import core_infrastructure` executes
- THEN the import completes without raising `ModuleNotFoundError`
- AND `core_infrastructure` is a usable module object

#### Scenario: Sub-package import succeeds without optional deps

- GIVEN `sqlalchemy` is not installed
- WHEN the statement `import core_infrastructure.database` executes
- THEN the import completes without raising
- AND `core_infrastructure.database.MemoryDatabaseAdapter` resolves to the
  memory adapter class (its deps are core-only)
- AND `core_infrastructure.database.SQLAlchemyAdapter` resolves to `None`

#### Scenario: FileStorage sub-package import succeeds without aiofiles

- GIVEN `aiofiles` is not installed
- WHEN the statement `import core_infrastructure.filestorage` executes
- THEN the import completes without raising
- AND `core_infrastructure.filestorage.MemoryStorageAdapter` resolves to the
  memory adapter class
- AND `core_infrastructure.filestorage.LocalStorageAdapter` resolves to `None`

### Requirement: Optional Adapter Symbols SHALL Resolve When Deps Present

When an optional dependency IS installed, the corresponding adapter symbol
SHALL resolve to the real adapter class, preserving full functionality for
consumers who opt into the extra.

#### Scenario: SQLAlchemyAdapter resolves when sqlalchemy installed

- GIVEN `core-cenf[database]` (or `sqlalchemy`) is installed
- WHEN `import core_infrastructure.database` executes
- THEN `core_infrastructure.database.SQLAlchemyAdapter` is a class
- AND it is NOT `None`
- AND instantiating it does not raise `ImportError`

#### Scenario: LocalStorageAdapter resolves when aiofiles installed

- GIVEN `core-cenf[local-storage]` (or `aiofiles`) is installed
- WHEN `import core_infrastructure.filestorage` executes
- THEN `core_infrastructure.filestorage.LocalStorageAdapter` is a class
- AND it is NOT `None`

### Requirement: Optional Dependencies SHALL Be Installable Via Named Extras

`aiofiles` and `sqlalchemy` SHALL each be installable through a named optional
extra in `pyproject.toml`, so consumers who need a given adapter have a clean,
documented install path and consumers who do not are not forced to install it.

#### Scenario: local-storage extra installs aiofiles

- GIVEN a fresh environment without `aiofiles`
- WHEN `pip install "core-cenf[local-storage]"` runs
- THEN `aiofiles` is installed and importable
- AND `core_infrastructure.filestorage.LocalStorageAdapter` resolves to the
  real class (not `None`)

### Requirement: Import Safety Regression Coverage SHALL Exist

A regression test SHALL guard the graceful-degradation contract so that any
future adapter added eagerly (without a `try/except ImportError`) fails CI
before shipping.

#### Scenario: Regression test asserts core-only import path

- GIVEN a test environment with core deps only (no sqlalchemy, no aiofiles)
- WHEN `pytest tests/test_import_safety.py` runs
- THEN all assertions pass, specifically:
  - `import core_infrastructure` does not raise
  - `core_infrastructure.database.SQLAlchemyAdapter is None`
  - `core_infrastructure.filestorage.LocalStorageAdapter is None`
  - `core_infrastructure.database.MemoryDatabaseAdapter is not None`

## Deliverables

| File | Change | Purpose |
|------|--------|---------|
| `src/core_infrastructure/database/__init__.py` | Modified | Reorder imports (models/ports before adapters); wrap `SQLAlchemyAdapter` in `try/except ImportError` → `None` |
| `src/core_infrastructure/filestorage/__init__.py` | Modified | Reorder imports; wrap `LocalStorageAdapter` in `try/except ImportError` → `None` |
| `pyproject.toml` | Modified | Add `[local-storage]` optional extra with `aiofiles`; ensure `[database]` extra covers `sqlalchemy` |
| `tests/test_import_safety.py` | New | Regression test for the core-only import success contract |
