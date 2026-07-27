"""Unit tests for FileReaderPort Protocol.

Tests cover:
- FileReaderPort Protocol contract (read_file, file_exists, list_files, read_lines)
- Protocol is runtime-checkable
- Class with all methods satisfies the protocol
- Class missing a method does not satisfy the protocol

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from pathlib import Path

from core_infrastructure.file_reader.ports import FileReaderPort


class TestFileReaderPortProtocol:
    """Verify FileReaderPort Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """FileReaderPort Protocol is decorated with @runtime_checkable."""
        assert hasattr(FileReaderPort, "_is_runtime_protocol") or hasattr(
            FileReaderPort, "__protocol_attrs__"
        )

    def test_has_read_file_method(self) -> None:
        """Protocol requires read_file(path) -> str."""
        assert hasattr(FileReaderPort, "read_file")

    def test_has_file_exists_method(self) -> None:
        """Protocol requires file_exists(path) -> bool."""
        assert hasattr(FileReaderPort, "file_exists")

    def test_has_list_files_method(self) -> None:
        """Protocol requires list_files(pattern) -> list[Path]."""
        assert hasattr(FileReaderPort, "list_files")

    def test_has_read_lines_method(self) -> None:
        """Protocol requires read_lines(path) -> list[str]."""
        assert hasattr(FileReaderPort, "read_lines")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all FileReaderPort methods satisfies the protocol."""

        class ValidReader:
            async def read_file(self, path: str | Path) -> str: ...
            async def file_exists(self, path: str | Path) -> bool: ...
            async def list_files(self, pattern: str) -> list[Path]: ...
            async def read_lines(self, path: str | Path) -> list[str]: ...

        assert isinstance(ValidReader(), FileReaderPort)

    def test_class_missing_read_file_fails_protocol(self) -> None:
        """A class without read_file() does NOT satisfy FileReaderPort."""

        class Incomplete:
            async def file_exists(self, path: str | Path) -> bool: ...

        assert not isinstance(Incomplete(), FileReaderPort)

    def test_class_missing_list_files_fails_protocol(self) -> None:
        """A class without list_files() does NOT satisfy FileReaderPort."""

        class Incomplete:
            async def read_file(self, path: str | Path) -> str: ...
            async def file_exists(self, path: str | Path) -> bool: ...
            async def read_lines(self, path: str | Path) -> list[str]: ...

        assert not isinstance(Incomplete(), FileReaderPort)
