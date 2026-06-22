"""Unit tests for AzureStorageAdapter — Azure Blob Storage FileStorageManager.

Tests cover:
- Protocol compliance check
- Mock azure-storage-blob to verify method calls
- Test SAS token generation
- Test container↔bucket mapping

Security: Tests use mock azure-storage-blob — no real Azure credentials required.
Observability: Tests verify adapter method signatures and error paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core_infrastructure.common.errors import PermanentError, TransientError
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.filestorage.adapters.azure_storage_adapter import AzureStorageAdapter
from core_infrastructure.filestorage.models import FileRef
from core_infrastructure.filestorage.ports import FileStorageManager
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with Azure settings."""
    return InMemoryConfigAdapter(
        initial_data={
            "filestorage": {
                "azure": {
                    "connection_string": "DefaultEndpointsProtocol=https;AccountName=myaccount;AccountKey=key;EndpointSuffix=core.windows.net",
                    "container": "my-container",
                },
            },
        }
    )


@pytest.fixture
def secret_manager() -> InMemorySecretAdapter:
    """Create an InMemorySecretAdapter."""
    return InMemorySecretAdapter()


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """Create an InMemoryLoggerAdapter."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    """Create an InMemoryObservabilityAdapter."""
    return InMemoryObservabilityAdapter()


@pytest.fixture
def error_handler(
    config: InMemoryConfigAdapter,
    logger: InMemoryLoggerAdapter,
    observability: InMemoryObservabilityAdapter,
) -> CapturingErrorAdapter:
    """Create a CapturingErrorAdapter."""
    return CapturingErrorAdapter(config, logger, observability)


@pytest.fixture
def mock_blob_client() -> MagicMock:
    """Create a mock azure blob client."""
    blob = MagicMock()
    blob.upload_blob = MagicMock()
    blob.download_blob = MagicMock()
    blob.delete_blob = MagicMock()
    blob.exists = MagicMock(return_value=False)
    return blob


@pytest.fixture
def mock_container_client(mock_blob_client: MagicMock) -> MagicMock:
    """Create a mock azure container client."""
    container = MagicMock()
    container.get_blob_client = MagicMock(return_value=mock_blob_client)
    return container


@pytest.fixture
def mock_service_client(mock_container_client: MagicMock) -> MagicMock:
    """Create a mock azure BlobServiceClient."""
    service = MagicMock()
    service.get_container_client = MagicMock(return_value=mock_container_client)
    return service


@pytest.fixture
def storage(
    config: InMemoryConfigAdapter,
    secret_manager: InMemorySecretAdapter,
    logger: InMemoryLoggerAdapter,
    error_handler: CapturingErrorAdapter,
    mock_service_client: MagicMock,
) -> AzureStorageAdapter:
    """Create an AzureStorageAdapter with mocked azure BlobServiceClient."""
    with patch(
        "core_infrastructure.filestorage.adapters.azure_storage_adapter.BlobServiceClient",
    ) as mock_bsc:
        mock_bsc.from_connection_string = MagicMock(return_value=mock_service_client)
        return AzureStorageAdapter(config, secret_manager, logger, error_handler)


class TestAzureStorageAdapterProtocol:
    """Verify AzureStorageAdapter satisfies FileStorageManager Protocol."""

    def test_satisfies_file_storage_manager_protocol(self, storage: AzureStorageAdapter) -> None:
        """AzureStorageAdapter passes isinstance check against FileStorageManager."""
        assert isinstance(storage, FileStorageManager)


class TestAzureStorageAdapterBucketMapping:
    """Verify bucket param is mapped to container internally."""

    @pytest.mark.asyncio
    async def test_upload_uses_container_from_get_blob_client(
        self, storage: AzureStorageAdapter, mock_service_client: MagicMock,
        mock_container_client: MagicMock, mock_blob_client: MagicMock,
    ) -> None:
        """upload() gets container client using the bucket parameter."""
        mock_blob_client.upload_blob.return_value = {"etag": "0x8D..."}

        await storage.upload("photos-bucket", "cat.jpg", b"cat-data", content_type="image/jpeg")

        mock_service_client.get_container_client.assert_called_once_with("photos-bucket")
        mock_container_client.get_blob_client.assert_called_once_with("cat.jpg")

    @pytest.mark.asyncio
    async def test_list_objects_uses_container(
        self, storage: AzureStorageAdapter, mock_service_client: MagicMock,
        mock_container_client: MagicMock,
    ) -> None:
        """list_objects() gets container client using the bucket parameter."""
        mock_container_client.list_blobs.return_value = []

        await storage.list_objects("docs-container", prefix="reports/")

        mock_service_client.get_container_client.assert_called_once_with("docs-container")


class TestAzureStorageAdapterUpload:
    """Verify upload delegates to azure blob client."""

    @pytest.mark.asyncio
    async def test_upload_calls_blob_upload(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """upload() calls upload_blob with data and content_type."""
        mock_blob_client.upload_blob.return_value = {"etag": "0x8DABC123", "url": "https://account.blob.core.windows.net/container/key"}

        result = await storage.upload("my-bucket", "data/file.txt", b"hello world", content_type="text/plain")

        mock_blob_client.upload_blob.assert_called_once_with(b"hello world", content_type="text/plain")
        assert result.key == "data/file.txt"
        assert result.etag == "0x8DABC123"
        assert "https://" in result.url

    @pytest.mark.asyncio
    async def test_upload_wraps_exception_as_transient_error(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """upload() wraps azure exception into TransientError."""
        mock_blob_client.upload_blob.side_effect = Exception("Azure network error")

        with pytest.raises(TransientError, match="Azure upload failed"):
            await storage.upload("bucket", "key.txt", b"data")


class TestAzureStorageAdapterDownload:
    """Verify download delegates to azure blob client."""

    @pytest.mark.asyncio
    async def test_download_calls_blob_download(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """download() calls download_blob and reads content."""
        mock_downloader = MagicMock()
        mock_downloader.readall = MagicMock(return_value=b"azure blob content")
        mock_blob_client.download_blob.return_value = mock_downloader

        data = await storage.download("my-bucket", "data/file.bin")

        mock_blob_client.download_blob.assert_called_once()
        assert data == b"azure blob content"

    @pytest.mark.asyncio
    async def test_download_wraps_exception_as_transient_error(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """download() wraps azure exception into TransientError."""
        mock_blob_client.download_blob.side_effect = Exception("Blob not found")

        with pytest.raises(TransientError, match="Azure download failed"):
            await storage.download("bucket", "key.txt")


class TestAzureStorageAdapterDelete:
    """Verify delete delegates to azure blob client."""

    @pytest.mark.asyncio
    async def test_delete_calls_blob_delete(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """delete() calls delete_blob on the blob client."""
        await storage.delete("my-bucket", "key.txt")
        mock_blob_client.delete_blob.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_is_idempotent_on_exception(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """delete() does not raise for non-existent blob."""
        mock_blob_client.delete_blob.side_effect = Exception("BlobNotFound")
        await storage.delete("my-bucket", "no-such-key.txt")  # Should not raise


class TestAzureStorageAdapterExists:
    """Verify exists uses blob client exists()."""

    @pytest.mark.asyncio
    async def test_exists_returns_true(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """exists() returns True when blob.exists() returns True."""
        mock_blob_client.exists.return_value = True

        result = await storage.exists("my-bucket", "data/file.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """exists() returns False when blob.exists() returns False."""
        mock_blob_client.exists.return_value = False

        result = await storage.exists("my-bucket", "data/missing.txt")
        assert result is False


class TestAzureStorageAdapterGenerateSasToken:
    """Verify SAS token generation for Azure."""

    @pytest.mark.asyncio
    async def test_generate_presigned_url_generates_sas_token(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """generate_presigned_url() generates a SAS-based URL."""
        mock_blob_client.url = "https://myaccount.blob.core.windows.net/my-bucket/data/file.txt"

        with patch(
            "core_infrastructure.filestorage.adapters.azure_storage_adapter.generate_blob_sas",
            return_value="sv=2023-11-03&se=2024-01-01&sr=b&sig=abc123",
        ) as mock_sas:
            url = await storage.generate_presigned_url("my-bucket", "data/file.txt", expiry=600)

            mock_sas.assert_called_once()
            assert "data/file.txt" in url
            assert "sv=2023-11-03" in url
            assert url.startswith("https://myaccount.blob.core.windows.net/")

    @pytest.mark.asyncio
    async def test_generate_presigned_url_default_expiry(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """generate_presigned_url() defaults expiry to 3600."""
        mock_blob_client.url = "https://myaccount.blob.core.windows.net/bucket/key"

        with patch(
            "core_infrastructure.filestorage.adapters.azure_storage_adapter.generate_blob_sas",
            return_value="sv=2023-11-03&se=2024-01-01&sr=b&sig=xyz",
        ) as mock_sas:
            await storage.generate_presigned_url("bucket", "key")

            call_kwargs = mock_sas.call_args.kwargs
            expiry_dt = call_kwargs["expiry"]
            assert expiry_dt is not None


class TestAzureStorageAdapterListObjects:
    """Verify list_objects uses container client list_blobs."""

    @pytest.mark.asyncio
    async def test_list_objects_returns_file_refs(
        self, storage: AzureStorageAdapter, mock_container_client: MagicMock,
    ) -> None:
        """list_objects() converts azure blobs to FileRef list."""

        class FakeBlob:
            name = "photos/cat.jpg"
            size = 2048

        class FakeBlob2:
            name = "photos/dog.jpg"
            size = 4096

        mock_container_client.list_blobs.return_value = [FakeBlob(), FakeBlob2()]

        result = await storage.list_objects("my-bucket", prefix="photos/")

        mock_container_client.list_blobs.assert_called_once_with(name_starts_with="photos/")
        assert len(result) == 2
        assert all(isinstance(ref, FileRef) for ref in result)
        assert {ref.key for ref in result} == {"photos/cat.jpg", "photos/dog.jpg"}
        assert {ref.bucket for ref in result} == {"my-bucket"}

    @pytest.mark.asyncio
    async def test_list_objects_empty_returns_empty_list(
        self, storage: AzureStorageAdapter, mock_container_client: MagicMock,
    ) -> None:
        """list_objects() returns empty list when no blobs found."""
        mock_container_client.list_blobs.return_value = []

        result = await storage.list_objects("my-bucket", prefix="nonexistent/")
        assert result == []


class TestAzureStorageAdapterErrorClassification:
    """Verify Azure adapter correctly classifies transient vs permanent errors."""

    @pytest.mark.asyncio
    async def test_resource_not_found_raises_permanent_error(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """ResourceNotFoundError raises PermanentError."""
        from azure.core.exceptions import ResourceNotFoundError

        mock_blob_client.download_blob.side_effect = ResourceNotFoundError("Blob not found")

        with pytest.raises(PermanentError, match="Azure download failed"):
            await storage.download("bucket", "missing.txt")

    @pytest.mark.asyncio
    async def test_generic_exception_raises_transient_error(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
    ) -> None:
        """Generic Exception (network error) still raises TransientError."""
        mock_blob_client.download_blob.side_effect = Exception("Azure network error")

        with pytest.raises(TransientError, match="Azure download failed"):
            await storage.download("bucket", "key.txt")

    @pytest.mark.asyncio
    async def test_error_handler_report_called_on_error(
        self, storage: AzureStorageAdapter, mock_blob_client: MagicMock,
        logger: InMemoryLoggerAdapter,
    ) -> None:
        """error_handler.report() is called before raising the error."""
        from azure.core.exceptions import ResourceNotFoundError

        mock_blob_client.download_blob.side_effect = ResourceNotFoundError("Blob not found")

        with pytest.raises(PermanentError):
            await storage.download("bucket", "missing.txt")

        error_logs = [r for r in logger.get_logs() if r.get("level") == "ERROR"]
        assert len(error_logs) >= 1, "error_handler.report() should log an ERROR"
