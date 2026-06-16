"""Unit tests for MemoryStorageAdapter — in-memory dict-backed FileStorageManager.

Tests cover:
- Protocol compliance (satisfies FileStorageManager)
- upload/download roundtrip
- exists returns True after upload, False for missing
- delete removes object
- list_objects with and without prefix
- generate_presigned_url
- Bucket isolation

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
from core_infrastructure.filestorage.ports import FileStorageManager


@pytest.fixture
def storage() -> MemoryStorageAdapter:
    """Create a fresh MemoryStorageAdapter."""
    return MemoryStorageAdapter()


class TestMemoryStorageAdapterProtocol:
    """Verify MemoryStorageAdapter satisfies FileStorageManager Protocol."""

    def test_satisfies_file_storage_manager_protocol(self, storage: MemoryStorageAdapter) -> None:
        """MemoryStorageAdapter passes isinstance check against FileStorageManager."""
        assert isinstance(storage, FileStorageManager)


class TestMemoryStorageAdapterUploadDownload:
    """Verify upload/download roundtrip."""

    @pytest.mark.asyncio
    async def test_upload_stores_data(self, storage: MemoryStorageAdapter) -> None:
        """upload() stores data and returns UploadResult."""
        data = b"Hello, World!"
        result = await storage.upload("my-bucket", "hello.txt", data, content_type="text/plain")
        assert result.key == "hello.txt"
        assert result.etag != ""
        assert "memory://" in result.url

    @pytest.mark.asyncio
    async def test_download_retrieves_data(self, storage: MemoryStorageAdapter) -> None:
        """download() retrieves the exact bytes uploaded."""
        data = b"Binary data \x00\x01\x02"
        await storage.upload("my-bucket", "binary.bin", data)
        downloaded = await storage.download("my-bucket", "binary.bin")
        assert downloaded == data

    @pytest.mark.asyncio
    async def test_download_nonexistent_raises_validation_error(self, storage: MemoryStorageAdapter) -> None:
        """download() raises ValidationError for missing objects."""
        with pytest.raises(ValidationError):
            await storage.download("no-bucket", "no-key")

    @pytest.mark.asyncio
    async def test_exists_returns_true_after_upload(self, storage: MemoryStorageAdapter) -> None:
        """exists() returns True after upload."""
        await storage.upload("bucket-a", "file.txt", b"data")
        assert await storage.exists("bucket-a", "file.txt") is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_for_missing(self, storage: MemoryStorageAdapter) -> None:
        """exists() returns False for non-existent objects."""
        assert await storage.exists("bucket-a", "nonexistent.txt") is False

    @pytest.mark.asyncio
    async def test_delete_removes_object(self, storage: MemoryStorageAdapter) -> None:
        """delete() removes the object and exists() returns False."""
        await storage.upload("bucket-b", "temp.txt", b"temp")
        assert await storage.exists("bucket-b", "temp.txt") is True
        await storage.delete("bucket-b", "temp.txt")
        assert await storage.exists("bucket-b", "temp.txt") is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_is_idempotent(self, storage: MemoryStorageAdapter) -> None:
        """delete() on a non-existent object does not raise."""
        await storage.delete("no-bucket", "no-key")  # Should not raise


class TestMemoryStorageAdapterListObjects:
    """Verify list_objects behavior."""

    @pytest.mark.asyncio
    async def test_list_objects_returns_uploaded_objects(self, storage: MemoryStorageAdapter) -> None:
        """list_objects returns FileRefs for all objects in a bucket."""
        await storage.upload("photos", "cat.jpg", b"cat-data")
        await storage.upload("photos", "dog.jpg", b"dog-data")

        objects = await storage.list_objects("photos")
        assert len(objects) == 2
        keys = {obj.key for obj in objects}
        assert keys == {"cat.jpg", "dog.jpg"}

    @pytest.mark.asyncio
    async def test_list_objects_empty_bucket_returns_empty_list(self, storage: MemoryStorageAdapter) -> None:
        """list_objects returns empty list for an empty bucket."""
        objects = await storage.list_objects("empty-bucket")
        assert objects == []

    @pytest.mark.asyncio
    async def test_list_objects_with_prefix(self, storage: MemoryStorageAdapter) -> None:
        """list_objects with prefix filters results."""
        await storage.upload("docs", "reports/2024/q1.pdf", b"pdf-data")
        await storage.upload("docs", "reports/2024/q2.pdf", b"pdf-data")
        await storage.upload("docs", "images/logo.png", b"png-data")

        reports = await storage.list_objects("docs", prefix="reports/")
        assert len(reports) == 2
        for ref in reports:
            assert ref.key.startswith("reports/")

    @pytest.mark.asyncio
    async def test_list_objects_bucket_isolation(self, storage: MemoryStorageAdapter) -> None:
        """Objects in one bucket do not appear in another bucket."""
        await storage.upload("bucket-1", "shared-key.txt", b"data-1")
        await storage.upload("bucket-2", "shared-key.txt", b"data-2")

        b1_objects = await storage.list_objects("bucket-1")
        b2_objects = await storage.list_objects("bucket-2")
        assert len(b1_objects) == 1
        assert len(b2_objects) == 1


class TestMemoryStorageAdapterPresignedUrl:
    """Verify generate_presigned_url behavior."""

    @pytest.mark.asyncio
    async def test_generate_presigned_url(self, storage: MemoryStorageAdapter) -> None:
        """generate_presigned_url returns a URL for an existing object."""
        await storage.upload("public", "index.html", b"<html></html>")
        url = await storage.generate_presigned_url("public", "index.html", expiry=600)
        assert "memory://" in url
        assert "expiry=600" in url

    @pytest.mark.asyncio
    async def test_generate_presigned_url_nonexistent_raises(self, storage: MemoryStorageAdapter) -> None:
        """generate_presigned_url raises ValidationError for missing objects."""
        with pytest.raises(ValidationError):
            await storage.generate_presigned_url("no-bucket", "no-key")
