"""Unit tests for S3StorageAdapter — AWS S3 FileStorageManager using aiobotocore.

Tests cover:
- Protocol compliance check
- Mock aiobotocore session to verify method calls
- Test pre-signed URL generation with correct params
- Test error wrapping

Security: Tests use mock aiobotocore — no real AWS credentials required.
Observability: Tests verify adapter method signatures and error paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from core_infrastructure.common.errors import TransientError
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.filestorage.adapters.s3_storage_adapter import S3StorageAdapter
from core_infrastructure.filestorage.models import FileRef
from core_infrastructure.filestorage.ports import FileStorageManager
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with S3 settings."""
    return InMemoryConfigAdapter(
        initial_data={
            "filestorage": {
                "s3": {
                    "bucket": "my-s3-bucket",
                    "region": "us-east-1",
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
def mock_client() -> MagicMock:
    """Create a mock aiobotocore client with async methods and context manager support."""
    client = MagicMock()
    client.put_object = AsyncMock()
    client.get_object = AsyncMock()
    client.delete_object = AsyncMock()
    client.head_object = AsyncMock()
    client.list_objects_v2 = AsyncMock()
    client.generate_presigned_url = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_session(mock_client: MagicMock) -> MagicMock:
    """Create a mock aiobotocore session."""
    session = MagicMock()
    session.create_client = AsyncMock(return_value=mock_client)
    return session


@pytest.fixture
def storage(
    config: InMemoryConfigAdapter,
    secret_manager: InMemorySecretAdapter,
    logger: InMemoryLoggerAdapter,
    error_handler: CapturingErrorAdapter,
    mock_session: MagicMock,
) -> S3StorageAdapter:
    """Create an S3StorageAdapter with mocked aiobotocore session."""
    with patch(
        "core_infrastructure.filestorage.adapters.s3_storage_adapter.AioSession",
        return_value=mock_session,
    ):
        return S3StorageAdapter(config, secret_manager, logger, error_handler)


class TestS3StorageAdapterProtocol:
    """Verify S3StorageAdapter satisfies FileStorageManager Protocol."""

    def test_satisfies_file_storage_manager_protocol(self, storage: S3StorageAdapter) -> None:
        """S3StorageAdapter passes isinstance check against FileStorageManager."""
        assert isinstance(storage, FileStorageManager)


class TestS3StorageAdapterUpload:
    """Verify upload delegates to aiobotocore client.put_object."""

    @pytest.mark.asyncio
    async def test_upload_calls_put_object_with_correct_params(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """upload() calls client.put_object with Bucket, Key, Body, ContentType."""
        mock_client.put_object.return_value = {"ETag": '"abc123"', "Location": "https://s3.amazonaws.com/bucket/key"}

        result = await storage.upload("my-bucket", "data/file.txt", b"hello", content_type="text/plain")

        mock_client.put_object.assert_called_once_with(
            Bucket="my-bucket", Key="data/file.txt", Body=b"hello", ContentType="text/plain",
        )
        assert result.key == "data/file.txt"
        assert result.etag == "abc123"

    @pytest.mark.asyncio
    async def test_upload_wraps_exception_as_transient_error(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """upload() wraps aiobotocore exception into TransientError."""
        mock_client.put_object.side_effect = Exception("S3 connection error")

        with pytest.raises(TransientError, match="S3 upload failed"):
            await storage.upload("bucket", "key.txt", b"data")


class TestS3StorageAdapterDownload:
    """Verify download delegates to aiobotocore client.get_object."""

    @pytest.mark.asyncio
    async def test_download_calls_get_object_and_returns_bytes(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """download() calls client.get_object and reads Body."""
        mock_body = AsyncMock()
        mock_body.read = AsyncMock(return_value=b"downloaded content")
        mock_client.get_object.return_value = {"Body": mock_body}

        data = await storage.download("my-bucket", "data/file.bin")

        mock_client.get_object.assert_called_once_with(Bucket="my-bucket", Key="data/file.bin")
        assert data == b"downloaded content"

    @pytest.mark.asyncio
    async def test_download_wraps_exception_as_transient_error(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """download() wraps aiobotocore exception into TransientError."""
        mock_client.get_object.side_effect = Exception("S3 timeout")

        with pytest.raises(TransientError, match="S3 download failed"):
            await storage.download("bucket", "key.txt")


class TestS3StorageAdapterDelete:
    """Verify delete delegates to aiobotocore client.delete_object."""

    @pytest.mark.asyncio
    async def test_delete_calls_delete_object(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """delete() calls client.delete_object with Bucket and Key."""
        await storage.delete("my-bucket", "key.txt")
        mock_client.delete_object.assert_called_once_with(Bucket="my-bucket", Key="key.txt")

    @pytest.mark.asyncio
    async def test_delete_is_idempotent_on_exception(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """delete() does not raise for non-existent object."""
        mock_client.delete_object.side_effect = Exception("NoSuchKey")
        await storage.delete("my-bucket", "no-such-key.txt")  # Should not raise


class TestS3StorageAdapterExists:
    """Verify exists uses head_object."""

    @pytest.mark.asyncio
    async def test_exists_returns_true_on_200(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """exists() returns True when head_object succeeds (HTTP 200)."""
        mock_client.head_object.return_value = {"ContentLength": 1024}

        result = await storage.exists("my-bucket", "data/file.txt")
        assert result is True
        mock_client.head_object.assert_called_once_with(Bucket="my-bucket", Key="data/file.txt")

    @pytest.mark.asyncio
    async def test_exists_returns_false_on_404(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """exists() returns False when head_object raises 404-like error."""
        from botocore.exceptions import ClientError

        mock_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )

        result = await storage.exists("my-bucket", "data/missing.txt")
        assert result is False


class TestS3StorageAdapterGeneratePresignedUrl:
    """Verify generate_presigned_url with aiobotocore client."""

    @pytest.mark.asyncio
    async def test_generate_presigned_url_with_correct_params(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """generate_presigned_url() calls client.generate_presigned_url with correct params."""
        mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/bucket/key?signature=xyz"

        url = await storage.generate_presigned_url("my-bucket", "data/file.txt", expiry=600)

        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "data/file.txt"},
            ExpiresIn=600,
        )
        assert url == "https://s3.amazonaws.com/bucket/key?signature=xyz"

    @pytest.mark.asyncio
    async def test_generate_presigned_url_default_expiry(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """generate_presigned_url() defaults expiry to 3600 seconds."""
        mock_client.generate_presigned_url.return_value = "https://example.com/url"

        await storage.generate_presigned_url("bucket", "key")

        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "bucket", "Key": "key"},
            ExpiresIn=3600,
        )


class TestS3StorageAdapterListObjects:
    """Verify list_objects uses list_objects_v2."""

    @pytest.mark.asyncio
    async def test_list_objects_returns_file_refs(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """list_objects() converts S3 Contents to FileRef list."""
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "photos/cat.jpg", "Size": 2048, "ETag": '"etag1"'},
                {"Key": "photos/dog.jpg", "Size": 4096, "ETag": '"etag2"'},
            ],
        }

        result = await storage.list_objects("my-bucket", prefix="photos/")

        mock_client.list_objects_v2.assert_called_once_with(Bucket="my-bucket", Prefix="photos/")
        assert len(result) == 2
        assert all(isinstance(ref, FileRef) for ref in result)
        assert {ref.key for ref in result} == {"photos/cat.jpg", "photos/dog.jpg"}
        assert {ref.bucket for ref in result} == {"my-bucket"}

    @pytest.mark.asyncio
    async def test_list_objects_empty_returns_empty_list(
        self, storage: S3StorageAdapter, mock_client: MagicMock,
    ) -> None:
        """list_objects() returns empty list when no Contents key."""
        mock_client.list_objects_v2.return_value = {}

        result = await storage.list_objects("my-bucket", prefix="nonexistent/")
        assert result == []
