"""CENF FileStorageManager models — FileRef, UploadResult, StorageConfig.

Defines the Pydantic models for FileStorageManager data transfer and
configuration. FileRef represents an object reference; UploadResult
encapsulates the result of an upload; StorageConfig controls backend
selection and local base path.

Security: pre-signed URLs must have limited expiry. FileRef.checksum
    enables integrity verification on download.
Observability: Upload/download/list operations emit byte counters via
    ObservabilityManager.
@ai-directive: StorageConfig.local_base_path defaults to ``./data/storage``.
    Change this in production to an absolute path outside the code tree.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FileRef(BaseModel):
    """Reference to an object in a storage bucket.

    Represents metadata about a stored object — not the object data itself.

    Attributes:
        bucket: Logical bucket name (directory or S3 bucket).
        key: Object key (path within the bucket).
        size: Object size in bytes.
        content_type: MIME type of the object.
        checksum: SHA-256 hex digest for integrity verification.
    """

    bucket: str = Field(..., min_length=1, max_length=256, description="Bucket name.")
    key: str = Field(..., min_length=1, max_length=1024, description="Object key.")
    size: int = Field(default=0, ge=0, description="Object size in bytes.")
    content_type: str = Field(default="application/octet-stream", max_length=256, description="MIME type.")
    checksum: str = Field(default="", max_length=128, description="SHA-256 hex digest.")


class UploadResult(BaseModel):
    """Result of a successful upload operation.

    Contains the key, entity tag (etag), and a URL where the object
    can be accessed (which may be a pre-signed URL or a local path).

    Attributes:
        key: The object key that was uploaded.
        etag: Entity tag for the uploaded object.
        url: URL or path where the object can be accessed.
    """

    key: str = Field(..., min_length=1, max_length=1024, description="Uploaded object key.")
    etag: str = Field(default="", max_length=256, description="Entity tag (etag).")
    url: str = Field(default="", max_length=2048, description="Access URL or local path.")


class StorageConfig(BaseModel):
    """Configuration for FileStorageManager adapters.

    Controls the default bucket, backend selection, and local filesystem
    base path when the backend is ``"local"``.

    Attributes:
        default_bucket: Default bucket name for operations without explicit bucket.
        backend: Storage backend — ``"local"`` (filesystem) or ``"s3"``.
        local_base_path: Base directory for local filesystem storage.
    """

    default_bucket: str = Field(default="default", min_length=1, max_length=256, description="Default bucket name.")
    backend: Literal["local", "s3"] = Field(default="local", description="Storage backend.")
    local_base_path: str = Field(default="./data/storage", max_length=1024, description="Local filesystem base path.")
