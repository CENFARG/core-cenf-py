"""SQLAlchemyAdapter — skeleton for SQLAlchemy-backed DatabaseManager.

Provides the class structure and constructor for an async SQLAlchemy
database backend. SQLAlchemy is an optional dependency — this adapter
is NOT implemented yet and raises ``NotImplementedError`` on all methods.

Security: DSN credentials MUST come from SecretManager. NEVER hardcode
    connection strings. Use encrypted config for production.
Observability: When implemented, all operations emit query duration histograms
    and RED counters via ObservabilityManager.
@ai-directive: This is a SKELETON — do NOT use in production until the
    SQLAlchemy backend is fully implemented and integration-tested.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.observability.ports import ObservabilityManager
from core_infrastructure.secrets.ports import SecretManager


class SQLAlchemyAdapter:
    """Skeleton for SQLAlchemy-backed DatabaseManager.

    Raises ``NotImplementedError`` on all operations. Use this class as a
    structural placeholder — implement the SQLAlchemy backend when the
    optional ``sqlalchemy[asyncio]>=2.0`` dependency is available.

    Args:
        config: ConfigManager for database connection settings.
        secrets: SecretManager for database credentials.
        logger: LoggerManager for structured log emission.
        observability: ObservabilityManager for query metrics.
        error_handler: ErrorHandlingManager for exception classification.
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

    def transaction(self) -> Any:
        raise NotImplementedError("SQLAlchemyAdapter.transaction() is not implemented")

    def get_repository(self, entity_type: type) -> Any:
        raise NotImplementedError("SQLAlchemyAdapter.get_repository() is not implemented")
