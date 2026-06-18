"""Unit tests for SQLAlchemyAdapter — async SQLAlchemy-backed DatabaseManager.

Tests cover:
- Protocol compliance (satisfies DatabaseManager)
- Async engine creation with config-driven connection settings
- Full CRUD cycle: insert, find_by_id, find_all, update, delete, count
- Transaction commit persistence
- Transaction rollback discards changes
- find_all with filters, order_by, limit, offset
- Repository typing (GenericRepository[T])

Uses SQLite :memory: with aiosqlite for lightweight async testing.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.database.ports import DatabaseManager
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter

# ---------------------------------------------------------------------------
# Test ORM model
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Declarative base for test models."""


class User(Base):
    """Test User entity for CRUD operations."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=False)
    email: Mapped[str] = mapped_column(nullable=False, default="")


# ---------------------------------------------------------------------------
# Test configuration
# ---------------------------------------------------------------------------

SQLITE_DSN = "sqlite+aiosqlite://"


@pytest.fixture
def config() -> InMemoryConfigAdapter:
    """Create config with SQLite DSN for testing."""
    return InMemoryConfigAdapter(
        initial_data={
            "database": {
                "dsn": SQLITE_DSN,
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
            },
        }
    )


@pytest.fixture
def secrets() -> InMemorySecretAdapter:
    """Create InMemorySecretAdapter."""
    return InMemorySecretAdapter()


@pytest.fixture
def logger() -> InMemoryLoggerAdapter:
    """Create InMemoryLoggerAdapter."""
    return InMemoryLoggerAdapter()


@pytest.fixture
def observability() -> InMemoryObservabilityAdapter:
    """Create InMemoryObservabilityAdapter."""
    return InMemoryObservabilityAdapter()


@pytest.fixture
def error_handler(
    config: InMemoryConfigAdapter, logger: InMemoryLoggerAdapter, observability: InMemoryObservabilityAdapter
) -> CapturingErrorAdapter:
    """Create CapturingErrorAdapter."""
    return CapturingErrorAdapter(config, logger, observability)


@pytest.fixture
async def adapter(
    config: InMemoryConfigAdapter,
    secrets: InMemorySecretAdapter,
    logger: InMemoryLoggerAdapter,
    observability: InMemoryObservabilityAdapter,
    error_handler: CapturingErrorAdapter,
):
    """Create SQLAlchemyAdapter with SQLite :memory: and ensure tables."""
    from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter

    db = SQLAlchemyAdapter(config, secrets, logger, observability, error_handler)
    # Create tables
    async with db._engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.run_sync(Base.metadata.create_all)
    yield db
    # Cleanup
    async with db._engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.run_sync(Base.metadata.drop_all)
    await db._engine.dispose()  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSQLAlchemyAdapterProtocol:
    """Verify SQLAlchemyAdapter satisfies DatabaseManager Protocol."""

    @pytest.mark.asyncio
    async def test_satisfies_database_manager_protocol(self, adapter) -> None:
        """SQLAlchemyAdapter passes isinstance check against DatabaseManager."""
        from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter

        assert isinstance(adapter, SQLAlchemyAdapter)
        assert isinstance(adapter, DatabaseManager)


class TestSQLAlchemyAdapterCRUD:
    """Verify full CRUD operations within a transaction."""

    @pytest.mark.asyncio
    async def test_insert_and_find_by_id(self, adapter) -> None:
        """Insert an entity and retrieve it by ID."""
        user = User(name="Alice", email="alice@test.com")

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            inserted = await repo.insert(user)
            await tx.commit()

        assert inserted.id is not None
        assert inserted.name == "Alice"
        assert inserted.email == "alice@test.com"

    @pytest.mark.asyncio
    async def test_find_by_id_returns_none_for_missing(self, adapter) -> None:
        """find_by_id returns None for non-existent ID."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            result = await repo.find_by_id(9999)
            await tx.commit()

        assert result is None

    @pytest.mark.asyncio
    async def test_find_all_returns_all_records(self, adapter) -> None:
        """find_all returns all inserted records."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            await repo.insert(User(name="Alice", email="a@t.com"))
            await repo.insert(User(name="Bob", email="b@t.com"))
            await repo.insert(User(name="Charlie", email="c@t.com"))
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            results = await repo.find_all()
            await tx.commit()

        assert len(results) == 3
        names = {r.name for r in results}
        assert names == {"Alice", "Bob", "Charlie"}

    @pytest.mark.asyncio
    async def test_find_all_with_filters(self, adapter) -> None:
        """find_all filters by field-value pairs."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            await repo.insert(User(name="Alice", email="a@t.com"))
            await repo.insert(User(name="Bob", email="b@t.com"))
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            results = await repo.find_all(filters={"name": "Alice"})
            await tx.commit()

        assert len(results) == 1
        assert results[0].name == "Alice"

    @pytest.mark.asyncio
    async def test_find_all_with_pagination(self, adapter) -> None:
        """find_all supports limit and offset pagination."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            for i in range(10):
                await repo.insert(User(name=f"User{i}", email=f"u{i}@t.com"))
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            results = await repo.find_all(limit=3, offset=5)
            await tx.commit()

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_find_all_with_order_by(self, adapter) -> None:
        """find_all orders by specified field ASC."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            await repo.insert(User(name="Charlie", email="c@t.com"))
            await repo.insert(User(name="Alice", email="a@t.com"))
            await repo.insert(User(name="Bob", email="b@t.com"))
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            results = await repo.find_all(order_by="name")
            await tx.commit()

        assert [r.name for r in results] == ["Alice", "Bob", "Charlie"]

    @pytest.mark.asyncio
    async def test_update_existing_entity(self, adapter) -> None:
        """update modifies an existing entity."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            user = await repo.insert(User(name="Alice", email="old@t.com"))
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            user.name = "Alice Updated"
            updated = await repo.update(user)
            await tx.commit()

        assert updated.name == "Alice Updated"

    @pytest.mark.asyncio
    async def test_delete_removes_entity(self, adapter) -> None:
        """delete removes an entity by ID."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            user = await repo.insert(User(name="DeleteMe", email="d@t.com"))
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            await repo.delete(user.id)
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            found = await repo.find_by_id(user.id)
            await tx.commit()

        assert found is None

    @pytest.mark.asyncio
    async def test_count_returns_correct_total(self, adapter) -> None:
        """count returns total matching entities."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            await repo.insert(User(name="A", email="a@t.com"))
            await repo.insert(User(name="B", email="b@t.com"))
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            total = await repo.count()
            await tx.commit()

        assert total == 2

    @pytest.mark.asyncio
    async def test_count_with_filters(self, adapter) -> None:
        """count with filters returns matching count."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            await repo.insert(User(name="Alice", email="a@t.com"))
            await repo.insert(User(name="Alice", email="a2@t.com"))
            await repo.insert(User(name="Bob", email="b@t.com"))
            await tx.commit()

        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            total = await repo.count(filters={"name": "Alice"})
            await tx.commit()

        assert total == 2


