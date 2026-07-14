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

# Safe imports — zero optional deps
from core_infrastructure.database.models import DatabaseConfig, PaginatedResult, RepositoryQuery
from core_infrastructure.database.ports import DatabaseManager, GenericRepository, TransactionScope

# Optional adapters — gracefully degrade if optional deps missing
try:
    from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
except ImportError:
    MemoryDatabaseAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter
except ImportError:
    SQLAlchemyAdapter = None  # type: ignore[assignment,misc]

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
