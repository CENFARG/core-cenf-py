"""Pytest fixtures for all 12 CENF infrastructure managers.

Provides test-ready manager instances that implement both their respective
Protocol interface and the AsyncLifecycle Protocol (start/stop/health).
All adapters are in-memory test doubles — no external I/O, no network.

Fixtures follow the dependency graph:
    Config → Logger → Secret → OTel → Error → Auth → Cache → DB →
    File → Queue → HTTP → Flags

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
from core_infrastructure.auth.models import TokenClaims
from core_infrastructure.bootstrap import BootstrapOrchestrator
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.common.lifecycle import AsyncLifecycle, HealthStatus
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
from core_infrastructure.errors.adapters.classification_adapter import ClassificationAdapter
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import MemoryFeatureFlagAdapter
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter
from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import MemoryTaskQueueAdapter

# ---------------------------------------------------------------------------
# Lifecycle wrapper — adds AsyncLifecycle to any adapter
# ---------------------------------------------------------------------------


class _LifecycleWrapper:
    """Adds AsyncLifecycle (start/stop/health) to an adapter via composition.

    Delegates attribute access to the wrapped adapter for all non-lifecycle
    methods. This allows any plain adapter to satisfy AsyncLifecycle without
    modifying the adapter's source code.

    Args:
        adapter: The manager adapter instance to wrap.
        service_name: Name used in HealthStatus.service.
    """

    def __init__(self, adapter: object, service_name: str) -> None:
        self._adapter = adapter
        self._service_name = service_name
        self._started = False
        self._stopped = False

    def __getattr__(self, name: str) -> object:
        """Delegate attribute access to the wrapped adapter."""
        return getattr(self._adapter, name)

    async def start(self) -> None:
        """Mark this manager as started."""
        self._started = True

    async def stop(self) -> None:
        """Mark this manager as stopped."""
        self._stopped = True

    async def health(self) -> HealthStatus:
        """Return a healthy status for this manager.

        Returns:
            HealthStatus: Always reports ``status="healthy"``.
        """
        return HealthStatus(service=self._service_name, status="healthy")


# ---------------------------------------------------------------------------
# Manager fixtures (in dependency order)
# ---------------------------------------------------------------------------


@pytest.fixture
def config_manager() -> AsyncLifecycle:
    """ConfigManager with in-memory adapter, wrapped for lifecycle."""
    adapter = InMemoryConfigAdapter()
    return _LifecycleWrapper(adapter, "config")


@pytest.fixture
def logger_manager() -> AsyncLifecycle:
    """LoggerManager with in-memory adapter, wrapped for lifecycle."""
    adapter = InMemoryLoggerAdapter()
    return _LifecycleWrapper(adapter, "logger")


@pytest.fixture
def secret_manager() -> AsyncLifecycle:
    """SecretManager with in-memory adapter, wrapped for lifecycle."""
    adapter = InMemorySecretAdapter()
    return _LifecycleWrapper(adapter, "secret")


@pytest.fixture
def observability_manager() -> AsyncLifecycle:
    """ObservabilityManager with in-memory adapter, wrapped for lifecycle."""
    adapter = InMemoryObservabilityAdapter()
    return _LifecycleWrapper(adapter, "observability")


@pytest.fixture
def error_manager(config_manager, logger_manager, observability_manager) -> AsyncLifecycle:
    """ErrorHandlingManager with ClassificationAdapter, wired with deps."""
    adapter = ClassificationAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        observability=observability_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "error")


@pytest.fixture
def auth_manager() -> AsyncLifecycle:
    """AuthManager with StaticAuthAdapter, wrapped for lifecycle."""
    claims = TokenClaims(sub="test-user", iss="cenf-test", aud="cenf-app", exp=9999999999, iat=1)
    adapter = StaticAuthAdapter(default_claims=claims)
    return _LifecycleWrapper(adapter, "auth")


@pytest.fixture
def cache_manager(config_manager, logger_manager, error_manager) -> AsyncLifecycle:
    """CacheManager with MemoryCacheAdapter, wired with deps."""
    adapter = MemoryCacheAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        error_handler=error_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "cache")


@pytest.fixture
def database_manager(config_manager, logger_manager, observability_manager, error_manager) -> AsyncLifecycle:
    """DatabaseManager with MemoryDatabaseAdapter, wired with deps."""
    adapter = MemoryDatabaseAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        observability=observability_manager._adapter,
        error_handler=error_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "database")


@pytest.fixture
def filestorage_manager() -> AsyncLifecycle:
    """FileStorageManager with MemoryStorageAdapter, wrapped for lifecycle."""
    adapter = MemoryStorageAdapter()
    return _LifecycleWrapper(adapter, "filestorage")


@pytest.fixture
def taskqueue_manager() -> AsyncLifecycle:
    """TaskQueueManager with MemoryTaskQueueAdapter, wrapped for lifecycle."""
    adapter = MemoryTaskQueueAdapter()
    return _LifecycleWrapper(adapter, "taskqueue")


@pytest.fixture
def external_api_manager() -> AsyncLifecycle:
    """ExternalAPIManager with MockHTTPAdapter, wrapped for lifecycle."""
    adapter = MockHTTPAdapter()
    return _LifecycleWrapper(adapter, "external_api")


@pytest.fixture
def feature_flag_manager() -> AsyncLifecycle:
    """FeatureFlagManager with MemoryFeatureFlagAdapter, wrapped for lifecycle."""
    adapter = MemoryFeatureFlagAdapter()
    return _LifecycleWrapper(adapter, "feature_flags")


# ---------------------------------------------------------------------------
# Bootstrap orchestrator fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def bootstrap_orchestrator(
    config_manager,
    logger_manager,
    secret_manager,
    observability_manager,
    error_manager,
    auth_manager,
    cache_manager,
    database_manager,
    filestorage_manager,
    taskqueue_manager,
    external_api_manager,
    feature_flag_manager,
) -> BootstrapOrchestrator:
    """BootstrapOrchestrator wired with all 12 manager fixtures.

    Returns:
        BootstrapOrchestrator: Fully wired orchestrator with all 12 managers
            in dependency order.
    """
    return BootstrapOrchestrator(
        config_manager,
        logger_manager,
        secret_manager,
        observability_manager,
        error_manager,
        auth_manager,
        cache_manager,
        database_manager,
        filestorage_manager,
        taskqueue_manager,
        external_api_manager,
        feature_flag_manager,
    )
