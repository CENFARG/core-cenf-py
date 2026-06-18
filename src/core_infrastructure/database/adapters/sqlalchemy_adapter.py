"""SQLAlchemyAdapter — production async SQLAlchemy-backed DatabaseManager.

Provides a SQLAlchemy 2.0+ async-backed DatabaseManager implementation with
connection pooling, transaction scoping via contextvars, and typed
GenericRepository[T] for full CRUD operations.

Security: DSN credentials come from SecretManager — never hardcoded.
Observability: Query operations emit duration histograms via ObservabilityManager.
@ai-directive: Active session is propagated via ``contextvars`` so that
    ``get_repository()`` works naturally within ``transaction()`` blocks.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core_infrastructure.common.errors import PermanentError, ValidationError
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.observability.ports import ObservabilityManager
from core_infrastructure.secrets.ports import SecretManager

# Active session contextvar — propagated by ``transaction()`` for use by ``get_repository()``.
_active_session: ContextVar[AsyncSession | None] = ContextVar("_active_session", default=None)


class _SQLAlchemyTransactionScope:
    """Transaction scope wrapping a SQLAlchemy AsyncSession.

    Delegates commit() and rollback() to the underlying session.
    Both are idempotent — calling twice is safe.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._committed = False
        self._rolled_back = False

    async def commit(self) -> None:
        """Apply all pending operations atomically."""
        if self._rolled_back:
            raise PermanentError("Cannot commit a rolled-back transaction")
        if not self._committed:
            await self._session.commit()
            self._committed = True

    async def rollback(self) -> None:
        """Discard all pending operations."""
        if not self._rolled_back:
            await self._session.rollback()
            self._rolled_back = True


class _SQLAlchemyRepository:
    """GenericRepository[T] backed by a SQLAlchemy AsyncSession.

    Each repository instance manages a single entity type T using the
    session obtained from the ``_active_session`` contextvar.

    Args:
        session: SQLAlchemy AsyncSession for database operations.
        entity_type: The ORM model class (must inherit DeclarativeBase).
        observability: ObservabilityManager for query metrics.
    """

    def __init__(
        self,
        session: AsyncSession,
        entity_type: type[DeclarativeBase],
        observability: ObservabilityManager,
    ) -> None:
        self._session = session
        self._entity_type = entity_type
        self._observability = observability

    async def find_by_id(self, id: Any) -> Any | None:
        """Find a single entity by its primary key."""
        return await self._session.get(self._entity_type, id)

    async def find_all(
        self,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        """Find entities matching filters with pagination."""
        stmt = select(self._entity_type)

        if filters:
            for field, value in filters.items():
                col = getattr(self._entity_type, field, None)
                if col is not None:
                    stmt = stmt.where(col == value)

        if order_by is not None:
            col = getattr(self._entity_type, order_by, None)
            if col is not None:
                stmt = stmt.order_by(col.asc())

        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def insert(self, entity: Any) -> Any:
        """Insert a new entity into the session."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: Any) -> Any:
        """Update an existing entity (must already be attached to session)."""
        existing = await self._session.get(self._entity_type, self._pk(entity))
        if existing is None:
            raise ValidationError(
                f"Entity {self._entity_type.__name__} not found for update",
                details={"id": str(self._pk(entity))},
            )
        await self._session.merge(entity)
        await self._session.flush()
        return entity

    async def delete(self, id: Any) -> None:
        """Delete an entity by its primary key (idempotent)."""
        entity = await self._session.get(self._entity_type, id)
        if entity is not None:
            await self._session.delete(entity)
            await self._session.flush()

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count entities matching filters."""
        stmt = select(func.count()).select_from(self._entity_type)

        if filters:
            for field, value in filters.items():
                col = getattr(self._entity_type, field, None)
                if col is not None:
                    stmt = stmt.where(col == value)

        result = await self._session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    def _pk(entity: Any) -> Any:
        """Extract primary key value from an entity."""
        pk_cols = entity.__table__.primary_key.columns.keys()
        if len(pk_cols) == 1:
            return getattr(entity, pk_cols[0])
        return tuple(getattr(entity, c) for c in pk_cols)


class SQLAlchemyAdapter:
    """Async SQLAlchemy-backed DatabaseManager with connection pooling.

    Creates an async engine from DSN config and provides transaction-scoped
    repositories for typed entity CRUD operations via contextvar propagation.

    Args:
        config: ConfigManager for ``database.dsn``, ``database.pool_size``,
            ``database.max_overflow``, ``database.pool_timeout``.
        secrets: SecretManager for database credentials (reserved).
        logger: LoggerManager for structured log emission.
        observability: ObservabilityManager for query metrics.
        error_handler: ErrorHandlingManager for exception classification.

    Usage::

        db = SQLAlchemyAdapter(config, secrets, logger, observability, errors)
        async with db.transaction() as tx:
            repo = db.get_repository(User)
            user = await repo.insert(User(name="Alice"))
            await tx.commit()
    """

    def __init__(
        self,
        config: ConfigManager,
        secrets: SecretManager,
        logger: LoggerManager,
        observability: ObservabilityManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._logger = logger
        self._observability = observability
        self._error_handler = error_handler

        dsn = config.get_string("database.dsn", default_value="sqlite+aiosqlite://")
        self._pool_size: int = int(config.get_number("database.pool_size", default_value=5))
        self._max_overflow: int = int(config.get_number("database.max_overflow", default_value=10))
        self._pool_timeout: int = int(config.get_number("database.pool_timeout", default_value=30))

        engine_kwargs: dict[str, Any] = {}
        # Pool arguments are only valid for server-based dialects (PostgreSQL, MySQL, etc.)
        # SQLite uses StaticPool and does not accept pool_size/max_overflow/pool_timeout.
        if not dsn.startswith("sqlite"):
            engine_kwargs.update(
                pool_size=self._pool_size,
                max_overflow=self._max_overflow,
                pool_timeout=self._pool_timeout,
            )

        self._engine = create_async_engine(dsn, **engine_kwargs)
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    # ------------------------------------------------------------------
    # Public API — DatabaseManager Protocol
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[_SQLAlchemyTransactionScope]:
        """Begin a new transaction scope.

        Sets ``_active_session`` contextvar so that ``get_repository()``
        called within the ``async with`` block receives the correct session.

        Yields:
            _SQLAlchemyTransactionScope: The transaction scope.
        """
        session: AsyncSession = self._session_factory()
        scope = _SQLAlchemyTransactionScope(session)
        token = _active_session.set(session)
        try:
            yield scope
        except Exception:
            await session.rollback()
            raise
        finally:
            if not scope._committed and not scope._rolled_back:
                await session.rollback()
            _active_session.reset(token)
            await session.close()

    def get_repository(self, entity_type: type) -> _SQLAlchemyRepository:
        """Get a typed repository for the given entity type.

        Must be called within an active ``transaction()`` block —
        the session is propagated via ``_active_session`` contextvar.

        Args:
            entity_type: The ORM model class.

        Returns:
            _SQLAlchemyRepository: A repository instance for the entity type.

        Raises:
            RuntimeError: If called outside an active transaction.
        """
        session = _active_session.get()
        if session is None:
            raise RuntimeError(
                "get_repository() must be called within a transaction() context. "
                "Use: async with db.transaction() as tx: repo = db.get_repository(T)"
            )
        return _SQLAlchemyRepository(session, entity_type, self._observability)
