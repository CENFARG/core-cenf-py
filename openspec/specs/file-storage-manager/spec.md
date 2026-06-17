---
Spec_ID: SPEC_M09
Title: FileStorageManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [file-storage, multi-cloud, s3, gcs, azure]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M09: FileStorageManager

## Purpose

Provide async blob storage with multi-cloud support (Local, S3, GCS, Azure). Includes pre-signed URL generation, streaming upload/download, and bucket-scoped operations.

**Does NOT**: Infer MIME types by file extension, couple the Protocol to a specific cloud provider.

## Python Protocol

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable

from core_infrastructure.filestorage.models import FileRef, UploadResult

@runtime_checkable
class FileStorageManager(Protocol):
    """@ai-directive: All methods are async. upload() accepts bytes, not str."""

    async def upload(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> UploadResult:
        """Upload an object. Overwrites existing objects with same bucket+key."""
        ...

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object's raw bytes."""
        ...

    async def delete(self, bucket: str, key: str) -> None:
        """Delete an object. Idempotent."""
        ...

    async def exists(self, bucket: str, key: str) -> bool:
        """Check if an object exists and is readable."""
        ...

    async def generate_presigned_url(self, bucket: str, key: str, expiry: int = 3600) -> str:
        """Generate a time-limited URL for external access."""
        ...

    async def list_objects(self, bucket: str, prefix: str = "") -> list[FileRef]:
        """List objects with optional prefix filter."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class FileStorageSettings(BaseModel):
    backend: Literal["local", "s3", "gcs", "azure"] = Field(default="local")
    local_root: str | None = Field(default=None)
    s3_bucket: str | None = Field(default=None, min_length=3, max_length=63)
    s3_region: str | None = Field(default="us-east-1")
    gcs_bucket: str | None = Field(default=None)
    azure_container: str | None = Field(default=None)
    max_file_size_bytes: int = Field(default=104857600, ge=1048576)
    presigned_url_default_hours: int = Field(default=1, ge=1, le=168)

class UploadResult(BaseModel):
    key: str
    etag: str
    url: str
    content_type: str
    size_bytes: int

class FileRef(BaseModel):
    key: str
    size_bytes: int
    content_type: str
    last_modified: str
```

## Gherkin Scenarios

### Scenario: Upload and download roundtrip

- GIVEN a bucket "documents" exists
- WHEN `upload(bucket="documents", key="report.pdf", data=b"...")` is called
- THEN it returns `UploadResult` with key, etag, url
- AND `download(bucket="documents", key="report.pdf")` returns the same bytes

### Scenario: Delete is idempotent

- GIVEN an object does not exist
- WHEN `delete(bucket="docs", key="missing.pdf")` is called
- THEN it succeeds silently (no exception)

### Scenario: Pre-signed URL expiry

- GIVEN an object exists in S3
- WHEN `generate_presigned_url(bucket="docs", key="file.pdf", expiry=3600)` is called
- THEN a valid pre-signed URL is returned
- AND the URL expires after 3600 seconds
- AND the URL is NOT logged at INFO level or above

### Scenario: List objects with prefix

- GIVEN bucket "docs" contains keys: "a/1.txt", "a/2.txt", "b/3.txt"
- WHEN `list_objects(bucket="docs", prefix="a/")` is called
- THEN it returns `[FileRef("a/1.txt"), FileRef("a/2.txt")]`

### Scenario: File size limit enforced

- GIVEN max_file_size_bytes = 10MB
- WHEN `upload()` is called with 15MB of data
- THEN it raises `ValidationError` (file too large)

### Scenario: Local backend presigned URL

- GIVEN backend is "local"
- WHEN `generate_presigned_url()` is called
- THEN it returns a `file://` URL (not a cloud pre-signed URL)

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Object not found (download) | VALIDATION | Re-raise immediately |
| Network error, S3 throttling | TRANSIENT | Retry with backoff |
| Invalid bucket, expired credentials | PERMANENT | Fail bootstrap |
| Pre-signed URL on local backend | PERMANENT | Return file:// URL (not NotImplementedError) |

## RED Metrics

- `cenf.filestorage.upload_total` (counter)
- `cenf.filestorage.download_total` (counter)
- `cenf.filestorage.errors_total` (counter)
- `cenf.filestorage.operation_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryFileStorageAdapter` — dict of bytes.
- **Integration**: `S3Adapter` with moto mock.
- **E2E**: Streaming 100MB file, verify bounded memory.

## Do's and Don'ts

**Do**:
- Support multi-cloud: local, S3, GCS, Azure via separate adapters
- Use pre-signed URLs with configurable expiry (default 3600s)
- Stream using AsyncIterator[bytes] to bound memory
- Parametrize buckets/containers via configuration

**Don't**:
- Infer MIME types by file extension
- Couple the Protocol to a specific cloud provider
- Log file contents or pre-signed URLs at INFO or above
