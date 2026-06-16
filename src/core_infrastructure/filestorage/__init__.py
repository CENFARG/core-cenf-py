"""CENF FileStorageManager — blob storage with local and memory adapters.

Provides a Protocol-based interface for blob/file storage operations:
upload, download, delete, exists, generate pre-signed URLs, and list objects.
LocalStorageAdapter uses aiofiles for async filesystem I/O; MemoryStorageAdapter
provides an in-memory dict for testing.

Security: Pre-signed URLs MUST expire. NEVER log file contents or URLs
    at INFO or above.
Observability: All operations emit byte counters and duration histograms
    via ObservabilityManager.
@ai-directive: Use LocalStorageAdapter for dev, MemoryStorageAdapter for
    testing, and S3 adapter (future) for production.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.filestorage.adapters.local_storage_adapter import LocalStorageAdapter
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
from core_infrastructure.filestorage.models import FileRef, StorageConfig, UploadResult
from core_infrastructure.filestorage.ports import FileStorageManager

__all__ = [
    "FileRef",
    "FileStorageManager",
    "LocalStorageAdapter",
    "MemoryStorageAdapter",
    "StorageConfig",
    "UploadResult",
]
