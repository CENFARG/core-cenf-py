"""LocalFileReaderAdapter — reads files from the local filesystem.

Uses Python's built-in pathlib for path resolution and aiofiles for
async file I/O. Safe against path traversal when root_dir is configured.

Usage:
    reader = LocalFileReaderAdapter(root_dir=Path("/app/data"))
    content = await reader.read_file("config.yaml")
"""

from __future__ import annotations

from pathlib import Path

import aiofiles


class LocalFileReaderAdapter:
    """Reads files from a root directory on the local filesystem.

    All paths are resolved relative to ``root_dir``. Path traversal
    attempts (e.g., ``../../etc/passwd``) are rejected.
    """

    def __init__(self, root_dir: Path | str | None = None) -> None:
        if root_dir is None:
            root_dir = Path.cwd()
        self._root = Path(root_dir).resolve()

    def _resolve(self, path: str | Path) -> Path:
        """Resolve a relative path and reject traversal attempts.

        Raises:
            ValueError: If the resolved path escapes root_dir.
        """
        resolved = (self._root / path).resolve()
        if not str(resolved).startswith(str(self._root)):
            raise ValueError(
                f"Path traversal detected: '{path}' resolves outside root_dir"
            )
        return resolved

    async def read_file(self, path: str | Path) -> str:
        resolved = self._resolve(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        async with aiofiles.open(resolved, encoding="utf-8") as f:
            return await f.read()

    async def file_exists(self, path: str | Path) -> bool:
        try:
            resolved = self._resolve(path)
            return resolved.is_file()
        except (ValueError, OSError):
            return False

    async def list_files(self, pattern: str) -> list[Path]:
        matches = list(self._root.glob(pattern))
        return [p.relative_to(self._root) for p in matches if p.is_file()]

    async def read_lines(self, path: str | Path) -> list[str]:
        resolved = self._resolve(path)
        if not resolved.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        async with aiofiles.open(resolved, encoding="utf-8") as f:
            return [line.rstrip("\n") for line in await f.readlines()]
