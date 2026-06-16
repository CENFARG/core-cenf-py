"""Unit tests for LocalStorageAdapter — filesystem-backed FileStorageManager.

Tests cover:
- upload/download roundtrip using tmp_path fixture
- exists returns True after upload
- delete removes file
- list_objects with bucket isolation
- generate_presigned_url returns file:// URL

Security: Tests use tmp_path — no real filesystem pollution.
Observability: Tests verify aiofiles async I/O works correctly.

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.filestorage.adapters.local_storage_adapter import LocalStorageAdapter
from core_infrastructure.filestorage.ports import FileStorageManager
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)


@pytest.fixture
def config(tmp_path) -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with local storage settings."""
    return InMemoryConfigAdapter(
        initial_data={
            "storage": {
                "default_bucket": "default",
                "backend": "local",
                "local_base_path": str(tmp_path / "data" / "storage"),
            },
        }
    )


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """Create an InMemoryLoggerAdapter."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    """Create an InMemoryObservabilityAdapter."""
    return InMemoryObservabilityAdapter()


@pytest.fixture
def error_handler(config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, observability: InMemoryObservabilityAdapter) -> CapturingErrorAdapter:
    """Create a CapturingErrorAdapter."""
    return CapturingErrorAdapter(config, logger, observability)


@pytest.fixture
def storage(config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, observability: InMemoryObservabilityAdapter, error_handler: CapturingErrorAdapter) -> LocalStorageAdapter:
    """Create a LocalStorageAdapter with tmp_path-based storage."""
    return LocalStorageAdapter(config, logger, error_handler)


class TestLocalStorageAdapterProtocol:
    """Verify LocalStorageAdapter satisfies FileStorageManager Protocol."""

    def test_satisfies_file_storage_manager_protocol(self, storage: LocalStorageAdapter) -> None:
        """LocalStorageAdapter passes isinstance check against FileStorageManager."""
        assert isinstance(storage, FileStorageManager)


class TestLocalStorageAdapterUploadDownload:
    """Verify upload/download roundtrip on local filesystem."""

    @pytest.mark.asyncio
    async def test_upload_stores_data(self, storage: LocalStorageAdapter) -> None:
        """upload() stores data and returns UploadResult."""
        data = b"Hello, Local Storage!"
        result = await storage.upload("uploads", "greeting.txt", data, content_type="text/plain")
        assert result.key == "greeting.txt"
        assert result.etag != ""
        assert result.url.startswith("file://")

    @pytest.mark.asyncio
    async def test_download_retrieves_data(self, storage: LocalStorageAdapter) -> None:
        """download() retrieves the exact bytes uploaded."""
        data = b"Binary local data \x00\xff\xfe"
        await storage.upload("downloads", "binary.bin", data)
        downloaded = await storage.download("downloads", "binary.bin")
        assert downloaded == data

    @pytest.mark.asyncio
    async def test_download_nonexistent_raises_validation_error(self, storage: LocalStorageAdapter) -> None:
        """download() raises ValidationError for missing objects."""
        with pytest.raises(ValidationError):
            await storage.download("no-bucket", "no-file.txt")

    @pytest.mark.asyncio
    async def test_exists_returns_true_after_upload(self, storage: LocalStorageAdapter) -> None:
        """exists() returns True after upload."""
        await storage.upload("bucket-z", "exists-test.txt", b"data")
        assert await storage.exists("bucket-z", "exists-test.txt") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing(self, storage: LocalStorageAdapter) -> None:
        """exists() returns False for non-existent objects."""
        assert await storage.exists("bucket-z", "no-such-file.txt") is False

    @pytest.mark.asyncio
    async def test_delete_removes_object(self, storage: LocalStorageAdapter) -> None:
        """delete() removes the file and exists() returns False."""
        await storage.upload("tmp-bucket", "to-delete.txt", b"temp")
        assert await storage.exists("tmp-bucket", "to-delete.txt") is True
        await storage.delete("tmp-bucket", "to-delete.txt")
        assert await storage.exists("tmp-bucket", "to-delete.txt") is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_idempotent(self, storage: LocalStorageAdapter) -> None:
        """delete() on a non-existent object does not raise."""
        await storage.delete("no-bucket", "no-file.txt")  # Should not raise


class TestLocalStorageAdapterListObjects:
    """Verify list_objects behavior on local filesystem."""

    @pytest.mark.asyncio
    async def test_list_objects_returns_uploaded_objects(self, storage: LocalStorageAdapter) -> None:
        """list_objects returns FileRefs for all files in a bucket."""
        await storage.upload("images", "cat.png", b"cat-png-data")
        await storage.upload("images", "dog.png", b"dog-png-data")

        objects = await storage.list_objects("images")
        assert len(objects) == 2
        keys = {obj.key for obj in objects}
        assert keys == {"cat.png", "dog.png"}

    @pytest.mark.asyncio
    async def test_list_objects_empty_bucket_returns_empty_list(self, storage: LocalStorageAdapter) -> None:
        """list_objects returns empty list for a non-existent bucket."""
        objects = await storage.list_objects("nonexistent-bucket")
        assert objects == []

    @pytest.mark.asyncio
    async def test_list_objects_bucket_isolation(self, storage: LocalStorageAdapter) -> None:
        """Files in one bucket do not appear in another bucket."""
        await storage.upload("b1", "shared.txt", b"data-1")
        await storage.upload("b2", "shared.txt", b"data-2")

        b1_objects = await storage.list_objects("b1")
        b2_objects = await storage.list_objects("b2")
        assert len(b1_objects) == 1
        assert len(b2_objects) == 1


class TestLocalStorageAdapterPresignedUrl:
    """Verify generate_presigned_url behavior."""

    @pytest.mark.asyncio
    async def test_generate_presigned_url(self, storage: LocalStorageAdapter) -> None:
        """generate_presigned_url returns a file:// URL."""
        await storage.upload("public", "index.html", b"<html></html>")
        url = await storage.generate_presigned_url("public", "index.html", expiry=120)
        assert url.startswith("file://")
        assert "expiry=120" in url

    @pytest.mark.asyncio
    async def test_generate_presigned_url_nonexistent_raises(self, storage: LocalStorageAdapter) -> None:
        """generate_presigned_url raises ValidationError for missing objects."""
        with pytest.raises(ValidationError):
            await storage.generate_presigned_url("no-bucket", "no-file.txt")
