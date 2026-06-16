"""Integration test fixtures — production-like adapters wired together.

Uses the same in-memory test doubles as unit tests but wires them
with their real dependency chains. The key difference from unit tests
is that integration tests verify cross-manager interactions — no mocking,
real adapter interaction through the wire.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
from core_infrastructure.auth.models import TokenClaims
from core_infrastructure.bootstrap import BootstrapOrchestrator
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.common.context import (
    get_context_snapshot,
    restore_context_snapshot,
)
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
# Context cleanup — prevents test isolation leaks from contextvars
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_contextvars() -> None:
    """Save and restore contextvars around each test to prevent cross-test pollution."""
    snapshot = get_context_snapshot()
    yield
    restore_context_snapshot(snapshot)


# Reuse the same _LifecycleWrapper from unit conftest (or duplicate for independence)
class _LifecycleWrapper:
    """Adds AsyncLifecycle (start/stop/health) to an adapter via composition."""

    def __init__(self, adapter: object, service_name: str) -> None:
        self._adapter = adapter
        self._service_name = service_name
        self._started = False
        self._stopped = False

    def __getattr__(self, name: str) -> object:
        return getattr(self._adapter, name)

    async def start(self) -> None:
        self._started = True

    async def stop(self) -> None:
        self._stopped = True

    async def health(self) -> HealthStatus:
        return HealthStatus(service=self._service_name, status="healthy")


@pytest.fixture
def config_manager() -> AsyncLifecycle:
    adapter = InMemoryConfigAdapter()
    return _LifecycleWrapper(adapter, "config")


@pytest.fixture
def logger_manager() -> AsyncLifecycle:
    adapter = InMemoryLoggerAdapter()
    return _LifecycleWrapper(adapter, "logger")


@pytest.fixture
def secret_manager() -> AsyncLifecycle:
    adapter = InMemorySecretAdapter()
    return _LifecycleWrapper(adapter, "secret")


@pytest.fixture
def observability_manager() -> AsyncLifecycle:
    adapter = InMemoryObservabilityAdapter()
    return _LifecycleWrapper(adapter, "observability")


@pytest.fixture
def error_manager(config_manager, logger_manager, observability_manager) -> AsyncLifecycle:
    adapter = ClassificationAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        observability=observability_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "error")


@pytest.fixture
def auth_manager() -> AsyncLifecycle:
    claims = TokenClaims(sub="test-user", iss="cenf-test", aud="cenf-app", exp=9999999999, iat=1)
    adapter = StaticAuthAdapter(default_claims=claims)
    return _LifecycleWrapper(adapter, "auth")


@pytest.fixture
def cache_manager(config_manager, logger_manager, error_manager) -> AsyncLifecycle:
    adapter = MemoryCacheAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        error_handler=error_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "cache")


@pytest.fixture
def database_manager(config_manager, logger_manager, observability_manager, error_manager) -> AsyncLifecycle:
    adapter = MemoryDatabaseAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        observability=observability_manager._adapter,
        error_handler=error_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "database")


@pytest.fixture
def filestorage_manager() -> AsyncLifecycle:
    adapter = MemoryStorageAdapter()
    return _LifecycleWrapper(adapter, "filestorage")


@pytest.fixture
def taskqueue_manager() -> AsyncLifecycle:
    adapter = MemoryTaskQueueAdapter()
    return _LifecycleWrapper(adapter, "taskqueue")


@pytest.fixture
def external_api_manager() -> AsyncLifecycle:
    adapter = MockHTTPAdapter()
    return _LifecycleWrapper(adapter, "external_api")


@pytest.fixture
def feature_flag_manager() -> AsyncLifecycle:
    adapter = MemoryFeatureFlagAdapter()
    return _LifecycleWrapper(adapter, "feature_flags")


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
