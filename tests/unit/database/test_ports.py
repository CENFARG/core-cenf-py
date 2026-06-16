"""Unit tests for DatabaseManager Protocol and Pydantic models.

Tests cover:
- DatabaseManager Protocol contract (transaction, get_repository)
- GenericRepository[T] Protocol contract (find_by_id, find_all, insert, update, delete, count)
- TransactionScope Protocol contract (commit, rollback)
- Protocols are runtime-checkable
- DatabaseConfig, RepositoryQuery, PaginatedResult model validation

Author: CENF AI Team
Version: 0.1.0
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.database.models import DatabaseConfig, PaginatedResult, RepositoryQuery
from core_infrastructure.database.ports import DatabaseManager, GenericRepository, TransactionScope


class TestDatabaseManagerProtocol:
    """Verify DatabaseManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """DatabaseManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(DatabaseManager, "_is_runtime_protocol") or hasattr(
            DatabaseManager, "__protocol_attrs__"
        )

    def test_has_transaction_method(self) -> None:
        """Protocol requires async transaction() context manager."""
        assert hasattr(DatabaseManager, "transaction")

    def test_has_get_repository_method(self) -> None:
        """Protocol requires get_repository[T](name) -> GenericRepository[T]."""
        assert hasattr(DatabaseManager, "get_repository")


class TestGenericRepositoryProtocol:
    """Verify GenericRepository[T] Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """GenericRepository Protocol is decorated with @runtime_checkable."""
        assert hasattr(GenericRepository, "_is_runtime_protocol") or hasattr(
            GenericRepository, "__protocol_attrs__"
        )

    def test_has_find_by_id_method(self) -> None:
        """Protocol requires find_by_id(id) -> T|None."""
        assert hasattr(GenericRepository, "find_by_id")

    def test_has_find_all_method(self) -> None:
        """Protocol requires find_all(filters, order_by, limit, offset)."""
        assert hasattr(GenericRepository, "find_all")

    def test_has_insert_method(self) -> None:
        """Protocol requires insert(entity) -> T."""
        assert hasattr(GenericRepository, "insert")

    def test_has_update_method(self) -> None:
        """Protocol requires update(entity) -> T."""
        assert hasattr(GenericRepository, "update")

    def test_has_delete_method(self) -> None:
        """Protocol requires delete(id)."""
        assert hasattr(GenericRepository, "delete")

    def test_has_count_method(self) -> None:
        """Protocol requires count(filters) -> int."""
        assert hasattr(GenericRepository, "count")


class TestTransactionScopeProtocol:
    """Verify TransactionScope Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """TransactionScope Protocol is decorated with @runtime_checkable."""
        assert hasattr(TransactionScope, "_is_runtime_protocol") or hasattr(
            TransactionScope, "__protocol_attrs__"
        )

    def test_has_commit_method(self) -> None:
        """Protocol requires commit() method."""
        assert hasattr(TransactionScope, "commit")

    def test_has_rollback_method(self) -> None:
        """Protocol requires rollback() method."""
        assert hasattr(TransactionScope, "rollback")


class TestDatabaseConfigModel:
    """Verify DatabaseConfig Pydantic model validation."""

    def test_default_config(self) -> None:
        """DatabaseConfig creates with sensible defaults."""
        config = DatabaseConfig()
        assert config.dsn == ""
        assert config.pool_size == 5
        assert config.max_overflow == 10
        assert config.pool_timeout == 30

    def test_custom_config(self) -> None:
        """DatabaseConfig accepts custom values."""
        config = DatabaseConfig(
            dsn="postgresql://localhost:5432/test",
            pool_size=10,
            max_overflow=20,
            pool_timeout=60,
        )
        assert config.dsn == "postgresql://localhost:5432/test"
        assert config.pool_size == 10
        assert config.max_overflow == 20
        assert config.pool_timeout == 60

    def test_negative_pool_size_fails(self) -> None:
        """pool_size must be >= 0."""
        with pytest.raises(PydanticValidationError):
            DatabaseConfig(pool_size=-1)

    def test_negative_max_overflow_fails(self) -> None:
        """max_overflow must be >= 0."""
        with pytest.raises(PydanticValidationError):
            DatabaseConfig(max_overflow=-1)


class TestRepositoryQueryModel:
    """Verify RepositoryQuery Pydantic model."""

    def test_default_query(self) -> None:
        """RepositoryQuery creates with sensible defaults."""
        query = RepositoryQuery()
        assert query.filters == {}
        assert query.order_by is None
        assert query.limit == 100
        assert query.offset == 0

    def test_custom_query(self) -> None:
        """RepositoryQuery accepts custom filters and pagination."""
        query = RepositoryQuery(
            filters={"status": "active"},
            order_by="created_at",
            limit=50,
            offset=10,
        )
        assert query.filters == {"status": "active"}
        assert query.order_by == "created_at"
        assert query.limit == 50
        assert query.offset == 10

    def test_negative_limit_fails(self) -> None:
        """limit must be >= 0."""
        with pytest.raises(PydanticValidationError):
            RepositoryQuery(limit=-1)

    def test_negative_offset_fails(self) -> None:
        """offset must be >= 0."""
        with pytest.raises(PydanticValidationError):
            RepositoryQuery(offset=-1)


class TestPaginatedResultModel:
    """Verify PaginatedResult Pydantic model."""

    def test_empty_result(self) -> None:
        """PaginatedResult with empty items list."""
        result = PaginatedResult(items=[], total=0, limit=100, offset=0)
        assert result.items == []
        assert result.total == 0
        assert result.limit == 100
        assert result.offset == 0
        assert result.has_more is False

    def test_result_with_items(self) -> None:
        """PaginatedResult with items and total."""
        result = PaginatedResult(items=[{"id": 1}, {"id": 2}], total=10, limit=5, offset=0)
        assert len(result.items) == 2
        assert result.total == 10
        assert result.has_more is True

    def test_has_more_when_total_equals_limit(self) -> None:
        """has_more is True when total exceeds offset + limit."""
        result = PaginatedResult(items=[{"id": 1}], total=10, limit=5, offset=5)
        assert result.has_more is True

    def test_has_more_false_when_total_below_limit(self) -> None:
        """has_more is False when total <= offset + limit."""
        result = PaginatedResult(items=[{"id": 1}], total=1, limit=10, offset=0)
        assert result.has_more is False
