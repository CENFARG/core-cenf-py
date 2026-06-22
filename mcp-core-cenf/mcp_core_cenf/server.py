"""MCP server — FastMCP application with FTS5 search for core-cenf.

Indexes the api-catalog.json on startup and exposes semantic search
tools that AI agents can call directly.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("core-cenf-search")

_CATALOG: list[dict[str, Any]] = []


def _build_index(catalog_path: str | Path) -> None:
    """Load the api-catalog.json and build an FTS5 index in memory."""
    global _CATALOG
    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)
    _CATALOG = data.get("managers", [])

    db = sqlite3.connect(":memory:")
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS managers_fts USING fts5(manager_name, methods, directives)")
    for mgr in _CATALOG:
        methods_text = " ".join(
            f"{m['name']} {m.get('returns', {}).get('type', '')}"
            for m in mgr.get("methods", [])
        )
        directives_text = " ".join(mgr.get("directives", []))
        db.execute(
            "INSERT INTO managers_fts(manager_name, methods, directives) VALUES(?, ?, ?)",
            (mgr["name"], methods_text, directives_text),
        )
    db.commit()
    db.close()


@mcp.tool()
def search_core_cenf(query: str) -> str:
    """Search across all 20 core-cenf managers by method name or @ai-directive.

    Args:
        query: Natural language query. Examples: "rate limiting", "JWT validation", "cache".

    Returns:
        Formatted list of matching managers with relevant methods and directives.
    """
    db = sqlite3.connect(":memory:")
    _build_index("agents/api-catalog.json")  # re-index for fresh connection
    try:
        rows = db.execute(
            "SELECT manager_name, methods, directives FROM managers_fts WHERE managers_fts MATCH ? ORDER BY rank LIMIT 5",
            (query,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = db.execute(
            "SELECT manager_name, methods, directives FROM managers_fts WHERE manager_name LIKE ? LIMIT 5",
            (f"%{query}%",),
        ).fetchall()
    finally:
        db.close()

    if not rows:
        return f"No managers found matching '{query}'. Try a different search term."

    lines = [f"## Search results for: {query}\n"]
    for name, methods, directives in rows:
        lines.append(f"### {name}")
        lines.append(f"**Methods**: {methods[:200]}...")
        if directives:
            lines.append(f"**@ai-directive**: {directives[:200]}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def get_manager(name: str) -> str:
    """Get detailed information about a specific core-cenf manager.

    Args:
        name: Manager name (e.g., "ConfigManager", "CacheManager").

    Returns:
        Full manager details: methods, dependencies, directives, adapter imports.
    """
    _build_index("agents/api-catalog.json")
    for mgr in _CATALOG:
        if mgr["name"].lower() == name.lower():
            methods = "\n".join(
                f"- `{m['name']}({', '.join(p['name'] + ': ' + p['type'] for p in m.get('params', []))}) -> {m.get('returns', {}).get('type', '')}`"
                for m in mgr.get("methods", [])
            )
            deps = ", ".join(mgr.get("dependencies", [])) or "None (root)"
            directives = "\n".join(f"- {d}" for d in mgr.get("directives", []))
            return f"""## {mgr['name']} ({mgr['id']})

**Dependencies**: {deps}

**Methods**:
{methods}

**@ai-directive**:
{directives}

**Package**: `{mgr['package']}`
"""
    return f"Manager '{name}' not found. Available: {', '.join(m['name'] for m in _CATALOG)}"


def main() -> None:
    """CLI entry point: build index and start MCP server."""
    parser = argparse.ArgumentParser(description="core-cenf MCP search server")
    parser.add_argument("--catalog", default="agents/api-catalog.json", help="Path to api-catalog.json")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog not found: {catalog_path}")

    _build_index(catalog_path)
    mcp.run()


if __name__ == "__main__":
    main()
