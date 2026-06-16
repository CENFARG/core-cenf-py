"""CENF DatabaseManager models — DatabaseConfig, RepositoryQuery, PaginatedResult.

Defines the Pydantic models for DatabaseManager configuration and data transfer.
DatabaseConfig controls connection pooling; RepositoryQuery standardizes
query filtering and pagination; PaginatedResult wraps paginated responses.

Security: DatabaseConfig.dsn may contain credentials — NEVER log it at INFO
    or above. Use masked DSN for logging.
Observability: Pool metrics (size, overflow, timeout) are emitted via
    ObservabilityManager on pool events.
@ai-directive: RepositoryQuery.limit defaults to 100 — callers should
    always specify explicit pagination for large datasets.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """Configuration for DatabaseManager adapters.

    Controls database connection string, pool sizing, and timeout behavior.
    The DSN follows the standard ``scheme://user:pass@host:port/dbname`` format
    as accepted by SQLAlchemy and asyncpg.

    Attributes:
        dsn: Database connection string (data source name).
        pool_size: Maximum number of persistent connections in the pool.
        max_overflow: Additional connections allowed beyond pool_size.
        pool_timeout: Seconds to wait for a connection from the pool.
    """

    dsn: str = Field(default="", max_length=2048, description="Database connection string.")
    pool_size: int = Field(default=5, ge=0, description="Pool size (persistent connections).")
    max_overflow: int = Field(default=10, ge=0, description="Overflow connections beyond pool_size.")
    pool_timeout: int = Field(default=30, ge=0, description="Seconds to wait for a pool connection.")


class RepositoryQuery(BaseModel):
    """Standardized query parameters for GenericRepository.find_all().

    Combines filtering, sorting, and pagination into a single model.
    All fields are optional — empty query returns all records up to limit.

    Attributes:
        filters: Dict of field-name to value for exact-match filtering.
        order_by: Field name to sort by (ASC), or None for no ordering.
        limit: Maximum number of records to return (0 = no limit).
        offset: Number of records to skip before returning results.
    """

    filters: dict[str, Any] = Field(default_factory=dict, description="Field-name to value filters.")
    order_by: str | None = Field(default=None, description="Field name for ASC ordering.")
    limit: int = Field(default=100, ge=0, description="Max records (0 = no limit).")
    offset: int = Field(default=0, ge=0, description="Records to skip.")


class PaginatedResult(BaseModel):
    """Paginated result wrapper returned by GenericRepository.find_all().

    Wraps a list of items with total count and pagination metadata.
    ``has_more`` is computed from ``offset + len(items) < total``.

    Attributes:
        items: The list of entity records for the current page.
        total: Total number of records matching the query (before pagination).
        limit: The limit used in the query.
        offset: The offset used in the query.
        has_more: True if there are more records after this page.
    """

    items: list[Any] = Field(default_factory=list, description="Records for the current page.")
    total: int = Field(default=0, ge=0, description="Total matching records.")
    limit: int = Field(default=100, ge=0, description="Query limit.")
    offset: int = Field(default=0, ge=0, description="Query offset.")

    @property
    def has_more(self) -> bool:
        """Check if more records exist beyond this page.

        Returns:
            bool: ``True`` if ``offset + len(items) < total``.
        """
        return (self.offset + len(self.items)) < self.total
