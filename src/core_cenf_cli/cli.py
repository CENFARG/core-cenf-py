"""CENF Scaffolding CLI — entry point for ``cenf`` command.

Commands:
    cenf new <project-name>    Generate a new CENF project skeleton
    cenf version               Print the core-cenf version

Uses argparse (stdlib only, zero extra deps) for argument parsing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

# Map of relative template path -> generated file name
_TEMPLATE_FILES: dict[str, str] = {
    "pyproject.toml.tmpl": "pyproject.toml",
    "config.yaml.tmpl": "config.yaml",
    ".gitignore.tmpl": ".gitignore",
    ".env.example.tmpl": ".env.example",
    "app.py.tmpl": "app.py",
    "settings.py.tmpl": "settings.py",
    "test_app.py.tmpl": "test_app.py",
}


def _get_version() -> str:
    """Return the core-cenf version string."""
    try:
        from core_infrastructure import __version__
    except ImportError:
        __version__ = "0.1.0"
    return f"core-cenf {__version__}"


def _slugify(name: str) -> str:
    """Convert a project name to a valid Python package name."""
    return name.lower().replace("-", "_").replace(" ", "_")


def _render_template(template_path: Path, variables: dict[str, str]) -> str:
    """Render a template file using simple string substitution.

    Uses Python's str.replace() for ``{{ variable }}`` placeholders.
    No extra dependencies required.
    """
    content = template_path.read_text(encoding="utf-8")
    return _render_template_str(content, variables)


def _render_template_str(content: str, variables: dict[str, str]) -> str:
    """Render a template string using simple string substitution."""
    for key, value in variables.items():
        placeholder = "{{ " + key + " }}"
        content = content.replace(placeholder, value)
    return content


def cmd_new(project_path: str) -> int:
    """Generate a new CENF project skeleton.

    Args:
        project_path: Path or name of the project to create.
            Can be a simple name or a full path.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    if not project_path or not project_path.strip():
        print("Error: Project name must not be empty.", file=sys.stderr)
        return 1

    project_dir = Path(project_path).resolve()
    project_name_clean = project_dir.name
    pkg_name = _slugify(project_name_clean)

    # Validate the project name (basename only, not the full path)
    if not project_name_clean or not project_name_clean.replace("-", "").replace("_", "").isalnum():
        print(
            f"Error: Invalid project name '{project_name_clean}'. Use letters, numbers, hyphens, and underscores.",
            file=sys.stderr,
        )
        return 1

    if project_dir.exists():
        print(f"Warning: Directory '{project_dir}' already exists. Files may be overwritten.", file=sys.stderr)

    variables = {
        "project_name": project_name_clean,
        "package_name": pkg_name,
    }

    try:
        # Create directory structure
        (project_dir / "src" / pkg_name).mkdir(parents=True, exist_ok=True)
        (project_dir / "tests").mkdir(parents=True, exist_ok=True)

        # Generate templates
        for tmpl_name, out_name in _TEMPLATE_FILES.items():
            tmpl_path = _TEMPLATES_DIR / tmpl_name
            if not tmpl_path.is_file():
                print(f"Error: Template not found: {tmpl_name}", file=sys.stderr)
                return 1

            rendered = _render_template(tmpl_path, variables)

            # Determine output path
            if out_name in ("app.py", "settings.py"):
                out_path = project_dir / "src" / pkg_name / out_name
            elif out_name == "test_app.py":
                out_path = project_dir / "tests" / out_name
            else:
                out_path = project_dir / out_name

            out_path.write_text(rendered, encoding="utf-8")

        # Generate __init__.py files (package markers)
        init_content = '"""{{ package_name }} — CENF application package."""\n'
        init_rendered = _render_template_str(init_content, variables)
        (project_dir / "src" / pkg_name / "__init__.py").write_text(init_rendered, encoding="utf-8")
        (project_dir / "tests" / "__init__.py").write_text("", encoding="utf-8")

        print(f"Project '{project_name_clean}' created successfully at {project_dir}")
        print(f"  Package: src/{pkg_name}/")
        print(f"  Run: cd {project_name_clean} && python -m {pkg_name}.app")
        return 0

    except OSError as e:
        print(f"Error: Failed to create project: {e}", file=sys.stderr)
        return 1


def cmd_version() -> int:
    """Print the core-cenf version and exit."""
    print(_get_version())
    return 0


def main() -> None:
    """Entry point for the ``cenf`` CLI."""
    parser = argparse.ArgumentParser(
        prog="cenf",
        description="CENF Scaffolding CLI — generate new CENF projects",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # cenf new <project-name>
    new_parser = subparsers.add_parser("new", help="Create a new CENF project")
    new_parser.add_argument("project_name", help="Name of the project to create")

    # cenf version
    subparsers.add_parser("version", help="Show core-cenf version")

    # cenf -v / --version (top-level flag)
    parser.add_argument("-v", "--version", action="store_true", help="Show core-cenf version")

    args = parser.parse_args()

    if args.version:
        sys.exit(cmd_version())

    if args.command == "version":
        sys.exit(cmd_version())

    if args.command == "new":
        sys.exit(cmd_new(args.project_name))

    # No command given — print help
    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
