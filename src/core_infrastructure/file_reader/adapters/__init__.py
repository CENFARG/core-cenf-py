"""File reader adapter implementations.

LocalFileReaderAdapter requires ``aiofiles`` (optional dependency).
If ``aiofiles`` is not installed, ``LocalFileReaderAdapter`` is set to ``None``.
"""

try:
    from core_infrastructure.file_reader.adapters.local_file_reader_adapter import (
        LocalFileReaderAdapter,
    )
except ImportError:
    LocalFileReaderAdapter = None  # type: ignore[assignment,misc]

__all__ = ["LocalFileReaderAdapter"]
