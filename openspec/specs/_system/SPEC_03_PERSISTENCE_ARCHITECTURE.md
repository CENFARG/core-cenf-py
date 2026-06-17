---
Spec_ID: SPEC_03
Title: Persistence Architecture
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [database, cache, file-storage, persistence]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_03: Persistence Architecture

## Purpose

Define the database, cache, and file storage architecture including DDL schemas, connection pooling, stampede mitigation, and multi-cloud support.

## Database Architecture

### Technology Stack

| Component | Library | License | Purpose |
|-----------|---------|---------|---------|
| ORM/Query Builder | SQLAlchemy 2.0+ (asyncio) | MIT | Async engine, session management |
| Driver | asyncpg | Apache 2.0 | PostgreSQL async driver (no psycopg3/LGPL) |
| Migrations | Alembic | MIT | Schema versioning |

### TransactionScope Contract

```python
@runtime_checkable
class TransactionScope(Protocol):
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

**Rules:**
- `commit()` applies all pending operations atomically
- `rollback()` discards all pending changes — idempotent
- Both are safe to call multiple times

### GenericRepository Contract

```python
@runtime_checkable
class GenericRepository[T](Protocol):
    async def find_by_id(self, id: Any) -> T | None: ...
    async def find_all(self, filters: dict, order_by: str | None, limit: int, offset: int) -> list[T]: ...
    async def insert(self, entity: T) -> T: ...
    async def update(self, entity: T) -> T: ...
    async def delete(self, id: Any) -> None: ...
    async def count(self, filters: dict | None) -> int: ...
```

#### Scenario: Transaction rollback

- GIVEN a transaction scope with a pending insert
- WHEN `rollback()` is called
- THEN the insert is discarded
- AND `find_by_id()` returns None for the would-be-inserted entity

### DatabaseSettings (Pydantic V2)

```python
class DatabaseSettings(BaseModel):
    url: str = Field(min_length=1)
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=20, ge=0, le=100)
    pool_timeout: int = Field(default=30, ge=1, le=120)
    pool_recycle: int = Field(default=3600, ge=300)
    pool_pre_ping: bool = Field(default=True)
    echo: bool = Field(default=False)
```

### DDL Schema Requirements

- All tables MUST have `id` (UUID), `created_at` (UTC timestamp), `updated_at` (UTC timestamp)
- Multi-tenant tables MUST have `tenant_id` (VARCHAR(64), indexed)
- All foreign keys MUST have `ON DELETE CASCADE` or `ON DELETE SET NULL`
- Indexes on frequently queried columns (tenant_id, status, created_at)

## Cache Architecture

### Technology Stack

| Component | Library | License | Purpose |
|-----------|---------|---------|---------|
| Redis Client | redis-py (asyncio) | MIT | Direct async Redis operations |
| No aiocache | — | — | No intermediate facade — core-cenf IS the abstraction |

### Stampede Mitigation (XFetch Algorithm)

The system SHALL implement Probabilistic Early Expiration to prevent thundering herd on hot keys:

1. When a key is within `stampede_probability` of its TTL expiry window
2. Probabilistically trigger early recompute
3. Return stale value while recomputing in background
4. Emit `cenf.cache.stampede_recompute_total` counter

#### Scenario: Stampede prevention

- GIVEN 100 concurrent calls to `get_or_set("hot-key", factory, ttl=60)`
- WHEN the key is near expiry (55 seconds elapsed)
- THEN only ONE call invokes the factory
- AND 99 calls return the cached (possibly stale) value
- AND `cenf.cache.stampede_recompute_total` increments by 1

### CacheSettings (Pydantic V2)

```python
class CacheSettings(BaseModel):
    backend: Literal["memory", "redis"] = Field(default="memory")
    redis_url: str | None = Field(default=None)
    default_ttl_seconds: int = Field(default=300, ge=1, le=86400)
    max_key_length: int = Field(default=256, ge=32)
    max_value_size_bytes: int = Field(default=1048576, ge=1024)
    stampede_probability: float = Field(default=0.1, ge=0.0, le=1.0)
    namespace: str = Field(min_length=1, max_length=64, default="cenf")
```

## File Storage Architecture

### Multi-Cloud Support

| Backend | Library | License | Adapter |
|---------|---------|---------|---------|
| Local | aiofiles | Apache 2.0 | `local_storage_adapter` |
| AWS S3 | aiobotocore | Apache 2.0 | `s3_storage_adapter` |
| Google Cloud | gcloud-aio-storage | Apache 2.0 | `gcs_storage_adapter` |
| Azure Blob | azure-storage-blob | MIT | `azure_storage_adapter` |

### FileStorageSettings (Pydantic V2)

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
```

#### Scenario: Pre-signed URL expiry

- GIVEN an object uploaded to S3 bucket "documents" with key "report.pdf"
- WHEN `generate_presigned_url(bucket="documents", key="report.pdf", expiry=3600)` is called
- THEN a valid pre-signed URL is returned
- AND the URL expires after 3600 seconds
- AND the URL is NOT logged at INFO level or above

### Boundary Validation

- Bucket names: alphanumeric + hyphens, 3-63 chars (S3), 1-256 chars (local)
- Object keys: non-empty, URL-safe characters
- Content types: validated against IANA MIME registry
- File size: enforced by `max_file_size_bytes`
