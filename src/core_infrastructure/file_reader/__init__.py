"""FileReaderPort — local filesystem read operations for agents and workflows.

Separate from FileStorageManager (blob storage). Designed for use cases
like reading config files, prompt templates, or logging output — anything
an agent would do with ``cat`` or ``read``.

Docker note: LocalFileReaderAdapter works inside Docker containers by
setting ``root_dir`` to the mounted volume path (e.g., ``/app/data``).
No separate Docker adapter is needed.

@ai-directive: All paths are resolved relative to the adapter's root directory.
    Never pass absolute user-supplied paths without validation.
"""

from core_infrastructure.file_reader.ports import FileReaderPort

# Optional adapter — gracefully degrade if aiofiles is missing
try:
    from core_infrastructure.file_reader.adapters.local_file_reader_adapter import (
        LocalFileReaderAdapter,
    )
except ImportError:
    LocalFileReaderAdapter = None  # type: ignore[assignment,misc]

__all__ = [
    "FileReaderPort",
    "LocalFileReaderAdapter",
]
