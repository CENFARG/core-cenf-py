"""E2E test fixtures — all 16 CENF infrastructure managers wired together.

Extends the integration conftest pattern with the 4 additional managers
(M13-M16: alert, dependency, dynamic_prompting, ratelimit) and provides
a BootstrapOrchestrator fixture with the complete 16-manager stack.

All adapters are in-memory test doubles — no external I/O, no network.
Each fixture is wrapped with _LifecycleWrapper for AsyncLifecycle compliance.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.alert.adapters.dispatch_alert_adapter import DispatchAlertAdapter
from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
from core_infrastructure.auth.models import TokenClaims
from core_infrastructure.bootstrap import BootstrapOrchestrator
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.common.lifecycle import AsyncLifecycle, HealthStatus
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import (
    InMemoryDependencyAdapter,
)
from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import (
    ConditionalPromptAdapter,
)
from core_infrastructure.errors.adapters.classification_adapter import ClassificationAdapter
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import MemoryFeatureFlagAdapter
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import (
    InMemoryRateLimitAdapter,
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
# Manager fixtures (in dependency order, M1-M16)
# ---------------------------------------------------------------------------


@pytest.fixture
def config_manager() -> AsyncLifecycle:
    """M1: ConfigManager with in-memory adapter."""
    adapter = InMemoryConfigAdapter()
    return _LifecycleWrapper(adapter, "config")


@pytest.fixture
def logger_manager() -> AsyncLifecycle:
    """M2: LoggerManager with in-memory adapter."""
    adapter = InMemoryLoggerAdapter()
    return _LifecycleWrapper(adapter, "logger")


@pytest.fixture
def secret_manager() -> AsyncLifecycle:
    """M3: SecretManager with in-memory adapter."""
    adapter = InMemorySecretAdapter()
    return _LifecycleWrapper(adapter, "secret")


@pytest.fixture
def observability_manager() -> AsyncLifecycle:
    """M4: ObservabilityManager with in-memory adapter."""
    adapter = InMemoryObservabilityAdapter()
    return _LifecycleWrapper(adapter, "observability")


@pytest.fixture
def error_manager(
    config_manager, logger_manager, observability_manager
) -> AsyncLifecycle:
    """M5: ErrorHandlingManager with ClassificationAdapter, wired with deps."""
    adapter = ClassificationAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        observability=observability_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "error")


@pytest.fixture
def auth_manager() -> AsyncLifecycle:
    """M6: AuthManager with StaticAuthAdapter."""
    claims = TokenClaims(
        sub="test-user",
        iss="cenf-test",
        aud="cenf-app",
        exp=9999999999,
        iat=1,
    )
    adapter = StaticAuthAdapter(default_claims=claims)
    return _LifecycleWrapper(adapter, "auth")


@pytest.fixture
def cache_manager(
    config_manager, logger_manager, error_manager
) -> AsyncLifecycle:
    """M7: CacheManager with MemoryCacheAdapter, wired with deps."""
    adapter = MemoryCacheAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        error_handler=error_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "cache")


@pytest.fixture
def database_manager(
    config_manager, logger_manager, observability_manager, error_manager
) -> AsyncLifecycle:
    """M8: DatabaseManager with MemoryDatabaseAdapter, wired with deps."""
    adapter = MemoryDatabaseAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        observability=observability_manager._adapter,
        error_handler=error_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "database")


@pytest.fixture
def filestorage_manager() -> AsyncLifecycle:
    """M9: FileStorageManager with MemoryStorageAdapter."""
    adapter = MemoryStorageAdapter()
    return _LifecycleWrapper(adapter, "filestorage")


@pytest.fixture
def taskqueue_manager() -> AsyncLifecycle:
    """M10: TaskQueueManager with MemoryTaskQueueAdapter."""
    adapter = MemoryTaskQueueAdapter()
    return _LifecycleWrapper(adapter, "taskqueue")


@pytest.fixture
def external_api_manager() -> AsyncLifecycle:
    """M11: ExternalAPIManager with MockHTTPAdapter."""
    adapter = MockHTTPAdapter()
    return _LifecycleWrapper(adapter, "external_api")


@pytest.fixture
def feature_flag_manager() -> AsyncLifecycle:
    """M12: FeatureFlagManager with MemoryFeatureFlagAdapter."""
    adapter = MemoryFeatureFlagAdapter()
    return _LifecycleWrapper(adapter, "feature_flags")


# ---------------------------------------------------------------------------
# M13-M16: Additional managers (alert, dependency, dynamic_prompting, ratelimit)
# ---------------------------------------------------------------------------


@pytest.fixture
def alert_manager(
    config_manager, secret_manager, logger_manager,
    external_api_manager, error_manager,
) -> AsyncLifecycle:
    """M13: AlertManager with DispatchAlertAdapter, wired with deps."""
    adapter = DispatchAlertAdapter(
        config=config_manager._adapter,
        secret_manager=secret_manager._adapter,
        logger=logger_manager._adapter,
        external_api=external_api_manager._adapter,
        error_handler=error_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "alert")


@pytest.fixture
def dependency_manager() -> AsyncLifecycle:
    """M14: DependencyManager with InMemoryDependencyAdapter."""
    adapter = InMemoryDependencyAdapter()
    return _LifecycleWrapper(adapter, "dependency")


@pytest.fixture
def dynamic_prompting_manager(
    config_manager, logger_manager, error_manager,
) -> AsyncLifecycle:
    """M15: DynamicPromptingManager with ConditionalPromptAdapter, wired with deps."""
    adapter = ConditionalPromptAdapter(
        config=config_manager._adapter,
        logger=logger_manager._adapter,
        error_handler=error_manager._adapter,
    )
    return _LifecycleWrapper(adapter, "dynamic_prompting")


@pytest.fixture
def ratelimit_manager() -> AsyncLifecycle:
    """M16: RateLimiterManager with InMemoryRateLimitAdapter."""
    adapter = InMemoryRateLimitAdapter(mode="always_allow")
    return _LifecycleWrapper(adapter, "ratelimit")


# ---------------------------------------------------------------------------
# Bootstrap orchestrator fixture — ALL 16 managers
# ---------------------------------------------------------------------------


@pytest.fixture
def bootstrap_orchestrator_16(
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
    alert_manager,
    dependency_manager,
    dynamic_prompting_manager,
    ratelimit_manager,
) -> BootstrapOrchestrator:
    """BootstrapOrchestrator wired with all 16 CENF managers in dependency order.

    Returns:
        BootstrapOrchestrator: Fully wired orchestrator with all 16 managers
            in dependency order (M1-M16).
    """
    return BootstrapOrchestrator(
        config_manager,          # M1
        logger_manager,          # M2
        secret_manager,          # M3
        observability_manager,   # M4
        error_manager,           # M5
        auth_manager,            # M6
        cache_manager,           # M7
        database_manager,        # M8
        filestorage_manager,     # M9
        taskqueue_manager,       # M10
        external_api_manager,    # M11
        feature_flag_manager,    # M12
        alert_manager,           # M13
        dependency_manager,      # M14
        dynamic_prompting_manager,  # M15
        ratelimit_manager,       # M16
    )
