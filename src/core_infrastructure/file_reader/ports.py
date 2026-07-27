"""FileReaderPort — local filesystem read contract.

Separate from M09 FileStorageManager (blob storage) — this port is for
reading local files as an agent would with `cat` or `read`. Used by workflow
engines, prompt loaders, and any component that needs filesystem access.

@ai-directive: All paths are resolved relative to the adapter's root directory.
    Never pass absolute user-supplied paths without validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileReaderPort(Protocol):
    """Local filesystem read operations for workflow engines and agents."""

    async def read_file(self, path: str | Path) -> str:
        """Read entire file contents as a UTF-8 string.

        Args:
            path: Relative path from the adapter's root directory.

        Returns:
            File contents as a string.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        ...

    async def file_exists(self, path: str | Path) -> bool:
        """Check if a file exists at the given path.

        Args:
            path: Relative path from the adapter's root directory.

        Returns:
            True if the file exists and is a regular file.
        """
        ...

    async def list_files(self, pattern: str) -> list[Path]:
        """List files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., ``*.py``, ``**/*.md``, ``src/**/*.ts``).

        Returns:
            List of matching file paths (relative to adapter root).
        """
        ...

    async def read_lines(self, path: str | Path) -> list[str]:
        """Read a file line by line, stripping trailing newlines.

        Args:
            path: Relative path from the adapter's root directory.

        Returns:
            List of lines (without trailing newline characters).

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        ...
