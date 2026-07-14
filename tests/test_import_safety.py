"""Test that core_infrastructure can be imported without optional dependencies.

Regression tests for the eager-import-fix:
- Core import MUST succeed even when sqlalchemy/aiofiles are absent
- SQLAlchemyAdapter MUST be None when sqlalchemy is absent
- LocalStorageAdapter MUST be None when aiofiles is absent
- MemoryDatabaseAdapter MUST NOT be None (core dep)
- MemoryStorageAdapter MUST NOT be None (core dep)

Author: CENF AI Team
Version: 0.1.2
"""

import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Subprocess-based tests: reliable isolation by masking deps at interpreter level
# ---------------------------------------------------------------------------

_SUBPROCESS_SCRIPT = """\
import sys
# Block optional deps BEFORE any core_infrastructure import
sys.modules["sqlalchemy"] = None
sys.modules["aiofiles"] = None

import core_infrastructure

errors = []

# Core import must succeed
if core_infrastructure is None:
    errors.append("core_infrastructure is None")

# SQLAlchemyAdapter must be None when sqlalchemy absent
if core_infrastructure.SQLAlchemyAdapter is not None:
    errors.append(f"SQLAlchemyAdapter should be None, got {core_infrastructure.SQLAlchemyAdapter}")

# LocalStorageAdapter must be None when aiofiles absent
if core_infrastructure.LocalStorageAdapter is not None:
    errors.append(f"LocalStorageAdapter should be None, got {core_infrastructure.LocalStorageAdapter}")

# MemoryDatabaseAdapter must NOT be None (core-only deps)
if core_infrastructure.MemoryDatabaseAdapter is None:
    errors.append("MemoryDatabaseAdapter should not be None")

# MemoryStorageAdapter must NOT be None (core-only deps)
if core_infrastructure.MemoryStorageAdapter is None:
    errors.append("MemoryStorageAdapter should not be None")

# Sub-package imports must also succeed
import core_infrastructure.database as db
if db.SQLAlchemyAdapter is not None:
    errors.append(f"db.SQLAlchemyAdapter should be None, got {db.SQLAlchemyAdapter}")
if db.MemoryDatabaseAdapter is None:
    errors.append("db.MemoryDatabaseAdapter should not be None")

import core_infrastructure.filestorage as fs
if fs.LocalStorageAdapter is not None:
    errors.append(f"fs.LocalStorageAdapter should be None, got {fs.LocalStorageAdapter}")
if fs.MemoryStorageAdapter is None:
    errors.append("fs.MemoryStorageAdapter should not be None")

if errors:
    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
else:
    print("OK")
    sys.exit(0)
"""


class TestImportSafetySubprocess:
    """Subprocess-based tests: reliable isolation via sys.modules shim."""

    def test_core_import_succeeds_without_optional_deps(self) -> None:
        """import core_infrastructure MUST succeed with sqlalchemy+aiofiles masked."""
        result = subprocess.run(
            [sys.executable, "-c", _SUBPROCESS_SCRIPT],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Import safety check failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "OK" in result.stdout

    def test_database_subpackage_safe_without_sqlalchemy(self) -> None:
        """database sub-package: SQLAlchemyAdapter is None, MemoryDatabaseAdapter resolves."""
        script = (
            "import sys; sys.modules['sqlalchemy'] = None; sys.modules['aiofiles'] = None; "
            "import core_infrastructure.database as db; "
            "assert db.SQLAlchemyAdapter is None, f'Expected None, got {db.SQLAlchemyAdapter}'; "
            "assert db.MemoryDatabaseAdapter is not None; "
            "print('OK')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_filestorage_subpackage_safe_without_aiofiles(self) -> None:
        """filestorage sub-package: LocalStorageAdapter is None, MemoryStorageAdapter resolves."""
        script = (
            "import sys; sys.modules['sqlalchemy'] = None; sys.modules['aiofiles'] = None; "
            "import core_infrastructure.filestorage as fs; "
            "assert fs.LocalStorageAdapter is None, f'Expected None, got {fs.LocalStorageAdapter}'; "
            "assert fs.MemoryStorageAdapter is not None; "
            "print('OK')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Failed: {result.stderr}"

    def test_regression_subprocess_sys_modules_shim(self) -> None:
        """Full regression: subprocess + sys.modules shim exits 0."""
        result = subprocess.run(
            [sys.executable, "-c", _SUBPROCESS_SCRIPT],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Regression test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# In-process tests: verify adapters resolve when deps ARE present
# ---------------------------------------------------------------------------


class TestOptionalAdaptersResolveWhenPresent:
    """When optional deps ARE installed, adapters resolve to real classes."""

    @pytest.mark.skipif(
        importlib.util.find_spec("sqlalchemy") is None,
        reason="sqlalchemy not installed",
    )
    def test_sqlalchemy_adapter_resolves_when_present(self) -> None:
        """SQLAlchemyAdapter is a class when sqlalchemy is installed."""
        from core_infrastructure.database import SQLAlchemyAdapter

        assert SQLAlchemyAdapter is not None
        assert isinstance(SQLAlchemyAdapter, type)

    @pytest.mark.skipif(
        importlib.util.find_spec("aiofiles") is None,
        reason="aiofiles not installed",
    )
    def test_local_storage_adapter_resolves_when_present(self) -> None:
        """LocalStorageAdapter is a class when aiofiles is installed."""
        from core_infrastructure.filestorage import LocalStorageAdapter

        assert LocalStorageAdapter is not None
        assert isinstance(LocalStorageAdapter, type)


# ---------------------------------------------------------------------------
# Metadata tests: verify package extras are declared correctly
# ---------------------------------------------------------------------------


class TestLocalStorageExtraMetadata:
    """Verify [local-storage] extra is declared in package metadata."""

    def test_local_storage_extra_declared(self) -> None:
        """pyproject.toml declares [local-storage] extra with aiofiles."""
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert "local-storage" in content, "Missing [local-storage] extra in pyproject.toml"
        assert "aiofiles" in content, "Missing aiofiles dependency in [local-storage] extra"

    def test_local_storage_in_all_aggregate(self) -> None:
        """[local-storage] is included in the 'all' aggregate extra."""
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert "local-storage" in content.split("all = [")[1].split("]")[0], (
            "local-storage not in 'all' aggregate extra"
        )
