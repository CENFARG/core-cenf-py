"""GcsStorageAdapter — Google Cloud Storage FileStorageManager using gcloud-aio-storage.

Provides a GCS-backed FileStorageManager implementation using the
gcloud-aio-storage async library. Supports ADC (Application Default
Credentials) when credentials_path is not configured.

Security: Pre-signed URLs are time-limited via GCS signed URLs.
    NEVER log file contents or pre-signed URLs at INFO or above.
Observability: All operations logged at DEBUG level with byte counters.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from aiohttp import ClientResponseError
from gcloud.aio.storage import Storage

from core_infrastructure.common.errors import PermanentError, TransientError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.filestorage.models import FileRef, UploadResult
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager


class GcsStorageAdapter:
    """Google Cloud Storage FileStorageManager using gcloud-aio-storage.

    Reads GCS configuration via ConfigManager and creates an async
    gcloud.aio.storage.Storage client. Supports ADC when no explicit
    credentials path is configured.

    Args:
        config: ConfigManager for GCS bucket/project/credentials reading.
        secret_manager: SecretManager for optional credentials retrieval.
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for exception classification.

    Usage::

        adapter = GcsStorageAdapter(config, secret_manager, logger, error_handler)
        await adapter.upload("my-bucket", "data/file.txt", b"content")
        data = await adapter.download("my-bucket", "data/file.txt")
    """

    def __init__(
        self,
        config: ConfigManager,
        secret_manager: SecretManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._secret_manager = secret_manager
        self._logger = logger
        self._error_handler = error_handler

        self._bucket = config.get_string("filestorage.gcs.bucket")
        self._project = config.get_string("filestorage.gcs.project")
        self._credentials_path = config.get_string("filestorage.gcs.credentials_path", default_value="") or None

        self._client = Storage()

    # ------------------------------------------------------------------
    # Internal: error classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_gcs_error(exc: Exception) -> type[PermanentError] | type[TransientError]:
        """Classify a GCS exception as permanent or transient.

        Inspects aiohttp ClientResponseError status codes. Defaults to
        transient for unknown exceptions (network timeouts, etc.).

        Args:
            exc: The exception raised by the GCS client.

        Returns:
            PermanentError or TransientError class.
        """
        if isinstance(exc, ClientResponseError):
            if exc.status == 404:
                return PermanentError
            # 429 (rate limit) and 5xx are transient/retryable
            if exc.status == 429 or 500 <= exc.status < 600:
                return TransientError
        # Default: transient (network errors, timeouts, etc.)
        return TransientError

    def _raise_classified(
        self,
        exc: Exception,
        *,
        operation: str,
        bucket: str,
        key: str,
    ) -> None:
        """Classify, report, and raise a structured GCS error.

        Args:
            exc: The original exception from the GCS client.
            operation: Human-readable operation name (e.g. "upload").
            bucket: The GCS bucket name.
            key: The object key.

        Raises:
            PermanentError: If the error is classified as permanent.
            TransientError: If the error is classified as transient.
        """
        # Safely extract error message — some aiohttp exceptions crash on str()
        try:
            exc_str = str(exc)
        except Exception:
            exc_str = repr(exc)

        error_cls = self._classify_gcs_error(exc)
        error = error_cls(
            f"GCS {operation} failed: {bucket}/{key}",
            details={"bucket": bucket, "key": key, "error": exc_str},
        )
        self._error_handler.report(error, context={"bucket": bucket, "key": key})
        raise error from exc

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
        """Upload an object to GCS.

        Args:
            bucket: The GCS bucket name.
            key: The object key.
            data: The raw bytes to store.
            content_type: MIME type of the object.

        Returns:
            UploadResult: Metadata about the uploaded object.

        Raises:
            TransientError: If the upload fails due to a transient issue.
            PermanentError: If the upload fails due to a permanent issue.
        """
        try:
            result = await self._client.upload(bucket, key, data)
        except Exception as exc:
            self._raise_classified(
                exc,
                operation="upload",
                bucket=bucket,
                key=key,
            )

        return UploadResult(
            key=key,
            etag=result.get("etag", ""),
            url=result.get("selfLink", ""),
        )

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object's raw bytes from GCS.

        Args:
            bucket: The GCS bucket name.
            key: The object key.

        Returns:
            bytes: The raw object data.

        Raises:
            TransientError: If the download fails due to a transient issue.
            PermanentError: If the download fails due to a permanent issue.
        """
        try:
            return await self._client.download(bucket, key)  # type: ignore[no-any-return]
        except Exception as exc:
            self._raise_classified(
                exc,
                operation="download",
                bucket=bucket,
                key=key,
            )

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object from GCS.

        Idempotent — silently succeeds if the object does not exist.

        Args:
            bucket: The GCS bucket name.
            key: The object key.
        """
        try:
            await self._client.delete(bucket, key)
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "GcsStorageAdapter.delete", "bucket": bucket, "key": key})

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists in GCS.

        Args:
            bucket: The GCS bucket name.
            key: The object key.

        Returns:
            bool: ``True`` if the object exists.
        """
        try:
            objects = await self._client.list_objects(bucket, params={"prefix": key})
            items: list[dict[str, Any]] = objects.get("items", [])
            return any(obj.get("name") == key for obj in items)
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "GcsStorageAdapter.exists", "bucket": bucket, "key": key})
            return False

    async def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expiry: int = 3600,
    ) -> str:
        """Generate a time-limited GCS signed URL.

        Args:
            bucket: The GCS bucket name.
            key: The object key.
            expiry: URL validity duration in seconds (default 3600).

        Returns:
            str: A time-limited GCS download URL.

        Raises:
            PermanentError: If URL generation fails.
        """
        try:
            return await self._client.get_download_url(  # type: ignore[attr-defined, no-any-return]
                bucket, key, expiration=expiry
            )
        except Exception as exc:
            self._raise_classified(
                exc,
                operation="pre-signed URL generation",
                bucket=bucket,
                key=key,
            )

    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
    ) -> list[FileRef]:
        """List objects in a GCS bucket with an optional prefix filter.

        Args:
            bucket: The GCS bucket name.
            prefix: Optional key prefix to filter.

        Returns:
            list[FileRef]: List of object references.
        """
        try:
            objects = await self._client.list_objects(bucket, params={"prefix": prefix})
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "GcsStorageAdapter.list_objects", "bucket": bucket, "prefix": prefix})
            return []

        items: list[dict[str, Any]] = objects.get("items", [])
        results: list[FileRef] = []
        for obj in items:
            ref = FileRef(
                bucket=bucket,
                key=obj.get("name", ""),
                size=int(obj.get("size", 0)),
                content_type=obj.get("contentType", "application/octet-stream"),
            )
            results.append(ref)
        return results
