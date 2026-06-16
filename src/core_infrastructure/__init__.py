"""core_cenf — CENF Core Infrastructure (Python 3.12+).

Este paquete implementa los managers horizontales transversales reutilizables
para todos los desarrollos de CENF, siguiendo Clean Architecture / Hexagonal
y los principios SDD + TDD del estándar SOTA 2026.

Managers incluidos:
- ConfigManager: Fuente única de verdad para configuración
- LoggerManager: Logging estructurado multi-perfil
- SecretManager: Gestión segura de credenciales Zero-Trust
- ErrorHandlingManager: Clasificación y reporte de excepciones
- ObservabilityManager: Telemetría OpenTelemetry (RED Metrics, Tracing)
- AuthManager / IdentityManager: Validación técnica de tokens OIDC/JWT
- DatabaseManager: Pooling, Transacciones y Repositorios abstractos
- CacheManager: Abstracción KV con mitigación de Stampede
- FileStorageManager: Operaciones asíncronas de blobs
- TaskQueueManager: Orquestación asíncrona y DLQ
- ExternalAPIManager: Cliente HTTP resiliente con Circuit Breaker
- FeatureFlagManager: Activación dinámica en runtime
"""

from core_infrastructure.common.context import (
    ContextValidation,
    get_context_snapshot,
    get_correlation_id,
    get_principal_id,
    get_span_id,
    get_tenant_id,
    get_trace_id,
    new_correlation_id,
    restore_context_snapshot,
    set_correlation_id,
    set_principal_id,
    set_span_id,
    set_tenant_id,
    set_trace_id,
)
from core_infrastructure.common.errors import (
    AuthError,
    CenfError,
    ErrorType,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationError,
)
from core_infrastructure.common.lifecycle import AsyncLifecycle, HealthStatus, LifecycleManager
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.config.adapters.pydantic_config_adapter import PydanticConfigAdapter
from core_infrastructure.config.models import CoreSettings
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter
from core_infrastructure.logger.models import LoggerSettings
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.observability.adapters.noop_observability_adapter import (
    NoopObservabilityAdapter,
)
from core_infrastructure.observability.adapters.otel_adapter import OTelAdapter
from core_infrastructure.observability.models import ObservabilitySettings
from core_infrastructure.observability.ports import ObservabilityManager
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.errors.adapters.classification_adapter import ClassificationAdapter
from core_infrastructure.errors.models import ErrorClassification, ErrorContext, ErrorReport
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter
from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
from core_infrastructure.auth.models import AuthConfig, TokenClaims
from core_infrastructure.auth.ports import AuthManager
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter
from core_infrastructure.cache.models import CacheConfig, CacheEntry, StampedeConfig
from core_infrastructure.cache.ports import CacheManager
from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter
from core_infrastructure.database.models import DatabaseConfig, PaginatedResult, RepositoryQuery
from core_infrastructure.database.ports import DatabaseManager, GenericRepository, TransactionScope
from core_infrastructure.filestorage.adapters.local_storage_adapter import LocalStorageAdapter
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
from core_infrastructure.filestorage.models import FileRef, StorageConfig, UploadResult
from core_infrastructure.filestorage.ports import FileStorageManager
from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import (
    MemoryTaskQueueAdapter,
)
from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus, QueueConfig
from core_infrastructure.taskqueue.ports import TaskQueueManager
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter
from core_infrastructure.external_api.adapters.resilient_http_adapter import (
    ResilientHTTPAdapter,
)
from core_infrastructure.external_api.models import (
    ApiResponse,
    CircuitState,
    RequestConfig,
    RetryPolicy,
)
from core_infrastructure.external_api.ports import ExternalAPIManager
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FeatureFlag, FlagConfig, FlagContext
from core_infrastructure.feature_flags.ports import FeatureFlagManager

__version__ = "0.1.0-dev"
__all__ = [
    "ApiResponse",
    "AsyncLifecycle",
    "AuthConfig",
    "AuthError",
    "AuthManager",
    "CacheConfig",
    "CacheEntry",
    "CacheManager",
    "CapturingErrorAdapter",
    "CenfError",
    "CircuitState",
    "ClassificationAdapter",
    "ConfigManager",
    "ContextValidation",
    "CoreSettings",
    "DatabaseConfig",
    "DatabaseManager",
    "ErrorClassification",
    "ErrorContext",
    "ErrorHandlingManager",
    "ErrorReport",
    "ErrorType",
    "ExternalAPIManager",
    "FeatureFlag",
    "FeatureFlagManager",
    "FileRef",
    "FileStorageManager",
    "FlagConfig",
    "FlagContext",
    "GenericRepository",
    "HealthStatus",
    "InMemoryConfigAdapter",
    "InMemoryLoggerAdapter",
    "InMemoryObservabilityAdapter",
    "Job",
    "JobRef",
    "JobStatus",
    "JwtAuthAdapter",
    "LifecycleManager",
    "LocalStorageAdapter",
    "LoggerManager",
    "LoggerSettings",
    "MemoryCacheAdapter",
    "MemoryDatabaseAdapter",
    "MemoryFeatureFlagAdapter",
    "MemoryStorageAdapter",
    "MemoryTaskQueueAdapter",
    "MockHTTPAdapter",
    "NoopObservabilityAdapter",
    "OTelAdapter",
    "ObservabilityManager",
    "ObservabilitySettings",
    "PaginatedResult",
    "PermanentError",
    "PydanticConfigAdapter",
    "QueueConfig",
    "RateLimitError",
    "RedisCacheAdapter",
    "RepositoryQuery",
    "RequestConfig",
    "ResilientHTTPAdapter",
    "RetryPolicy",
    "SQLAlchemyAdapter",
    "SecretManager",
    "StampedeConfig",
    "StaticAuthAdapter",
    "StorageConfig",
    "StructlogAdapter",
    "TaskQueueManager",
    "TokenClaims",
    "TransactionScope",
    "TransientError",
    "UploadResult",
    "ValidationError",
    "get_context_snapshot",
    "get_correlation_id",
    "get_principal_id",
    "get_span_id",
    "get_tenant_id",
    "get_trace_id",
    "new_correlation_id",
    "restore_context_snapshot",
    "set_correlation_id",
    "set_principal_id",
    "set_span_id",
    "set_tenant_id",
    "set_trace_id",
]
