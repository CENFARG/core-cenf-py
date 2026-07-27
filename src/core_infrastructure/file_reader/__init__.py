"""FileReaderPort — local filesystem read operations for agents and workflows.

Separate from FileStorageManager (blob storage). Designed for use cases
like reading config files, prompt templates, or logging output — anything
an agent would do with ``cat`` or ``read``.
"""

from core_infrastructure.file_reader.ports import FileReaderPort

__all__ = ["FileReaderPort"]
