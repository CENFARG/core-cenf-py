"""S3StorageAdapter — AWS S3 FileStorageManager using aiobotocore.

Supports MinIO/localstack via configurable endpoint_url.

Security: Pre-signed URLs are time-limited. NEVER log file contents or URLs.
Observability: All operations logged at DEBUG level.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from aiobotocore.session import AioSession
from botocore.exceptions import ClientError

from core_infrastructure.common.errors import PermanentError, TransientError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.filestorage.models import FileRef, UploadResult
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager

# S3 error codes that indicate a permanent (non-retryable) failure.
_PERMANENT_S3_CODES: frozenset[str] = frozenset({
    "404",
    "NoSuchKey",
    "NoSuchBucket",
    "AccessDenied",
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
})

# S3 error codes that indicate a transient (retryable) failure.
_TRANSIENT_S3_CODES: frozenset[str] = frozenset({
    "500",
    "503",
    "Throttling",
    "ServiceUnavailable",
    "SlowDown",
    "InternalError",
})


class S3StorageAdapter:
    """AWS S3 FileStorageManager using aiobotocore async client.

    Supports optional endpoint_url for MinIO/localstack.

    Args:
        config: ConfigManager for S3 bucket/region/endpoint.
        secret_manager: SecretManager for optional AWS credentials.
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for exception classification.
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

        self._bucket = config.get_string("filestorage.s3.bucket")
        self._region = config.get_string("filestorage.s3.region")
        self._endpoint_url = config.get_string("filestorage.s3.endpoint_url", default_value="") or None

        session = AioSession()
        self._session = session
        self._client = None  # Created lazily via _get_client

    async def _get_client(self) -> Any:
        """Get or create the aiobotocore S3 client.

        Returns:
            The aiobotocore S3 client instance.
        """
        if self._client is None:
            client_kwargs: dict[str, Any] = {"service_name": "s3", "region_name": self._region}
            if self._endpoint_url:
                client_kwargs["endpoint_url"] = self._endpoint_url
            client_ctx = await self._session.create_client(**client_kwargs)
            self._client = await client_ctx.__aenter__()
        return self._client

    # ------------------------------------------------------------------
    # Internal: error classification
    # ------------------------------------------------------------------

    def _classify_s3_error(self, exc: Exception) -> type[PermanentError] | type[TransientError]:
        """Classify an S3 exception as permanent or transient.

        Inspects botocore ClientError response codes. Defaults to transients
        for unknown exceptions (network timeouts, connection errors, etc.).

        Args:
            exc: The exception raised by the S3 client.

        Returns:
            PermanentError or TransientError class.
        """
        # Check for botocore ClientError with known codes
        try:
            error_code = exc.response["Error"]["Code"]  # type: ignore[attr-defined, union-attr]
        except (AttributeError, KeyError, TypeError):
            # Not a ClientError or missing response structure → transient
            return TransientError

        if error_code in _PERMANENT_S3_CODES:
            return PermanentError
        return TransientError

    def _raise_classified(
        self,
        exc: Exception,
        *,
        operation: str,
        bucket: str,
        key: str,
    ) -> None:
        """Classify, report, and raise a structured S3 error.

        Args:
            exc: The original exception from the S3 client.
            operation: Human-readable operation name (e.g. "upload").
            bucket: The S3 bucket name.
            key: The object key.

        Raises:
            PermanentError: If the error is classified as permanent.
            TransientError: If the error is classified as transient.
        """
        error_cls = self._classify_s3_error(exc)
        error = error_cls(
            f"S3 {operation} failed: {bucket}/{key}",
            details={"bucket": bucket, "key": key, "error": str(exc)},
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
        """Upload an object to S3.

        Args:
            bucket: The S3 bucket name.
            key: The object key.
            data: The raw bytes to store.
            content_type: MIME type of the object.

        Returns:
            UploadResult: Metadata about the uploaded object.

        Raises:
            TransientError: If the upload fails due to a transient issue.
            PermanentError: If the upload fails due to a permanent issue.
        """
        client = await self._get_client()
        try:
            result = await client.put_object(
                Bucket=bucket, Key=key, Body=data, ContentType=content_type,
            )
        except Exception as exc:
            self._raise_classified(
                exc,
                operation="upload",
                bucket=bucket,
                key=key,
            )

        etag = result.get("ETag", "").strip('"')
        location = result.get("Location", "")
        return UploadResult(
            key=key,
            etag=etag,
            url=location,
        )

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object's raw bytes from S3.

        Args:
            bucket: The S3 bucket name.
            key: The object key.

        Returns:
            bytes: The raw object data.

        Raises:
            TransientError: If the download fails due to a transient issue.
            PermanentError: If the download fails due to a permanent issue.
        """
        client = await self._get_client()
        try:
            result = await client.get_object(Bucket=bucket, Key=key)
        except Exception as exc:
            self._raise_classified(
                exc,
                operation="download",
                bucket=bucket,
                key=key,
            )

        body = result["Body"]
        return await body.read()  # type: ignore[no-any-return]

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object from S3.

        Idempotent — silently succeeds if the object does not exist.

        Args:
            bucket: The S3 bucket name.
            key: The object key.
        """
        client = await self._get_client()
        try:
            await client.delete_object(Bucket=bucket, Key=key)
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "S3StorageAdapter.delete", "bucket": bucket, "key": key})

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists in S3.

        Uses head_object — returns True on 200, False on 404.

        Args:
            bucket: The S3 bucket name.
            key: The object key.

        Returns:
            bool: ``True`` if the object exists.
        """
        client = await self._get_client()
        try:
            await client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            self._error_handler.report(
                exc, context={"source": "S3StorageAdapter.exists", "bucket": bucket, "key": key})
            return False
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "S3StorageAdapter.exists", "bucket": bucket, "key": key})
            return False

    async def generate_presigned_url(  # type: ignore[return]
        self,
        bucket: str,
        key: str,
        expiry: int = 3600,
    ) -> str:
        """Generate a time-limited S3 pre-signed URL.

        Args:
            bucket: The S3 bucket name.
            key: The object key.
            expiry: URL validity duration in seconds (default 3600).

        Returns:
            str: A time-limited pre-signed URL.

        Raises:
            TransientError: If URL generation fails due to a transient issue.
            PermanentError: If URL generation fails due to a permanent issue.
        """
        client = await self._get_client()
        try:
            url = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expiry,
            )
            return url  # type: ignore[no-any-return]
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
        """List objects in an S3 bucket with an optional prefix filter.

        Args:
            bucket: The S3 bucket name.
            prefix: Optional key prefix to filter.

        Returns:
            list[FileRef]: List of object references.
        """
        client = await self._get_client()
        try:
            result = await client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "S3StorageAdapter.list_objects", "bucket": bucket, "prefix": prefix})
            return []

        contents = result.get("Contents", [])
        results: list[FileRef] = []
        for obj in contents:
            ref = FileRef(
                bucket=bucket,
                key=obj.get("Key", ""),
                size=int(obj.get("Size", 0)),
                content_type="application/octet-stream",
            )
            results.append(ref)
        return results
