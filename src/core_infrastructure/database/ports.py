"""DatabaseManager Protocol — transactional database contract with generic repos.

Defines the database interface consumed by all infrastructure managers that
need persistent data access. Includes transaction scope management and a
generic typed repository pattern with full CRUD operations.

Security: DSN credentials MUST come from SecretManager — never hardcoded.
    Repository operations set tenant_id contextvar for multi-tenant isolation.
Observability: Every repository operation emits RED counters and tracing spans.
    Transaction begin/commit/rollback events are logged at INFO level.
@ai-directive: GenericRepository[T] is a Protocol with TypeVar T — adapter
    implementations MUST preserve the generic type for mypy strict mode.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class TransactionScope(Protocol):
    """Transaction scope contract for atomic operations.

    Returned by ``DatabaseManager.transaction()`` as an async context manager.
    Tracks pending operations and only applies them on ``commit()``.
    ``rollback()`` discards all pending changes.

    Rules:
        - commit() applies all pending operations atomically.
        - rollback() discards all pending operations without side effects.
        - Both commit() and rollback() are idempotent — calling twice is safe.
    """

    async def commit(self) -> None:
        """Apply all pending operations atomically.

        After commit, the transaction scope is closed — further operations
        on this scope should raise an error.

        Raises:
            PermanentError: If the commit fails (e.g., constraint violation).
        """
        ...

    async def rollback(self) -> None:
        """Discard all pending operations.

        After rollback, the transaction scope is closed. Idempotent —
        calling twice is safe and does nothing.
        """
        ...


@runtime_checkable
class GenericRepository(Protocol[T]):
    """Generic typed repository contract for CRUD operations.

    Each repository instance manages a single entity type T. Adapter
    implementations provide the concrete storage backend (in-memory dict
    or SQLAlchemy session).

    Rules:
        - find_by_id() returns None when the record is not found.
        - find_all() returns a list — empty list when no matches.
        - insert() returns the entity WITH its generated id.
        - update() raises ValidationError if the entity does not exist.
        - delete() is idempotent — deleting a non-existent id succeeds silently.
        - count() returns 0 when no records match the filters.

    Type Parameters:
        T: The entity type managed by this repository.
    """

    async def find_by_id(self, id: Any) -> T | None:
        """Find a single entity by its primary key.

        Args:
            id: The primary key value.

        Returns:
            T | None: The entity if found, ``None`` otherwise.
        """
        ...

    async def find_all(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[T]:
        """Find entities matching the given filters with pagination.

        Args:
            filters: Dict of field-name to value for exact-match filtering.
            order_by: Field name for ASC sorting, or None.
            limit: Maximum records to return.
            offset: Records to skip before returning.

        Returns:
            list[T]: Matching entities (empty list if none match).
        """
        ...

    async def insert(self, entity: T) -> T:
        """Insert a new entity into the repository.

        Args:
            entity: The entity to insert (without an id — the repository
                assigns one).

        Returns:
            T: The entity with its generated id populated.
        """
        ...

    async def update(self, entity: T) -> T:
        """Update an existing entity.

        Args:
            entity: The entity with updated fields (must have an id).

        Returns:
            T: The updated entity.

        Raises:
            ValidationError: If the entity does not exist.
        """
        ...

    async def delete(self, id: Any) -> None:
        """Delete an entity by its primary key.

        Idempotent — deleting a non-existent id succeeds silently.

        Args:
            id: The primary key value.
        """
        ...

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count entities matching the given filters.

        Args:
            filters: Dict of field-name to value for exact-match filtering.

        Returns:
            int: Number of matching entities (0 if none).
        """
        ...


@runtime_checkable
class DatabaseManager(Protocol):
    """Transactional database contract for all infrastructure managers.

    All managers that need persistent data access consume this interface.
    Concrete adapters provide in-memory dict (dev/testing) or SQLAlchemy
    with asyncpg (production).

    Rules:
        - transaction() returns an async context manager for atomic operations.
        - get_repository() returns a typed GenericRepository for entity T.
        - Repositories obtained within a transaction share its scope.

    @ai-directive: All repository methods are async because they may involve
        network I/O (database queries). In-memory adapter simulates this
        with synchronous operations wrapped in coroutines.
    """

    def transaction(self) -> AbstractAsyncContextManager[TransactionScope]:
        """Begin a new transaction scope.

        Returns an async context manager yielding a TransactionScope.
        Operations performed within the scope are only persisted on commit().

        Returns:
            AbstractAsyncContextManager[TransactionScope]: An async context
                manager for the transaction.

        Usage::

            async with db.transaction() as tx:
                repo = db.get_repository(User)
                await repo.insert(user)
                await tx.commit()
        """
        ...

    def get_repository(self, entity_type: type[T]) -> GenericRepository[T]:
        """Get a typed repository for the given entity type.

        Args:
            entity_type: The Python class representing the entity.

        Returns:
            GenericRepository[T]: A repository instance for the entity type.
        """
        ...
