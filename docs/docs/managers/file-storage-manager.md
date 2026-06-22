---
sidebar_position: 9
---

# FileStorageManager (M09)

Multi-cloud blob storage abstraction for uploading, downloading, deleting, and listing objects. Supports local filesystem (dev) and S3-compatible stores (production) with pre-signed URL generation.

## Protocol

`FileStorageManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.filestorage.ports`.

### `async upload(bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") → UploadResult`

Upload an object to the specified bucket.

```python
async def upload(
    self,
    bucket: str,
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> UploadResult: ...
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `bucket` | `str` | *(required)* | Bucket name (logical container) |
| `key` | `str` | *(required)* | Object key (path within the bucket) |
| `data` | `bytes` | *(required)* | Raw bytes to store |
| `content_type` | `str` | `"application/octet-stream"` | MIME type of the object |

**Returns:** `UploadResult` — metadata about the uploaded object (key, etag, url).

**Raises:**
- `ValidationError` — bucket or key is invalid
- `PermanentError` — write fails (disk full, permission denied)

Overwrites existing objects with the same bucket+key.

---

### `async download(bucket: str, key: str) → bytes`

Download an object's raw bytes.

```python
async def download(self, bucket: str, key: str) -> bytes: ...
```

**Raises:**
- `ValidationError` — object does not exist
- `PermanentError` — read fails

---

### `async delete(bucket: str, key: str) → None`

Delete an object from storage.

```python
async def delete(self, bucket: str, key: str) -> None: ...
```

Idempotent — deleting a non-existent object succeeds silently.

---

### `async exists(bucket: str, key: str) → bool`

Check if an object exists in storage.

```python
async def exists(self, bucket: str, key: str) -> bool: ...
```

**Returns:** `True` if the object exists and is readable.

---

### `async generate_presigned_url(bucket: str, key: str, expiry: int = 3600) → str`

Generate a time-limited URL for external access.

```python
async def generate_presigned_url(
    self,
    bucket: str,
    key: str,
    expiry: int = 3600,
) -> str: ...
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `bucket` | `str` | *(required)* | Bucket name |
| `key` | `str` | *(required)* | Object key |
| `expiry` | `int` | `3600` (1 hour) | URL validity duration in seconds |

**Raises:** `ValidationError` if the object does not exist.

**Security:** The returned URL grants access to the object — never log it at INFO or above. For local storage, returns a `file://` URL. For S3, generates an actual pre-signed URL.

---

### `async list_objects(bucket: str, prefix: str = "") → list[FileRef]`

List objects in a bucket with an optional prefix filter.

```python
async def list_objects(self, bucket: str, prefix: str = "") -> list[FileRef]: ...
```

**Returns:** List of `FileRef` objects (empty if none match).

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing `StorageConfig`.

## Models

### `FileRef`

**File:** `core_infrastructure.filestorage.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `bucket` | `str` (1–256) | *(required)* | Bucket name |
| `key` | `str` (1–1024) | *(required)* | Object key |
| `size` | `int` (≥0) | `0` | Object size in bytes |
| `content_type` | `str` (max 256) | `"application/octet-stream"` | MIME type |
| `checksum` | `str` (max 128) | `""` | SHA-256 hex digest for integrity verification |

---

### `UploadResult`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key` | `str` (1–1024) | *(required)* | Uploaded object key |
| `etag` | `str` (max 256) | `""` | Entity tag (etag) |
| `url` | `str` (max 2048) | `""` | Access URL or local path |

---

### `StorageConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_bucket` | `str` (1–256) | `"default"` | Default bucket name |
| `backend` | `Literal["local","s3"]` | `"local"` | Storage backend |
| `local_base_path` | `str` (max 1024) | `"./data/storage"` | Local filesystem base path |

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `LocalStorageAdapter` | Local filesystem | Dev — files stored under `local_base_path/bucket/key` |
| `MemoryStorageAdapter` | Python dict | Testing — in-memory, no disk I/O |
| `S3StorageAdapter` | AWS S3 (aiobotocore) | Production — S3-compatible object storage |
| `GcsStorageAdapter` | Google Cloud Storage (gcloud-aio) | Production — GCS buckets |
| `AzureStorageAdapter` | Azure Blob Storage | Production — Azure containers |

**Bucket name rules:** Alphanumeric + hyphens only, max 256 characters.

## Usage Example

```python
from core_infrastructure.filestorage.adapters.local_storage_adapter import LocalStorageAdapter

# Bootstrap
storage = LocalStorageAdapter(config_manager=config, logger_manager=logger)

# Upload
pdf_data = b"%PDF-1.4 ..."
result = await storage.upload(
    bucket="documents",
    key="reports/2024/annual.pdf",
    data=pdf_data,
    content_type="application/pdf",
)
# → UploadResult(key="reports/2024/annual.pdf", etag="abc123", url="file://...")

# Download
downloaded = await storage.download("documents", "reports/2024/annual.pdf")
# → b"%PDF-1.4 ..."

# Check existence
exists = await storage.exists("documents", "reports/2024/annual.pdf")
# → True

# Generate pre-signed URL (1 hour expiry)
url = await storage.generate_presigned_url(
    bucket="documents",
    key="reports/2024/annual.pdf",
    expiry=3600,
)
# → "file:///data/storage/documents/reports/2024/annual.pdf" (local)
# → "https://s3.amazonaws.com/..." (S3)

# List objects with prefix
objects = await storage.list_objects("documents", prefix="reports/2024/")
# → [FileRef(key="reports/2024/annual.pdf", size=1048576, ...), ...]

# Delete (idempotent)
await storage.delete("documents", "reports/2024/annual.pdf")
await storage.delete("documents", "nonexistent")  # no-op

# LLM agent discovery
schema = storage.get_json_schema()
```

### Multi-Cloud Example

```python
# S3 adapter
from core_infrastructure.filestorage.adapters.s3_storage_adapter import S3StorageAdapter

storage = S3StorageAdapter(config_manager=config, logger_manager=logger)

result = await storage.upload(
    bucket="cenf-uploads",
    key="avatars/user-42.jpg",
    data=image_bytes,
    content_type="image/jpeg",
)

# Generate S3 pre-signed URL
public_url = await storage.generate_presigned_url(
    "cenf-uploads", "avatars/user-42.jpg", expiry=600  # 10 min
)
```

## @ai-directive

- **Never infer MIME type from file extension.** Always pass `content_type` explicitly — extensions are unreliable and can be spoofed.
- Pre-signed URLs MUST have configurable expiry and MUST NOT be logged at INFO or above.
- File contents MUST NOT be logged.
- All methods are async because they involve file I/O or network requests.
- `upload()` accepts `bytes` (not `str`) for data to avoid encoding ambiguity.
- `StorageConfig.local_base_path` defaults to `./data/storage`. Change this in production to an absolute path outside the code tree.

## Related

- [ConfigManager](config-manager.md) — reads `StorageConfig` section
- [LoggerManager](logger-manager.md) — DEBUG-level operation logging (never logs file contents)
- [ObservabilityManager](observability-manager.md) — byte counters and operation duration histograms
- [SecretManager](secret-manager.md) — retrieves cloud credentials
