"""MemoryStorageAdapter — in-memory dict-backed FileStorageManager for testing.

Provides a zero-dependency FileStorageManager implementation using nested
dicts (bucket → key → bytes) for in-memory object storage. Ideal for unit
tests that need fast, deterministic storage without filesystem I/O.

Security: All data is held in process memory — no persistence, no encryption.
    NEVER use this adapter for production data.
Observability: Operations are synchronous dict lookups wrapped in coroutines.
@ai-directive: This adapter exists solely for testing. Use
    LocalStorageAdapter for dev and S3 for production.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import uuid

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.filestorage.models import FileRef, StorageConfig, UploadResult


class MemoryStorageAdapter:
    """In-memory dict-backed FileStorageManager for unit testing.

    Stores objects in a nested dict structure: ``{bucket: {key: bytes}}``.
    All operations are synchronous dict operations wrapped in coroutines.

    Args:
        config: Optional StorageConfig for default bucket.

    Usage::

        storage = MemoryStorageAdapter()
        await storage.upload("photos", "cat.jpg", b"image-data")
        data = await storage.download("photos", "cat.jpg")
    """

    def __init__(self, config: StorageConfig | None = None) -> None:
        self._config = config if config is not None else StorageConfig()
        self._store: dict[str, dict[str, bytes]] = {}

    # ------------------------------------------------------------------
    # Public API — FileStorageManager Protocol
    # ------------------------------------------------------------------

    async def upload(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> UploadResult:
        """Upload an object to the in-memory store.

        Args:
            bucket: The bucket name.
            key: The object key.
            data: The raw bytes to store.
            content_type: MIME type.

        Returns:
            UploadResult: Metadata about the uploaded object.
        """
        if not bucket:
            raise ValidationError("Bucket name must not be empty", details={"bucket": bucket})
        if not key:
            raise ValidationError("Object key must not be empty", details={"key": key})

        if bucket not in self._store:
            self._store[bucket] = {}

        self._store[bucket][key] = data

        etag = str(uuid.uuid4())
        return UploadResult(
            key=key,
            etag=etag,
            url=f"memory://{bucket}/{key}",
        )

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object's raw bytes.

        Args:
            bucket: The bucket name.
            key: The object key.

        Returns:
            bytes: The raw object data.

        Raises:
            ValidationError: If the object does not exist.
        """
        bucket_data = self._store.get(bucket, {})
        if key not in bucket_data:
            raise ValidationError(
                f"Object not found: {bucket}/{key}",
                details={"bucket": bucket, "key": key},
            )
        return bucket_data[key]

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object from storage.

        Idempotent — does nothing if the object does not exist.

        Args:
            bucket: The bucket name.
            key: The object key.
        """
        bucket_data = self._store.get(bucket)
        if bucket_data is not None:
            bucket_data.pop(key, None)

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists in storage.

        Args:
            bucket: The bucket name.
            key: The object key.

        Returns:
            bool: ``True`` if the object exists.
        """
        return key in self._store.get(bucket, {})

    async def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expiry: int = 3600,
    ) -> str:
        """Generate a fake pre-signed URL for symmetry.

        For memory storage, returns a ``memory://`` URL.

        Args:
            bucket: The bucket name.
            key: The object key.
            expiry: URL validity duration in seconds.

        Returns:
            str: A ``memory://`` URL.

        Raises:
            ValidationError: If the object does not exist.
        """
        if not await self.exists(bucket, key):
            raise ValidationError(
                f"Object not found for pre-signed URL: {bucket}/{key}",
                details={"bucket": bucket, "key": key},
            )
        return f"memory://{bucket}/{key}?expiry={expiry}"

    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
    ) -> list[FileRef]:
        """List objects in a bucket with an optional prefix filter.

        Args:
            bucket: The bucket name.
            prefix: Optional key prefix to filter.

        Returns:
            list[FileRef]: List of object references.
        """
        bucket_data = self._store.get(bucket, {})
        results: list[FileRef] = []
        for key, data in bucket_data.items():
            if prefix and not key.startswith(prefix):
                continue
            ref = FileRef(
                bucket=bucket,
                key=key,
                size=len(data),
                content_type="application/octet-stream",
            )
            results.append(ref)
        return results
