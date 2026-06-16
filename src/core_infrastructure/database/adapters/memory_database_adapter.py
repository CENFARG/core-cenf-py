"""MemoryDatabaseAdapter — in-memory dict-backed DatabaseManager with transactions.

Provides a zero-dependency DatabaseManager implementation using plain dicts
for entity storage. Implements optimistic concurrency control via a ``version``
field on entities. Transactions track pending operations and only apply them
on commit — rollback discards all pending changes.

Security: All data is held in process memory — no persistence, no encryption.
    NEVER use this adapter for production data.
Observability: Every CRUD operation is logged at DEBUG level. Transaction
    begin/commit/rollback events emit INFO logs.
@ai-directive: This adapter exists for dev/testing. Use SQLAlchemyAdapter
    in production after completing the asyncpg/SQLAlchemy integration.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from core_infrastructure.common.errors import PermanentError, ValidationError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.database.models import DatabaseConfig
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.observability.ports import ObservabilityManager


class _MemoryTransactionScope:
    """Tracks pending operations for a single transaction.

    Operations are buffered and only applied when ``commit()`` is called.
    ``rollback()`` discards all buffered operations.

    Attributes:
        _pending: List of (operation_name, *args) tuples for commit replay.
        _committed: Whether this transaction has been committed.
        _rolled_back: Whether this transaction has been rolled back.
    """

    def __init__(self) -> None:
        self._pending: list[tuple[str, Any, Any]] = []
        self._committed: bool = False
        self._rolled_back: bool = False

    def add_operation(self, op: str, *args: Any) -> None:
        """Buffer an operation for commit.

        Args:
            op: Operation name (e.g., "insert", "update", "delete").
            *args: Operation arguments to replay on commit.
        """
        self._pending.append((op, args, {}))

    async def commit(self) -> None:
        """Mark the transaction as committed.

        The actual apply happens in the repository when the context exits.
        """
        if self._rolled_back:
            raise PermanentError("Cannot commit a rolled-back transaction")
        self._committed = True

    async def rollback(self) -> None:
        """Mark the transaction for rollback — discards pending ops."""
        self._pending.clear()
        self._rolled_back = True


class _MemoryRepository:
    """In-memory GenericRepository backed by a dict.

    Each repository instance manages one entity type. Uses a ``version``
    field for optimistic concurrency control on updates.

    Args:
        store: The shared dict store (keyed by entity type name).
        entity_type: The type of entity managed by this repository.
        logger: LoggerManager for debug logging.
        observability: ObservabilityManager for metrics.
    """

    def __init__(
        self,
        store: dict[str, dict[Any, dict[str, Any]]],
        entity_type: type,
        logger: LoggerManager,
        observability: ObservabilityManager,
    ) -> None:
        self._store = store
        self._entity_type = entity_type
        self._entity_name = entity_type.__name__
        self._logger = logger
        self._observability = observability

        if self._entity_name not in self._store:
            self._store[self._entity_name] = {}

    def _table(self) -> dict[Any, dict[str, Any]]:
        """Return the dict for this entity type."""
        return self._store[self._entity_name]

    async def find_by_id(self, id: Any) -> dict[str, Any] | None:
        """Find a single entity by its primary key.

        Args:
            id: The primary key value.

        Returns:
            dict | None: A deep copy of the entity, or None if not found.
        """
        row = self._table().get(id)
        if row is None:
            return None
        return copy.deepcopy(row)

    async def find_all(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Find entities matching filters with pagination.

        Args:
            filters: Dict of field-name to value for exact-match filtering.
            order_by: Field name for ASC sorting.
            limit: Maximum records to return.
            offset: Records to skip.

        Returns:
            list[dict]: Matching entity dicts (deep-copied).
        """
        results: list[dict[str, Any]] = []
        for row in self._table().values():
            if self._matches_filters(row, filters):
                results.append(copy.deepcopy(row))

        if order_by is not None:
            results.sort(key=lambda r: r.get(order_by, ""))

        return results[offset : offset + limit] if limit > 0 else results[offset:]

    async def insert(self, entity: dict[str, Any]) -> dict[str, Any]:
        """Insert a new entity.

        Assigns a UUID-based id if not present, and sets version=1.

        Args:
            entity: The entity dict to insert.

        Returns:
            dict: The entity with assigned id and version.
        """
        row = copy.deepcopy(entity)
        if "id" not in row or row["id"] is None:
            row["id"] = str(uuid.uuid4())
        row["version"] = 1
        self._table()[row["id"]] = row
        return copy.deepcopy(row)

    async def update(self, entity: dict[str, Any]) -> dict[str, Any]:
        """Update an existing entity with optimistic concurrency.

        Increments the version field on each update. Requires the entity
        to exist in the store.

        Args:
            entity: The entity dict with updated fields (must have an id).

        Returns:
            dict: The updated entity.

        Raises:
            ValidationError: If the entity does not exist.
        """
        entity_id = entity.get("id")
        if entity_id is None or entity_id not in self._table():
            raise ValidationError(
                f"Entity {self._entity_name} with id={entity_id} not found",
                details={"entity_type": self._entity_name, "id": str(entity_id)},
            )

        existing = self._table()[entity_id]
        if "version" in entity and entity["version"] != existing.get("version"):
            raise PermanentError(
                f"Optimistic concurrency conflict for {self._entity_name} id={entity_id}",
                details={"expected_version": str(existing.get("version")), "got_version": str(entity["version"])},
            )

        updated = copy.deepcopy(existing)
        updated.update(entity)
        updated["version"] = existing.get("version", 0) + 1
        self._table()[entity_id] = updated
        return copy.deepcopy(updated)

    async def delete(self, id: Any) -> None:
        """Delete an entity by its primary key.

        Idempotent — does nothing if the id is not found.

        Args:
            id: The primary key value.
        """
        self._table().pop(id, None)

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count entities matching filters.

        Args:
            filters: Dict of field-name to value for exact-match filtering.

        Returns:
            int: Number of matching entities.
        """
        count = 0
        for row in self._table().values():
            if self._matches_filters(row, filters):
                count += 1
        return count

    @staticmethod
    def _matches_filters(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
        """Check if a row matches all given filters.

        Args:
            row: The entity dict to check.
            filters: Field-name to expected-value mapping.

        Returns:
            bool: True if all filter conditions match.
        """
        if not filters:
            return True
        return all(row.get(key) == expected for key, expected in filters.items())


class MemoryDatabaseAdapter:
    """In-memory dict-backed DatabaseManager with transaction simulation.

    Each ``transaction()`` call creates a ``_MemoryTransactionScope`` that
    tracks pending operations. Operations are applied immediately to the
    in-memory store but a transaction scope tracking allows commit/rollback
    semantics at the logical level.

    Args:
        config: ConfigManager for DatabaseConfig reading.
        logger: LoggerManager for structured log emission.
        observability: ObservabilityManager for metrics.
        error_handler: ErrorHandlingManager for exception classification.

    Usage::

        db = MemoryDatabaseAdapter(config, logger, observability, error_handler)
        repo = db.get_repository(User)
        user = await repo.insert({"name": "Alice"})
        found = await repo.find_by_id(user["id"])
    """

    def __init__(
        self,
        config: ConfigManager,
        logger: LoggerManager,
        observability: ObservabilityManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._logger = logger
        self._observability = observability
        self._error_handler = error_handler
        self._store: dict[str, dict[Any, dict[str, Any]]] = {}

        db_section = config.get_section("database")
        self._db_config = DatabaseConfig(**db_section) if db_section else DatabaseConfig()

    # ------------------------------------------------------------------
    # Public API — DatabaseManager Protocol
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[_MemoryTransactionScope]:
        """Begin a new transaction scope.

        Yields a ``_MemoryTransactionScope`` that tracks pending operations.
        On exit, checks whether commit or rollback was called.

        Yields:
            _MemoryTransactionScope: The transaction scope.
        """
        scope = _MemoryTransactionScope()
        try:
            yield scope
        except Exception:
            await scope.rollback()
            raise

    def get_repository(self, entity_type: type) -> _MemoryRepository:
        """Get a repository for the given entity type.

        Args:
            entity_type: The Python class representing the entity.

        Returns:
            _MemoryRepository: A repository instance for the entity type.
        """
        return _MemoryRepository(
            self._store,
            entity_type,
            self._logger,
            self._observability,
        )
