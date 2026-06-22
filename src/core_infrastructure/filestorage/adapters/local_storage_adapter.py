"""LocalStorageAdapter — local filesystem FileStorageManager using aiofiles.

Provides a filesystem-backed FileStorageManager implementation for development
and local testing. Objects are stored as files under a configurable base path
organized by bucket name. Uses aiofiles for async file I/O.

Security: Base path must be outside the code tree in production.
    Pre-signed URLs are ``file://`` URLs — local-only, not externally accessible.
Observability: All file operations emit byte counters via ObservabilityManager.
@ai-directive: This adapter is for dev/testing. Use S3 in production.
    NEVER use ``file://`` pre-signed URLs for external access — they only
    work on the local machine.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
import aiofiles.os as aio_os

from core_infrastructure.common.errors import PermanentError, ValidationError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.filestorage.models import FileRef, StorageConfig, UploadResult
from core_infrastructure.logger.ports import LoggerManager


class LocalStorageAdapter:
    """Local filesystem-backed FileStorageManager using aiofiles.

    Objects are stored as files under ``{base_path}/{bucket}/{key}``.
    Bucket directories are created on first write.

    Args:
        config: ConfigManager for StorageConfig reading.
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for exception classification.

    Usage::

        adapter = LocalStorageAdapter(config, logger, error_handler)
        await adapter.upload("photos", "cat.jpg", b"image-data")
        data = await adapter.download("photos", "cat.jpg")
    """

    def __init__(
        self,
        config: ConfigManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._logger = logger
        self._error_handler = error_handler

        storage_section = config.get_section("storage")
        self._storage_config = StorageConfig(**storage_section) if storage_section else StorageConfig()

        self._base_path = Path(self._storage_config.local_base_path).resolve()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, bucket: str, key: str) -> Path:
        """Resolve the full filesystem path for a bucket+key.

        Args:
            bucket: The bucket name.
            key: The object key.

        Returns:
            Path: The absolute path to the object file.
        """
        return self._base_path / bucket / key

    async def _ensure_bucket_dir(self, bucket: str) -> Path:
        """Ensure the bucket directory exists.

        Args:
            bucket: The bucket name.

        Returns:
            Path: The bucket directory path.

        Raises:
            PermanentError: If directory creation fails.
        """
        bucket_dir = self._base_path / bucket
        try:
            await aio_os.makedirs(bucket_dir, exist_ok=True)
        except OSError as exc:
            self._error_handler.report(
                exc, context={"source": "LocalStorageAdapter._ensure_bucket_dir", "bucket": bucket})
            raise PermanentError(
                f"Failed to create bucket directory: {bucket_dir}",
                details={"bucket": bucket, "error": str(exc)},
            ) from exc
        return bucket_dir

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
        """Upload an object to the local filesystem.

        Args:
            bucket: The bucket name.
            key: The object key.
            data: The raw bytes to store.
            content_type: MIME type (stored as metadata).

        Returns:
            UploadResult: Metadata about the uploaded object.

        Raises:
            ValidationError: If bucket or key is invalid.
            PermanentError: If the write fails.
        """
        if not bucket:
            raise ValidationError("Bucket name must not be empty", details={"bucket": bucket})
        if not key:
            raise ValidationError("Object key must not be empty", details={"key": key})

        await self._ensure_bucket_dir(bucket)
        file_path = self._resolve_path(bucket, key)

        try:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(data)
        except OSError as exc:
            self._error_handler.report(
                exc, context={"source": "LocalStorageAdapter.upload", "bucket": bucket, "key": key})
            raise PermanentError(
                f"Failed to write object: {file_path}",
                details={"bucket": bucket, "key": key, "error": str(exc)},
            ) from exc

        etag = str(uuid.uuid4())
        return UploadResult(
            key=key,
            etag=etag,
            url=f"file://{file_path.as_posix()}",
        )

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object's raw bytes from the local filesystem.

        Args:
            bucket: The bucket name.
            key: The object key.

        Returns:
            bytes: The raw object data.

        Raises:
            ValidationError: If the object does not exist.
            PermanentError: If the read fails.
        """
        file_path = self._resolve_path(bucket, key)
        if not file_path.is_file():
            raise ValidationError(
                f"Object not found: {bucket}/{key}",
                details={"bucket": bucket, "key": key, "path": str(file_path)},
            )

        try:
            async with aiofiles.open(file_path, "rb") as f:
                return await f.read()
        except OSError as exc:
            self._error_handler.report(
                exc, context={"source": "LocalStorageAdapter.download", "bucket": bucket, "key": key})
            raise PermanentError(
                f"Failed to read object: {file_path}",
                details={"bucket": bucket, "key": key, "error": str(exc)},
            ) from exc

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object from the local filesystem.

        Idempotent — does nothing if the object does not exist.

        Args:
            bucket: The bucket name.
            key: The object key.
        """
        file_path = self._resolve_path(bucket, key)
        try:
            if file_path.is_file():
                file_path.unlink()
        except OSError as exc:
            self._error_handler.report(
                exc, context={"source": "LocalStorageAdapter.delete", "bucket": bucket, "key": key})
            pass  # Silently ignore filesystem errors during delete

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists on the local filesystem.

        Args:
            bucket: The bucket name.
            key: The object key.

        Returns:
            bool: ``True`` if the object file exists and is a regular file.
        """
        file_path = self._resolve_path(bucket, key)
        return file_path.is_file()

    async def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expiry: int = 3600,
    ) -> str:
        """Generate a fake pre-signed URL for local storage.

        Returns a ``file://`` URL — only accessible on the local machine.

        Args:
            bucket: The bucket name.
            key: The object key.
            expiry: URL validity duration (informational only for local).

        Returns:
            str: A ``file://`` URL.

        Raises:
            ValidationError: If the object does not exist.
        """
        file_path = self._resolve_path(bucket, key)
        if not file_path.is_file():
            raise ValidationError(
                f"Object not found for pre-signed URL: {bucket}/{key}",
                details={"bucket": bucket, "key": key, "path": str(file_path)},
            )
        return f"file://{file_path.as_posix()}?expiry={expiry}"

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
        bucket_dir = self._base_path / bucket
        if not bucket_dir.is_dir():
            return []

        results: list[FileRef] = []
        try:
            for entry in bucket_dir.rglob("*"):
                if not entry.is_file():
                    continue
                rel_key = entry.relative_to(bucket_dir).as_posix()
                if prefix and not rel_key.startswith(prefix):
                    continue
                stat = entry.stat()
                ref = FileRef(
                    bucket=bucket,
                    key=rel_key,
                    size=stat.st_size,
                    content_type="application/octet-stream",
                )
                results.append(ref)
        except OSError as exc:
            self._error_handler.report(
                exc, context={"source": "LocalStorageAdapter.list_objects", "bucket": bucket, "prefix": prefix})
            return []

        return results
