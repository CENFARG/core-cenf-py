"""Unit tests for FileStorageManager Protocol and Pydantic models.

Tests cover:
- FileStorageManager Protocol contract (upload, download, delete, exists,
  generate_presigned_url, list_objects)
- Protocol is runtime-checkable
- FileRef, UploadResult, StorageConfig model validation

Author: CENF AI Team
Version: 0.1.0
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.filestorage.models import FileRef, StorageConfig, UploadResult
from core_infrastructure.filestorage.ports import FileStorageManager


class TestFileStorageManagerProtocol:
    """Verify FileStorageManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """FileStorageManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(FileStorageManager, "_is_runtime_protocol") or hasattr(
            FileStorageManager, "__protocol_attrs__"
        )

    def test_has_upload_method(self) -> None:
        """Protocol requires upload(bucket, key, data, content_type)."""
        assert hasattr(FileStorageManager, "upload")

    def test_has_download_method(self) -> None:
        """Protocol requires download(bucket, key) -> bytes."""
        assert hasattr(FileStorageManager, "download")

    def test_has_delete_method(self) -> None:
        """Protocol requires delete(bucket, key)."""
        assert hasattr(FileStorageManager, "delete")

    def test_has_exists_method(self) -> None:
        """Protocol requires exists(bucket, key) -> bool."""
        assert hasattr(FileStorageManager, "exists")

    def test_has_generate_presigned_url_method(self) -> None:
        """Protocol requires generate_presigned_url(bucket, key, expiry)."""
        assert hasattr(FileStorageManager, "generate_presigned_url")

    def test_has_list_objects_method(self) -> None:
        """Protocol requires list_objects(bucket, prefix) -> list[FileRef]."""
        assert hasattr(FileStorageManager, "list_objects")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all FileStorageManager methods satisfies the protocol."""

        class ValidStorage:
            async def upload(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream"): ...
            async def download(self, bucket: str, key: str) -> bytes: ...
            async def delete(self, bucket: str, key: str) -> None: ...
            async def exists(self, bucket: str, key: str) -> bool: ...
            async def generate_presigned_url(self, bucket: str, key: str, expiry: int = 3600) -> str: ...
            async def list_objects(self, bucket: str, prefix: str = "") -> list: ...

        assert isinstance(ValidStorage(), FileStorageManager)

    def test_class_missing_upload_fails_protocol(self) -> None:
        """A class without upload() does NOT satisfy FileStorageManager."""

        class Incomplete:
            async def download(self, bucket: str, key: str) -> bytes: ...

        assert not isinstance(Incomplete(), FileStorageManager)


class TestFileRefModel:
    """Verify FileRef Pydantic model validation."""

    def test_file_ref_creation(self) -> None:
        """FileRef can be constructed with all fields."""
        ref = FileRef(
            bucket="my-bucket",
            key="path/to/file.txt",
            size=1024,
            content_type="text/plain",
            checksum="abc123",
        )
        assert ref.bucket == "my-bucket"
        assert ref.key == "path/to/file.txt"
        assert ref.size == 1024
        assert ref.content_type == "text/plain"
        assert ref.checksum == "abc123"

    def test_file_ref_defaults(self) -> None:
        """FileRef has sensible defaults for optional fields."""
        ref = FileRef(bucket="b", key="k")
        assert ref.size == 0
        assert ref.content_type == "application/octet-stream"
        assert ref.checksum == ""

    def test_empty_bucket_fails(self) -> None:
        """bucket must not be empty."""
        with pytest.raises(PydanticValidationError):
            FileRef(bucket="", key="k")

    def test_empty_key_fails(self) -> None:
        """key must not be empty."""
        with pytest.raises(PydanticValidationError):
            FileRef(bucket="b", key="")


class TestUploadResultModel:
    """Verify UploadResult Pydantic model."""

    def test_upload_result_creation(self) -> None:
        """UploadResult can be constructed with all fields."""
        result = UploadResult(key="uploads/file.txt", etag="abc123", url="https://example.com/file.txt")
        assert result.key == "uploads/file.txt"
        assert result.etag == "abc123"
        assert result.url == "https://example.com/file.txt"

    def test_upload_result_defaults(self) -> None:
        """UploadResult has sensible defaults."""
        result = UploadResult(key="k")
        assert result.etag == ""
        assert result.url == ""


class TestStorageConfigModel:
    """Verify StorageConfig Pydantic model validation."""

    def test_default_config(self) -> None:
        """StorageConfig creates with sensible defaults."""
        config = StorageConfig()
        assert config.default_bucket == "default"
        assert config.backend == "local"
        assert config.local_base_path == "./data/storage"

    def test_custom_config(self) -> None:
        """StorageConfig accepts custom values."""
        config = StorageConfig(
            default_bucket="uploads",
            backend="s3",
            local_base_path="/tmp/files",
        )
        assert config.default_bucket == "uploads"
        assert config.backend == "s3"
        assert config.local_base_path == "/tmp/files"

    def test_invalid_backend_fails(self) -> None:
        """backend must be 'local' or 's3'."""
        with pytest.raises(PydanticValidationError):
            StorageConfig(backend="gcs")  # type: ignore[arg-type]

    def test_empty_default_bucket_fails(self) -> None:
        """default_bucket must not be empty."""
        with pytest.raises(PydanticValidationError):
            StorageConfig(default_bucket="")
