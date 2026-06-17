---
Spec_ID: SPEC_M08
Title: DatabaseManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [database, sqlalchemy, asyncpg, alembic, transactions]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M08: DatabaseManager

## Purpose

Provide transactional database access with SQLAlchemy 2.0+ asyncpg and Alembic migrations. Includes GenericRepository pattern with full CRUD and TransactionScope for atomic operations.

**Does NOT**: Expose raw SQLAlchemy sessions to domain, accept dynamic SQL from domain, use psycopg3 (LGPL prohibited).

## Python Protocol

```python
from __future__ import annotations
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")

@runtime_checkable
class TransactionScope(Protocol):
    async def commit(self) -> None:
        """Apply all pending operations atomically. Idempotent."""
        ...

    async def rollback(self) -> None:
        """Discard all pending operations. Idempotent."""
        ...

@runtime_checkable
class GenericRepository(Protocol[T]):
    async def find_by_id(self, id: Any) -> T | None: ...
    async def find_all(self, filters: dict[str, Any] | None = None, order_by: str | None = None, limit: int = 100, offset: int = 0) -> list[T]: ...
    async def insert(self, entity: T) -> T: ...
    async def update(self, entity: T) -> T: ...
    async def delete(self, id: Any) -> None: ...
    async def count(self, filters: dict[str, Any] | None = None) -> int: ...

@runtime_checkable
class DatabaseManager(Protocol):
    """@ai-directive: Always use transaction() for write operations. Never expose raw sessions."""

    def transaction(self) -> AbstractAsyncContextManager[TransactionScope]:
        """Begin a new transaction scope."""
        ...

    def get_repository(self, entity_type: type[T]) -> GenericRepository[T]:
        """Get a typed repository for the given entity type."""
        ...
```

## Boundary Validation (Pydantic V2)

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

## Gherkin Scenarios

### Scenario: Transaction commit

- GIVEN a transaction scope is opened
- WHEN a repository inserts an entity within the scope
- AND `commit()` is called
- THEN the entity is persisted
- AND the transaction scope is closed

### Scenario: Transaction rollback

- GIVEN a transaction scope is opened with a pending insert
- WHEN `rollback()` is called
- THEN the insert is discarded
- AND `find_by_id()` returns None for the would-be entity

### Scenario: Repository find_by_id returns None

- GIVEN no entity exists with id="nonexistent"
- WHEN `repository.find_by_id("nonexistent")` is called
- THEN it returns `None` (no exception)

### Scenario: Repository update raises on missing entity

- GIVEN no entity exists with the given id
- WHEN `repository.update(entity)` is called
- THEN it raises `ValidationError`

### Scenario: Health check

- WHEN `health_check()` is called
- THEN it runs `SELECT 1` against the database
- AND returns `True` if successful

### Scenario: Connection pool pre-ping

- GIVEN a stale connection in the pool
- WHEN a query is executed
- THEN `pool_pre_ping` detects the stale connection
- AND a new connection is established automatically

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Connection lost, deadlock | TRANSIENT | Retry with backoff |
| Schema mismatch, table not found | PERMANENT | Fail bootstrap |
| Constraint violation | VALIDATION | Re-raise immediately |

## RED Metrics

- `cenf.database.query_total` (counter)
- `cenf.database.errors_total` (counter)
- `cenf.database.query_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryDatabaseAdapter` — dict-backed with transaction rollback support.
- **Integration**: `SQLAlchemyAdapter` with PostgreSQL testcontainer.
- **E2E**: Concurrent transactions, deadlock detection.

## Do's and Don'ts

**Do**:
- Use SQLAlchemy 2.0 async with asyncpg driver
- Implement GenericRepository with full CRUD
- Use Alembic for schema migrations
- Emit OTel spans on each query
- Set tenant_id contextvar for multi-tenant isolation

**Don't**:
- Expose raw SQLAlchemy sessions to domain
- Accept dynamic SQL from domain
- Use psycopg3 (LGPL) — only asyncpg (Apache 2.0)
- Perform ORM operations (no mandatory ORM)
