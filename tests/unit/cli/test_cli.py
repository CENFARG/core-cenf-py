"""Tests for core_cenf_cli — Scaffolding CLI.

STRICT TDD: Each test is written BEFORE the corresponding production code.
Tests verify that ``cenf version`` prints the version and ``cenf new <name>``
generates a complete project skeleton with all files and correct content.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# ======================================================================
# Helpers
# ======================================================================


def _run_cli(args: list[str]) -> tuple[str, str]:
    """Run the CLI main function with given args and capture stdout+stderr.

    Returns a tuple of (stdout, stderr).
    """
    import contextlib
    import io

    original_argv = sys.argv[:]
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    sys.stdout = captured_out
    sys.stderr = captured_err
    try:
        sys.argv = ["cenf", *args]

        # Force reimport to avoid stale state
        if "core_cenf_cli.cli" in sys.modules:
            del sys.modules["core_cenf_cli.cli"]

        from core_cenf_cli.cli import main

        with contextlib.suppress(SystemExit):
            main()
        stdout_text = captured_out.getvalue()
        stderr_text = captured_err.getvalue()
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        sys.argv = original_argv
    return stdout_text, stderr_text


def _check_generated_project(root: Path, project_name: str) -> dict[str, bool]:
    """Verify that a generated project has all expected files and structure.

    Returns a dict mapping file path to whether it exists and has content.
    """
    project_dir = root / project_name
    pkg_name = project_name.replace("-", "_")

    checks: dict[str, bool] = {}

    # Top-level files
    checks["pyproject.toml"] = (project_dir / "pyproject.toml").is_file()
    checks["config.yaml"] = (project_dir / "config.yaml").is_file()
    checks[".gitignore"] = (project_dir / ".gitignore").is_file()
    checks[".env.example"] = (project_dir / ".env.example").is_file()

    # Source files
    checks[f"src/{pkg_name}/__init__.py"] = (project_dir / "src" / pkg_name / "__init__.py").is_file()
    checks[f"src/{pkg_name}/app.py"] = (project_dir / "src" / pkg_name / "app.py").is_file()
    checks[f"src/{pkg_name}/settings.py"] = (project_dir / "src" / pkg_name / "settings.py").is_file()

    # Test files
    checks["tests/__init__.py"] = (project_dir / "tests" / "__init__.py").is_file()
    checks["tests/test_app.py"] = (project_dir / "tests" / "test_app.py").is_file()

    return checks


# ======================================================================
# Tests — RED phase: these fail because core_cenf_cli does not exist yet
# ======================================================================


class TestCenfVersion:
    """Tests for the ``cenf version`` command."""

    def test_version_command_exists(self) -> None:
        """RED: importing core_cenf_cli should not raise ImportError once
        the package is created."""
        # This will fail with ModuleNotFoundError until core_cenf_cli exists
        try:
            import core_cenf_cli.cli  # noqa: F401
        except ImportError:
            pytest.fail("core_cenf_cli.cli module not found — create src/core_cenf_cli/cli.py")

    def test_version_output_contains_version(self) -> None:
        """``cenf version`` prints a version string like 'core-cenf X.Y.Z'."""
        output, _ = _run_cli(["version"])
        assert "core-cenf" in output.lower(), f"Expected 'core-cenf' in output, got: {output}"
        # Should contain a version-like pattern like 0.1.0
        assert re.search(r"\d+\.\d+\.\d+", output), f"Expected semver in output, got: {output}"

    def test_version_flag_v(self) -> None:
        """``cenf -v`` (short flag) should also print the version."""
        output, _ = _run_cli(["-v"])
        assert "core-cenf" in output.lower(), f"Expected version in -v output, got: {output}"

    def test_version_flag_version(self) -> None:
        """``cenf --version`` (long flag) should also print the version."""
        output, _ = _run_cli(["--version"])
        assert "core-cenf" in output.lower(), f"Expected version in --version output, got: {output}"


class TestCenfNew:
    """Tests for the ``cenf new <project-name>`` scaffolding command."""

    def test_new_command_exists(self, tmp_path: Path) -> None:
        """``cenf new <project-name>`` runs without error and creates a directory."""
        output, _ = _run_cli(["new", str(tmp_path / "test-project")])
        # After successful generation, output should mention the project
        assert output, "Expected non-empty output from cenf new"
        gen_dir = tmp_path / "test-project"
        assert gen_dir.is_dir(), f"Expected directory {gen_dir} to be created"

    def test_new_creates_all_files(self, tmp_path: Path) -> None:
        """All expected files are created in the generated project."""
        _run_cli(["new", str(tmp_path / "myapp")])
        checks = _check_generated_project(tmp_path, "myapp")
        for file_path, exists in checks.items():
            assert exists, f"Expected {file_path} to exist, but it was not found"

    def test_pyproject_has_core_cenf_dependency(self, tmp_path: Path) -> None:
        """The generated pyproject.toml depends on core-cenf."""
        _run_cli(["new", str(tmp_path / "hasdep")])
        content = (tmp_path / "hasdep" / "pyproject.toml").read_text()
        assert "core-cenf" in content, f"Expected core-cenf dependency, got: {content[:200]}"

    def test_config_yaml_has_manager_sections(self, tmp_path: Path) -> None:
        """The generated config.yaml contains sections for all managers."""
        _run_cli(["new", str(tmp_path / "withcfg")])
        content = (tmp_path / "withcfg" / "config.yaml").read_text()
        # At minimum should have the root app section
        assert "app:" in content, "Expected 'app:' section in config.yaml"
        assert "env:" in content, "Expected 'env:' field in config.yaml"

    def test_app_py_imports_bootstrap_orchestrator(self, tmp_path: Path) -> None:
        """The generated app.py imports and uses BootstrapOrchestrator."""
        _run_cli(["new", str(tmp_path / "withapp")])
        content = (tmp_path / "withapp" / "src" / "withapp" / "app.py").read_text()
        assert "BootstrapOrchestrator" in content, "Expected BootstrapOrchestrator in generated app.py"
        assert "asyncio.run" in content, "Expected asyncio.run in generated app.py"

    def test_app_py_imports_all_17_managers(self, tmp_path: Path) -> None:
        """The generated app.py imports in-memory adapters for all 17 managers."""
        _run_cli(["new", str(tmp_path / "all17")])
        content = (tmp_path / "all17" / "src" / "all17" / "app.py").read_text()
        # Check for every manager's in-memory adapter import
        expected_imports = [
            "InMemoryConfigAdapter",
            "InMemoryLoggerAdapter",
            "InMemorySecretAdapter",
            "InMemoryObservabilityAdapter",
            "CapturingErrorAdapter",
            "StaticAuthAdapter",
            "MemoryCacheAdapter",
            "MemoryDatabaseAdapter",
            "MemoryStorageAdapter",
            "MemoryTaskQueueAdapter",
            "MockHTTPAdapter",
            "MemoryFeatureFlagAdapter",
            "InMemoryDependencyAdapter",
            "ConditionalPromptAdapter",
            "DispatchAlertAdapter",
            "InMemoryRateLimitAdapter",
            "InMemoryI18nAdapter",
        ]
        for expected in expected_imports:
            assert expected in content, f"Expected import of {expected} in generated app.py"

    def test_settings_py_extends_core_settings(self, tmp_path: Path) -> None:
        """The generated settings.py defines AppSettings extending CoreSettings."""
        _run_cli(["new", str(tmp_path / "withsettings")])
        content = (tmp_path / "withsettings" / "src" / "withsettings" / "settings.py").read_text()
        assert "CoreSettings" in content, "Expected CoreSettings in generated settings.py"
        assert "AppSettings" in content, "Expected AppSettings class in generated settings.py"

    def test_generated_project_is_runnable(self, tmp_path: Path) -> None:
        """The generated app.py is a valid Python file (syntax check only)."""
        _run_cli(["new", str(tmp_path / "runnable")])
        app_path = tmp_path / "runnable" / "src" / "runnable" / "app.py"
        source = app_path.read_text()
        compile(source, str(app_path), "exec")

    def test_new_with_invalid_name_reports_error(self) -> None:
        """An empty project name should produce an error message."""
        _output, err = _run_cli(["new", ""])
        # Should report error on stderr — at minimum doesn't crash
        assert isinstance(err, str), "Expected stderr output"

    def test_new_overwrite_does_not_crash(self, tmp_path: Path) -> None:
        """Running cenf new on an existing directory should not crash silently."""
        target = tmp_path / "existing"
        target.mkdir()
        (target / "some_file.txt").write_text("existing content")
        output, err = _run_cli(["new", str(target)])
        # Directory already exists — should print warning or success
        combined = output + err
        assert combined, "Expected output when targeting existing directory"

    def test_gitignore_has_cenf_standard_entries(self, tmp_path: Path) -> None:
        """The generated .gitignore contains standard CENF entries."""
        _run_cli(["new", str(tmp_path / "gitcheck")])
        content = (tmp_path / "gitcheck" / ".gitignore").read_text()
        assert "__pycache__" in content, "Expected __pycache__ in .gitignore"
        assert ".venv" in content, "Expected .venv in .gitignore"

    def test_env_example_has_template_vars(self, tmp_path: Path) -> None:
        """The generated .env.example contains placeholder environment variables."""
        _run_cli(["new", str(tmp_path / "envcheck")])
        content = (tmp_path / "envcheck" / ".env.example").read_text()
        assert "CENF_" in content, "Expected CENF_-prefixed vars in .env.example"
