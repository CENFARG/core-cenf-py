"""mcp-core-cenf — MCP server for CENF Core Infrastructure semantic search.

Exposes tools that let AI coding agents search across the 20 core-cenf
managers: find methods by description, discover manager dependencies,
and retrieve @ai-directive annotations — all via FTS5 full-text search
over the pre-built api-catalog.json.

Usage:
    mcp-core-cenf --catalog ../agents/api-catalog.json
"""

__version__ = "0.1.0"
