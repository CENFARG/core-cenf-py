"""Unit tests for GcsStorageAdapter — Google Cloud Storage FileStorageManager.

Tests cover:
- Protocol compliance (satisfies FileStorageManager)
- Constructor reads config correctly
- Mock gcloud-aio-storage.Storage method calls with correct params
- Error wrapping (GCS exceptions → TransientError)

Security: Tests use mock storage — no real GCS credentials required.
Observability: Tests verify adapter method signatures and error paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_infrastructure.common.errors import TransientError
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.filestorage.adapters.gcs_storage_adapter import GcsStorageAdapter
from core_infrastructure.filestorage.models import FileRef
from core_infrastructure.filestorage.ports import FileStorageManager
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with GCS settings."""
    return InMemoryConfigAdapter(
        initial_data={
            "filestorage": {
                "gcs": {
                    "bucket": "my-gcs-bucket",
                    "project": "my-gcp-project",
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
def mock_storage() -> MagicMock:
    """Create a mock gcloud.aio.storage.Storage."""
    storage_mock = MagicMock()
    storage_mock.upload = AsyncMock()
    storage_mock.download = AsyncMock()
    storage_mock.delete = AsyncMock()
    storage_mock.list_objects = AsyncMock()
    storage_mock.get_download_url = AsyncMock()
    return storage_mock


@pytest.fixture
def storage(
    config: InMemoryConfigAdapter,
    secret_manager: InMemorySecretAdapter,
    logger: InMemoryLoggerAdapter,
    error_handler: CapturingErrorAdapter,
    mock_storage: MagicMock,
) -> GcsStorageAdapter:
    """Create a GcsStorageAdapter with mocked gcloud storage."""
    with patch(
        "core_infrastructure.filestorage.adapters.gcs_storage_adapter.Storage",
        return_value=mock_storage,
    ):
        return GcsStorageAdapter(config, secret_manager, logger, error_handler)


class TestGcsStorageAdapterProtocol:
    """Verify GcsStorageAdapter satisfies FileStorageManager Protocol."""

    def test_satisfies_file_storage_manager_protocol(self, storage: GcsStorageAdapter) -> None:
        """GcsStorageAdapter passes isinstance check against FileStorageManager."""
        assert isinstance(storage, FileStorageManager)


class TestGcsStorageAdapterConstructor:
    """Verify constructor reads config correctly."""

    def test_constructor_reads_bucket_from_config(self, storage: GcsStorageAdapter) -> None:
        """Constructor reads filestorage.gcs.bucket from ConfigManager."""
        assert storage._bucket == "my-gcs-bucket"

    def test_constructor_reads_project_from_config(self, storage: GcsStorageAdapter) -> None:
        """Constructor reads filestorage.gcs.project from ConfigManager."""
        assert storage._project == "my-gcp-project"

    def test_constructor_reads_credentials_path_defaults_none(
        self, config: InMemoryConfigAdapter, secret_manager: InMemorySecretAdapter,
        logger: InMemoryLoggerAdapter, error_handler: CapturingErrorAdapter,
        mock_storage: MagicMock,
    ) -> None:
        """Constructor defaults credentials_path to None when not configured."""
        with patch(
            "core_infrastructure.filestorage.adapters.gcs_storage_adapter.Storage",
            return_value=mock_storage,
        ):
            adapter = GcsStorageAdapter(config, secret_manager, logger, error_handler)
            assert adapter._credentials_path is None


class TestGcsStorageAdapterUpload:
    """Verify upload delegates to gcloud-aio-storage.Storage.upload."""

    @pytest.mark.asyncio
    async def test_upload_calls_storage_upload_with_correct_params(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """upload() calls storage.upload(bucket, key, data) and returns UploadResult."""
        mock_storage.upload.return_value = {"etag": "etag-abc123", "selfLink": "https://example.com/obj"}

        result = await storage.upload("my-bucket", "test/key.txt", b"hello", content_type="text/plain")

        mock_storage.upload.assert_called_once_with("my-bucket", "test/key.txt", b"hello")
        assert result.key == "test/key.txt"
        assert result.etag == "etag-abc123"
        assert "https://example.com/obj" in result.url

    @pytest.mark.asyncio
    async def test_upload_wraps_exception_as_transient_error(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """upload() wraps gcloud exception into TransientError."""
        mock_storage.upload.side_effect = Exception("Network timeout")

        with pytest.raises(TransientError, match="GCS upload failed"):
            await storage.upload("bucket", "key.txt", b"data")


class TestGcsStorageAdapterDownload:
    """Verify download delegates to gcloud-aio-storage.Storage.download."""

    @pytest.mark.asyncio
    async def test_download_calls_storage_download_with_correct_params(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """download() calls storage.download(bucket, key) and returns bytes."""
        mock_storage.download.return_value = b"file contents"

        data = await storage.download("my-bucket", "data/file.bin")

        mock_storage.download.assert_called_once_with("my-bucket", "data/file.bin")
        assert data == b"file contents"

    @pytest.mark.asyncio
    async def test_download_wraps_exception_as_transient_error(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """download() wraps gcloud exception into TransientError."""
        mock_storage.download.side_effect = Exception("Connection refused")

        with pytest.raises(TransientError, match="GCS download failed"):
            await storage.download("bucket", "key.txt")


class TestGcsStorageAdapterDelete:
    """Verify delete delegates to gcloud-aio-storage.Storage.delete."""

    @pytest.mark.asyncio
    async def test_delete_calls_storage_delete_with_correct_params(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """delete() calls storage.delete(bucket, key)."""
        await storage.delete("my-bucket", "key.txt")

        mock_storage.delete.assert_called_once_with("my-bucket", "key.txt")

    @pytest.mark.asyncio
    async def test_delete_is_idempotent_on_exception(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """delete() does not raise for non-existent object (404-like)."""
        mock_storage.delete.side_effect = Exception("Not Found")

        # Should not raise — delete is idempotent
        await storage.delete("my-bucket", "no-such-key.txt")


class TestGcsStorageAdapterExists:
    """Verify exists checks object presence via list_objects."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_key_found(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """exists() returns True when list_objects includes the key."""
        mock_storage.list_objects.return_value = [
            {"name": "data/file.txt", "size": 1024},
            {"name": "data/other.txt", "size": 512},
        ]

        result = await storage.exists("my-bucket", "data/file.txt")
        assert result is True
        mock_storage.list_objects.assert_called_once_with("my-bucket", prefix="data/file.txt")

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_key_not_found(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """exists() returns False when list_objects does not include the key."""
        mock_storage.list_objects.return_value = []

        result = await storage.exists("my-bucket", "data/missing.txt")
        assert result is False


class TestGcsStorageAdapterGeneratePresignedUrl:
    """Verify generate_presigned_url delegates to gcloud get_download_url."""

    @pytest.mark.asyncio
    async def test_generate_presigned_url_calls_get_download_url(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """generate_presigned_url() calls storage.get_download_url with expiry."""
        mock_storage.get_download_url.return_value = "https://storage.googleapis.com/bucket/key?token=abc"

        url = await storage.generate_presigned_url("my-bucket", "data/file.txt", expiry=600)

        mock_storage.get_download_url.assert_called_once_with(
            "my-bucket", "data/file.txt", expiration=600,
        )
        assert url == "https://storage.googleapis.com/bucket/key?token=abc"

    @pytest.mark.asyncio
    async def test_generate_presigned_url_default_expiry(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """generate_presigned_url() defaults expiry to 3600 seconds."""
        mock_storage.get_download_url.return_value = "https://example.com/url"

        await storage.generate_presigned_url("bucket", "key")

        mock_storage.get_download_url.assert_called_once_with(
            "bucket", "key", expiration=3600,
        )


class TestGcsStorageAdapterListObjects:
    """Verify list_objects delegates to gcloud list_objects and returns FileRefs."""

    @pytest.mark.asyncio
    async def test_list_objects_returns_file_refs(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """list_objects() converts GCS objects to FileRef list."""
        mock_storage.list_objects.return_value = [
            {"name": "photos/cat.jpg", "size": 2048},
            {"name": "photos/dog.jpg", "size": 4096},
        ]

        result = await storage.list_objects("my-bucket", prefix="photos/")

        mock_storage.list_objects.assert_called_once_with("my-bucket", prefix="photos/")
        assert len(result) == 2
        assert all(isinstance(ref, FileRef) for ref in result)
        assert {ref.key for ref in result} == {"photos/cat.jpg", "photos/dog.jpg"}
        assert {ref.bucket for ref in result} == {"my-bucket"}

    @pytest.mark.asyncio
    async def test_list_objects_empty_returns_empty_list(
        self, storage: GcsStorageAdapter, mock_storage: MagicMock,
    ) -> None:
        """list_objects() returns empty list when no objects match."""
        mock_storage.list_objects.return_value = []

        result = await storage.list_objects("my-bucket", prefix="nonexistent/")
        assert result == []
