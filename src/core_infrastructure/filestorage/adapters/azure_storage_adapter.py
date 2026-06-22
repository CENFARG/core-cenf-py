"""AzureStorageAdapter — Azure Blob Storage FileStorageManager using azure-storage-blob.

Maps the ``bucket`` protocol parameter to Azure container internally.
Uses SAS tokens instead of pre-signed URLs for time-limited access.

Security: SAS tokens are time-limited. NEVER log SAS tokens or file contents.
Observability: All operations logged at DEBUG level.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    generate_blob_sas,
)

from core_infrastructure.common.errors import PermanentError, TransientError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.filestorage.models import FileRef, UploadResult
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager

try:
    from azure.core.exceptions import ResourceNotFoundError
except ImportError:  # pragma: no cover
    ResourceNotFoundError = Exception  # type: ignore[assignment,misc]


class AzureStorageAdapter:
    """Azure Blob Storage FileStorageManager using azure-storage-blob.

    Maps ``bucket`` to Azure container. Uses SAS tokens for access.

    Args:
        config: ConfigManager for Azure connection_string and container.
        secret_manager: SecretManager for optional connection string retrieval.
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

        connection_string = config.get_string("filestorage.azure.connection_string")
        self._container = config.get_string("filestorage.azure.container")

        self._service_client = BlobServiceClient.from_connection_string(connection_string)

    def _get_blob_client(self, bucket: str, key: str) -> Any:
        """Get a blob client for the given container and blob name.

        Args:
            bucket: The Azure container name (mapped from bucket protocol param).
            key: The blob name.

        Returns:
            The azure blob client instance.
        """
        container_client = self._service_client.get_container_client(bucket)
        return container_client.get_blob_client(key)

    def _get_container_client(self, bucket: str) -> Any:
        """Get a container client for the given container name.

        Args:
            bucket: The Azure container name (mapped from bucket protocol param).

        Returns:
            The azure container client instance.
        """
        return self._service_client.get_container_client(bucket)

    # ------------------------------------------------------------------
    # Internal: error classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_azure_error(exc: Exception) -> type[PermanentError] | type[TransientError]:
        """Classify an Azure exception as permanent or transient.

        Inspects Azure SDK exception types. ResourceNotFoundError (404)
        is permanent. Everything else defaults to transient (network
        timeouts, 5xx, etc.).

        Args:
            exc: The exception raised by the Azure client.

        Returns:
            PermanentError or TransientError class.
        """
        if isinstance(exc, ResourceNotFoundError):
            return PermanentError
        # Default: transient (network errors, timeouts, 5xx, etc.)
        return TransientError

    def _raise_classified(
        self,
        exc: Exception,
        *,
        operation: str,
        bucket: str,
        key: str,
    ) -> None:
        """Classify, report, and raise a structured Azure error.

        Args:
            exc: The original exception from the Azure client.
            operation: Human-readable operation name (e.g. "upload").
            bucket: The Azure container name.
            key: The blob name.

        Raises:
            PermanentError: If the error is classified as permanent.
            TransientError: If the error is classified as transient.
        """
        error_cls = self._classify_azure_error(exc)
        error = error_cls(
            f"Azure {operation} failed: {bucket}/{key}",
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
        """Upload an object to Azure Blob Storage.

        Args:
            bucket: The Azure container name (mapped from bucket).
            key: The blob name.
            data: The raw bytes to store.
            content_type: MIME type of the blob.

        Returns:
            UploadResult: Metadata about the uploaded blob.

        Raises:
            TransientError: If the upload fails due to a transient issue.
            PermanentError: If the upload fails due to a permanent issue.
        """
        blob_client = self._get_blob_client(bucket, key)
        try:
            result = blob_client.upload_blob(data, content_type=content_type)
        except Exception as exc:
            self._raise_classified(
                exc,
                operation="upload",
                bucket=bucket,
                key=key,
            )

        etag = result.get("etag", "")
        url = result.get("url", "")
        return UploadResult(
            key=key,
            etag=etag,
            url=url,
        )

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object's raw bytes from Azure Blob Storage.

        Args:
            bucket: The Azure container name.
            key: The blob name.

        Returns:
            bytes: The raw blob data.

        Raises:
            TransientError: If the download fails due to a transient issue.
            PermanentError: If the download fails due to a permanent issue.
        """
        blob_client = self._get_blob_client(bucket, key)
        try:
            downloader = blob_client.download_blob()
            return downloader.readall()  # type: ignore[no-any-return]
        except Exception as exc:
            self._raise_classified(
                exc,
                operation="download",
                bucket=bucket,
                key=key,
            )

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object from Azure Blob Storage.

        Idempotent — silently succeeds if the blob does not exist.

        Args:
            bucket: The Azure container name.
            key: The blob name.
        """
        blob_client = self._get_blob_client(bucket, key)
        try:
            blob_client.delete_blob()
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "AzureStorageAdapter.delete", "bucket": bucket, "key": key})

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if a blob exists in Azure Blob Storage.

        Args:
            bucket: The Azure container name.
            key: The blob name.

        Returns:
            bool: ``True`` if the blob exists.
        """
        blob_client = self._get_blob_client(bucket, key)
        try:
            return bool(blob_client.exists())
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "AzureStorageAdapter.exists", "bucket": bucket, "key": key})
            return False

    async def generate_presigned_url(
        self,
        bucket: str,
        key: str,
        expiry: int = 3600,
    ) -> str:
        """Generate a time-limited SAS URL for Azure Blob Storage.

        Uses SAS (Shared Access Signature) tokens instead of pre-signed
        URLs. The SAS token grants read permission for the specified
        duration.

        Args:
            bucket: The Azure container name.
            key: The blob name.
            expiry: SAS token validity duration in seconds (default 3600).

        Returns:
            str: A time-limited URL with SAS token.

        Raises:
            TransientError: If SAS token generation fails due to a transient issue.
            PermanentError: If SAS token generation fails due to a permanent issue.
        """
        blob_client = self._get_blob_client(bucket, key)
        try:
            sas_token = generate_blob_sas(
                account_name=blob_client.account_name,
                container_name=bucket,
                blob_name=key,
                account_key=self._service_client.credential.account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.now(timezone.utc) + timedelta(seconds=expiry),  # noqa: UP017
            )
            return f"{blob_client.url}?{sas_token}"
        except Exception as exc:
            self._raise_classified(
                exc,
                operation="SAS token generation",
                bucket=bucket,
                key=key,
            )

    async def list_objects(
        self,
        bucket: str,
        prefix: str = "",
    ) -> list[FileRef]:
        """List blobs in an Azure container with an optional prefix filter.

        Args:
            bucket: The Azure container name.
            prefix: Optional blob name prefix to filter.

        Returns:
            list[FileRef]: List of blob references.
        """
        container_client = self._get_container_client(bucket)
        try:
            blobs = container_client.list_blobs(name_starts_with=prefix)
        except Exception as exc:
            self._error_handler.report(
                exc, context={"source": "AzureStorageAdapter.list_objects", "bucket": bucket, "prefix": prefix})
            return []

        results: list[FileRef] = []
        for blob in blobs:
            ref = FileRef(
                bucket=bucket,
                key=blob.name,
                size=blob.size if blob.size else 0,
                content_type="application/octet-stream",
            )
            results.append(ref)
        return results
