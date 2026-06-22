---
sidebar_position: 8
---

# DatabaseManager (M08)

Transactional database access with generic typed repositories and async context manager support. All persistent data access flows through this interface.

## Protocol

`DatabaseManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.database.ports`.

### `transaction() → AbstractAsyncContextManager[TransactionScope]`

Begin a new transaction scope.

```python
def transaction(self) -> AbstractAsyncContextManager[TransactionScope]: ...
```

Returns an async context manager yielding a `TransactionScope`. Operations performed within the scope are only persisted on `commit()`.

---

### `get_repository(entity_type: type[T]) → GenericRepository[T]`

Get a typed repository for the given entity type.

```python
def get_repository(self, entity_type: type[T]) -> GenericRepository[T]: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `entity_type` | `type[T]` | The Python class representing the entity |

**Returns:** A `GenericRepository[T]` instance for the entity type. Repositories obtained within a transaction share its scope.

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing `DatabaseConfig`.

---

## TransactionScope

```python
class TransactionScope(Protocol):
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

| Method | Description |
|--------|-------------|
| `commit()` | Apply all pending operations atomically. After commit, the scope is closed — further operations raise. |
| `rollback()` | Discard all pending operations. Idempotent — calling twice is safe. |

**Raises:** `PermanentError` if commit fails (e.g., constraint violation).

## GenericRepository[T]

```python
class GenericRepository(Protocol[T]):
    async def find_by_id(self, id: Any) -> T | None: ...
    async def find_all(self, filters=None, order_by=None, limit=100, offset=0) -> list[T]: ...
    async def insert(self, entity: T) -> T: ...
    async def update(self, entity: T) -> T: ...
    async def delete(self, id: Any) -> None: ...
    async def count(self, filters=None) -> int: ...
```

### `find_by_id(id: Any) → T | None`

Find a single entity by its primary key.

```python
async def find_by_id(self, id: Any) -> T | None: ...
```

**Returns:** The entity if found, `None` otherwise.

---

### `find_all(filters: dict[str, Any] | None = None, order_by: str | None = None, limit: int = 100, offset: int = 0) → list[T]`

Find entities matching the given filters with pagination.

```python
async def find_all(
    self,
    filters: dict[str, Any] | None = None,
    order_by: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[T]: ...
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `filters` | `dict[str, Any] \| None` | `None` | Field-name to value for exact-match filtering |
| `order_by` | `str \| None` | `None` | Field name for ASC sorting |
| `limit` | `int` | `100` | Maximum records to return |
| `offset` | `int` | `0` | Records to skip |

**Returns:** Matching entities (empty list if none match).

---

### `insert(entity: T) → T`

Insert a new entity into the repository.

```python
async def insert(self, entity: T) -> T: ...
```

**Returns:** The entity with its generated `id` populated.

---

### `update(entity: T) → T`

Update an existing entity.

```python
async def update(self, entity: T) -> T: ...
```

**Returns:** The updated entity.

**Raises:** `ValidationError` if the entity does not exist.

---

### `delete(id: Any) → None`

Delete an entity by its primary key.

```python
async def delete(self, id: Any) -> None: ...
```

Idempotent — deleting a non-existent id succeeds silently.

---

### `count(filters: dict[str, Any] | None = None) → int`

Count entities matching the given filters.

```python
async def count(self, filters: dict[str, Any] | None = None) -> int: ...
```

**Returns:** Number of matching entities (0 if none).

## Models

### `DatabaseConfig`

**File:** `core_infrastructure.database.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dsn` | `str` (max 2048) | `""` | Database connection string (`scheme://user:pass@host:port/dbname`) |
| `pool_size` | `int` (≥0) | `5` | Persistent connections in the pool |
| `max_overflow` | `int` (≥0) | `10` | Additional connections beyond pool_size |
| `pool_timeout` | `int` (≥0) | `30` | Seconds to wait for a pool connection |

**Security:** DSN may contain credentials — NEVER log it at INFO or above. Use masked DSN for logging.

---

### `RepositoryQuery`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `filters` | `dict[str, Any]` | `{}` | Field-name to value filters |
| `order_by` | `str \| None` | `None` | Field name for ASC ordering |
| `limit` | `int` (≥0) | `100` | Max records (0 = no limit) |
| `offset` | `int` (≥0) | `0` | Records to skip |

---

### `PaginatedResult`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `items` | `list[Any]` | `[]` | Records for the current page |
| `total` | `int` (≥0) | `0` | Total matching records |
| `limit` | `int` (≥0) | `100` | Query limit |
| `offset` | `int` (≥0) | `0` | Query offset |
| `has_more` | `bool` *(computed)* | — | `True` if `offset + len(items) < total` |

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `MemoryDatabaseAdapter` | Python dict | Dev/testing — in-process, no persistence |
| `SQLAlchemyAdapter` | SQLAlchemy 2.0 + asyncpg | Production — PostgreSQL with connection pooling |

## Usage Example

```python
from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter

# Bootstrap
db = SQLAlchemyAdapter(config_manager=config, logger_manager=logger, secret_manager=secrets)

# Transaction with repository (RECOMMENDED pattern)
async with db.transaction() as tx:
    repo = db.get_repository(User)

    # Insert
    new_user = User(name="Alice", email="alice@example.com")
    created = await repo.insert(new_user)
    # → User(id="uuid-...", name="Alice", email="alice@example.com")

    # Find by id
    user = await repo.find_by_id(created.id)

    # Update
    user.name = "Alice Updated"
    updated = await repo.update(user)

    # Find all with filters + pagination
    users = await repo.find_all(
        filters={"role": "admin"},
        order_by="name",
        limit=50,
        offset=0,
    )

    # Count
    admin_count = await repo.count(filters={"role": "admin"})

    # Delete (idempotent)
    await repo.delete(created.id)

    # Commit all operations
    await tx.commit()
    # After commit, the transaction scope is closed
```

### Rollback Pattern

```python
async with db.transaction() as tx:
    repo = db.get_repository(User)
    await repo.insert(User(name="Temp User"))
    # Something went wrong — rollback
    await tx.rollback()
    # All pending operations are discarded
```

### Testing with MemoryDatabaseAdapter

```python
from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter

db = MemoryDatabaseAdapter(config_manager=config, logger_manager=logger)
async with db.transaction() as tx:
    repo = db.get_repository(MyEntity)
    entity = await repo.insert(MyEntity(field="value"))
    assert await repo.find_by_id(entity.id) is not None
```

## @ai-directive

- **Always use `async with db.transaction() as tx:` — never raw sessions.**
- All repository methods are async because they may involve network I/O.
- `GenericRepository[T]` is a Protocol with TypeVar T — adapter implementations MUST preserve the generic type for mypy strict mode.
- DSN credentials MUST come from SecretManager — never hardcoded.
- Repository operations set `tenant_id` contextvar for multi-tenant isolation.

## Related

- [SecretManager](secret-manager.md) — retrieves DSN connection string
- [CacheManager](cache-manager.md) — common `get_or_set` pattern for caching query results
- [LoggerManager](logger-manager.md) — transaction begin/commit/rollback logged at INFO
- [ObservabilityManager](observability-manager.md) — RED counters and tracing spans per operation
