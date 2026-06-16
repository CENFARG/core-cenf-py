"""CENF DatabaseManager — transactional database access with generic repositories.

Provides a Protocol-based interface for persistent data access with full
CRUD operations via GenericRepository[T]. MemoryDatabaseAdapter implements
the contract with in-memory dicts and optimistic concurrency; SQLAlchemyAdapter
is a skeleton for future production use with asyncpg.

Security: DSN credentials MUST come from SecretManager. Entity operations
    set tenant_id contextvar for multi-tenant isolation.
Observability: Every repository operation emits RED counters and tracing
    spans via ObservabilityManager.
@ai-directive: MemoryDatabaseAdapter exists for dev/testing. Use
    SQLAlchemyAdapter in production after completing the backend.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter
from core_infrastructure.database.models import DatabaseConfig, PaginatedResult, RepositoryQuery
from core_infrastructure.database.ports import DatabaseManager, GenericRepository, TransactionScope

__all__ = [
    "DatabaseConfig",
    "DatabaseManager",
    "GenericRepository",
    "MemoryDatabaseAdapter",
    "PaginatedResult",
    "RepositoryQuery",
    "SQLAlchemyAdapter",
    "TransactionScope",
]
