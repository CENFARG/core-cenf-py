"""FileStorageManager Protocol — the contract every storage adapter must satisfy.

Defines the blob storage interface consumed by all infrastructure managers
that need file storage (upload, download, delete, list, generate pre-signed
URLs). Adapters implement local filesystem storage (dev/testing) or S3
(production).

Security: Pre-signed URLs MUST expire after the specified duration.
    Upload/download operations log at DEBUG level only — NEVER log
    file contents or pre-signed URLs at INFO or above.
Observability: Every operation emits byte counters and operation duration
    histograms via ObservabilityManager.
@ai-directive: All methods are async because they involve file I/O or
    network requests. MemoryStorageAdapter wraps sync dict operations
    in coroutines for testing.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core_infrastructure.filestorage.models import FileRef, UploadResult


@runtime_checkable
class FileStorageManager(Protocol):
    """Blob storage contract for all infrastructure managers.

    All managers that need file/blob storage consume this interface.
    Concrete adapters provide local filesystem storage (dev/testing)
    or S3-compatible object storage (production).

    Rules:
        - upload() overwrites existing objects with the same bucket+key.
        - download() raises ValidationError if the object does not exist.
        - delete() is idempotent — deleting a non-existent object succeeds silently.
        - exists() returns True only if the object exists and is readable.
        - generate_presigned_url() returns a time-limited URL for external access.
        - list_objects() returns an empty list when no objects match the prefix.
        - Bucket names must be alphanumeric + hyphens, max 256 chars.

    Security: Pre-signed URLs MUST have configurable expiry and MUST NOT
        be logged at INFO or above. File contents MUST NOT be logged.

    @ai-directive: When implementing a new adapter, ensure upload()
        accepts bytes (not str) for data to avoid encoding ambiguity.
    """

    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> UploadResult:
        """Upload an object to the specified bucket.

        Args:
            bucket: The bucket name (logical container).
            key: The object key (path within the bucket).
            data: The raw bytes to store.
            content_type: MIME type of the object.

        Returns:
            UploadResult: Metadata about the uploaded object (key, etag, url).

        Raises:
            ValidationError: If bucket or key is invalid.
            PermanentError: If the write fails (disk full, permission denied).
        """
        ...

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object's raw bytes.

        Args:
            bucket: The bucket name.
            key: The object key.

        Returns:
            bytes: The raw object data.

        Raises:
            ValidationError: If the object does not exist.
            PermanentError: If the read fails.
        """
        ...

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object from storage.

        Idempotent — deleting a non-existent object succeeds silently.

        Args:
            bucket: The bucket name.
            key: The object key.
        """
        ...

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists in storage.

        Args:
            bucket: The bucket name.
            key: The object key.

        Returns:
            bool: ``True`` if the object exists and is readable.
        """
        ...

    async def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expiry: int = 3600,
    ) -> str:
        """Generate a time-limited URL for external access.

        For local storage, this returns a ``file://`` URL. For S3, this
        generates an actual pre-signed URL.

        Args:
            bucket: The bucket name.
            key: The object key.
            expiry: URL validity duration in seconds (default 3600 = 1 hour).

        Returns:
            str: A time-limited access URL.

        Raises:
            ValidationError: If the object does not exist.

        Security: The returned URL grants access to the object — never
            log it at INFO or above.
        """
        ...

    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
    ) -> list[FileRef]:
        """List objects in a bucket with an optional prefix filter.

        Args:
            bucket: The bucket name.
            prefix: Optional prefix to filter objects by key.

        Returns:
            list[FileRef]: List of object references (empty if none match).
        """
        ...