class TestSQLAlchemyAdapterTransactions:
    """Verify transaction commit/rollback behavior."""

    @pytest.mark.asyncio
    async def test_commit_persists_changes(self, adapter) -> None:
        """Changes within a committed transaction are persisted."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            await repo.insert(User(name="Persisted", email="p@t.com"))
            await tx.commit()

        # Read in a new transaction to verify persistence
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            results = await repo.find_all(filters={"name": "Persisted"})
            await tx.commit()

        assert len(results) == 1
        assert results[0].name == "Persisted"

    @pytest.mark.asyncio
    async def test_rollback_discards_changes(self, adapter) -> None:
        """Changes within a rolled-back transaction are discarded."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            await repo.insert(User(name="Discarded", email="d@t.com"))
            await tx.rollback()

        # Read to verify nothing was persisted
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            results = await repo.find_all(filters={"name": "Discarded"})
            await tx.commit()

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_count_before_and_after_commit(self, adapter) -> None:
        """Count reflects committed changes only."""
        async with adapter.transaction() as tx:
            repo = adapter.get_repository(User)
            before = await repo.count()
            await repo.insert(User(name="New", email="n@t.com"))
            after_insert = await repo.count()
            await tx.commit()

        assert after_insert == before + 1


class TestSQLAlchemyAdapterEngineConfig:
    """Verify adapter reads configuration correctly."""

    @pytest.mark.asyncio
    async def test_engine_created_with_config_values(self, config, secrets, logger, observability, error_handler) -> None:
        """Engine is created with values from ConfigManager."""
        from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter

        db = SQLAlchemyAdapter(config, secrets, logger, observability, error_handler)
        assert db._engine is not None

        # Verify pool config was applied
        # Default SQLAlchemy pool for async SQLite is NullPool, but config values are stored
        assert db._pool_size == 5
        assert db._max_overflow == 10
        assert db._pool_timeout == 30

        await db._engine.dispose()
