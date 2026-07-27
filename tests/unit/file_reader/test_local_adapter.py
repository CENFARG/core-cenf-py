"""Unit tests for LocalFileReaderAdapter — aiofiles-based FileReaderPort.

Tests cover:
- Protocol compliance (satisfies FileReaderPort)
- read_file returns file contents
- read_file raises FileNotFoundError for missing files
- read_file raises ValueError for path traversal
- file_exists returns True/False
- list_files with glob pattern
- list_files returns empty list for no match
- read_lines strips trailing newlines

Security: Tests use tmp_path — no real filesystem pollution.
Observability: Tests verify aiofiles async I/O works correctly.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core_infrastructure.file_reader.adapters.local_file_reader_adapter import (
    LocalFileReaderAdapter,
)
from core_infrastructure.file_reader.ports import FileReaderPort


@pytest.fixture
def reader(tmp_path: Path) -> LocalFileReaderAdapter:
    """Create a LocalFileReaderAdapter rooted at a temp directory."""
    return LocalFileReaderAdapter(root_dir=tmp_path)


class TestLocalFileReaderAdapterProtocol:
    """Verify LocalFileReaderAdapter satisfies FileReaderPort Protocol."""

    def test_satisfies_file_reader_port_protocol(self, reader: LocalFileReaderAdapter) -> None:
        """LocalFileReaderAdapter passes isinstance check against FileReaderPort."""
        assert isinstance(reader, FileReaderPort)


class TestLocalFileReaderAdapterReadFile:
    """Verify read_file behavior."""

    @pytest.mark.asyncio
    async def test_read_file_returns_contents(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """read_file() returns the full file contents."""
        file_path = tmp_path / "hello.txt"
        file_path.write_text("Hello, World!", encoding="utf-8")
        content = await reader.read_file("hello.txt")
        assert content == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_file_nonexistent_raises_filenotfound(self, reader: LocalFileReaderAdapter) -> None:
        """read_file() raises FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            await reader.read_file("missing.txt")

    @pytest.mark.asyncio
    async def test_read_file_traversal_raises_value_error(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """read_file() raises ValueError for path traversal attempts."""
        file_path = tmp_path.parent / "secret.txt"
        file_path.write_text("secret", encoding="utf-8")
        with pytest.raises(ValueError, match="Path traversal detected"):
            await reader.read_file(f"../{tmp_path.name}_/../secret.txt")

    @pytest.mark.asyncio
    async def test_read_file_traversal_escaping_root(self, reader: LocalFileReaderAdapter) -> None:
        """read_file() rejects clearly malicious traversal paths."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            await reader.read_file("../../etc/passwd")

    @pytest.mark.asyncio
    async def test_read_file_with_subdirectory(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """read_file() works with paths in subdirectories."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        file_path = subdir / "nested.txt"
        file_path.write_text("nested content", encoding="utf-8")
        content = await reader.read_file(Path("sub") / "nested.txt")
        assert content == "nested content"


class TestLocalFileReaderAdapterFileExists:
    """Verify file_exists behavior."""

    @pytest.mark.asyncio
    async def test_file_exists_returns_true(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """file_exists() returns True for existing files."""
        file_path = tmp_path / "exists.txt"
        file_path.write_text("data", encoding="utf-8")
        assert await reader.file_exists("exists.txt") is True

    @pytest.mark.asyncio
    async def test_file_exists_returns_false(self, reader: LocalFileReaderAdapter) -> None:
        """file_exists() returns False for missing files."""
        assert await reader.file_exists("nope.txt") is False

    @pytest.mark.asyncio
    async def test_file_exists_handles_traversal_gracefully(self, reader: LocalFileReaderAdapter) -> None:
        """file_exists() returns False for traversal paths instead of raising."""
        assert await reader.file_exists("../../etc/passwd") is False


class TestLocalFileReaderAdapterListFiles:
    """Verify list_files behavior."""

    @pytest.mark.asyncio
    async def test_list_files_matches_glob(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """list_files() returns paths matching the glob pattern."""
        (tmp_path / "foo.py").write_text("")
        (tmp_path / "bar.py").write_text("")
        (tmp_path / "readme.md").write_text("")

        results = await reader.list_files("*.py")
        assert len(results) == 2
        assert Path("foo.py") in results
        assert Path("bar.py") in results

    @pytest.mark.asyncio
    async def test_list_files_returns_relative_paths(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """list_files() returns paths relative to the root directory."""
        (tmp_path / "file.txt").write_text("")
        results = await reader.list_files("*")
        assert all(not p.is_absolute() for p in results)

    @pytest.mark.asyncio
    async def test_list_files_empty_for_no_match(self, reader: LocalFileReaderAdapter) -> None:
        """list_files() returns empty list when no files match."""
        results = await reader.list_files("*.xyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_list_files_excludes_directories(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """list_files() returns only files, not directories."""
        (tmp_path / "file.py").write_text("")
        (tmp_path / "subdir").mkdir()

        results = await reader.list_files("*")
        assert Path("file.py") in results
        assert Path("subdir") not in results


class TestLocalFileReaderAdapterReadLines:
    """Verify read_lines behavior."""

    @pytest.mark.asyncio
    async def test_read_lines_strips_trailing_newlines(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """read_lines() strips trailing newlines from each line."""
        file_path = tmp_path / "lines.txt"
        file_path.write_text("line1\nline2\nline3\n", encoding="utf-8")
        lines = await reader.read_lines("lines.txt")
        assert lines == ["line1", "line2", "line3"]

    @pytest.mark.asyncio
    async def test_read_lines_single_line(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """read_lines() works with a single line without trailing newline."""
        file_path = tmp_path / "single.txt"
        file_path.write_text("just one line", encoding="utf-8")
        lines = await reader.read_lines("single.txt")
        assert lines == ["just one line"]

    @pytest.mark.asyncio
    async def test_read_lines_nonexistent_raises_filenotfound(self, reader: LocalFileReaderAdapter) -> None:
        """read_lines() raises FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            await reader.read_lines("missing.txt")

    @pytest.mark.asyncio
    async def test_read_lines_empty_file(self, reader: LocalFileReaderAdapter, tmp_path: Path) -> None:
        """read_lines() returns empty list for an empty file."""
        file_path = tmp_path / "empty.txt"
        file_path.write_text("", encoding="utf-8")
        lines = await reader.read_lines("empty.txt")
        assert lines == []
