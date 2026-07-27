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
- DependencyManager: Resolución lazy y validada de dependencias via importlib
- RateLimiterManager: Rate limiting con Token Bucket y Sliding Window
- DynamicPromptingManager: Ensamblado condicional de system prompts
- AlertManager: Despacho multi-canal de alertas (Slack/Discord/Email)

Import strategy (two-layer lazy protection):
1. Root level: all optional adapter imports wrapped in try/except ImportError.
2. Sub-package level (database/__init__.py, filestorage/__init__.py): same pattern,
   ensuring the import chain never crashes before the root blocks execute.

If an optional dependency is missing, the adapter symbol is set to None.
Always check `is None` before using an optional adapter:
    from core_infrastructure.database import SQLAlchemyAdapter
    if SQLAlchemyAdapter is None:
        ...handle gracefully...
"""

# ---------------------------------------------------------------------------
# Safe imports — always available (Protocols + models, zero optional deps)
# ---------------------------------------------------------------------------

from core_infrastructure.alert.models import AlertChannel, AlertConfig
from core_infrastructure.alert.ports import AlertLevel, AlertManager, AlertRule
from core_infrastructure.auth.models import AuthConfig, TokenClaims
from core_infrastructure.auth.ports import AuthManager
from core_infrastructure.bootstrap import BootstrapOrchestrator
from core_infrastructure.cache.models import CacheConfig, CacheEntry, StampedeConfig
from core_infrastructure.cache.ports import CacheManager
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

# ---------------------------------------------------------------------------
# Always-available adapters (zero optional deps)
# ---------------------------------------------------------------------------
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.config.adapters.pydantic_config_adapter import PydanticConfigAdapter
from core_infrastructure.config.models import CoreSettings
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.database.models import DatabaseConfig, PaginatedResult, RepositoryQuery
from core_infrastructure.database.ports import DatabaseManager, GenericRepository, TransactionScope
from core_infrastructure.dependency.models import DependencyConfig, RegistryEntry
from core_infrastructure.dependency.ports import DependencyManager
from core_infrastructure.dynamic_prompting.models import PromptConfig
from core_infrastructure.dynamic_prompting.ports import DynamicPromptingManager, PromptBlock
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.errors.adapters.classification_adapter import ClassificationAdapter
from core_infrastructure.errors.models import ErrorClassification, ErrorContext, ErrorReport
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.external_api.models import (
    ApiResponse,
    CircuitState,
    RequestConfig,
    RetryPolicy,
)
from core_infrastructure.external_api.ports import ExternalAPIManager
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import MemoryFeatureFlagAdapter
from core_infrastructure.feature_flags.models import FeatureFlag, FlagConfig, FlagContext
from core_infrastructure.feature_flags.ports import FeatureFlagManager
from core_infrastructure.file_reader.ports import FileReaderPort
from core_infrastructure.filestorage.models import FileRef, StorageConfig, UploadResult
from core_infrastructure.filestorage.ports import FileStorageManager
from core_infrastructure.i18n.adapters.in_memory_i18n_adapter import InMemoryI18nAdapter
from core_infrastructure.i18n.adapters.yaml_i18n_adapter import YamlI18nAdapter
from core_infrastructure.i18n.models import I18nConfig
from core_infrastructure.i18n.ports import I18nManager
from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
    InMemoryLicenceAdapter,
)

# Licence Manager (Protocols + models — zero optional deps)
from core_infrastructure.licence.models import LicenceConfig, LicenseClaims
from core_infrastructure.licence.ports import LicenceManager, LicenseInfo
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
from core_infrastructure.observability.models import ObservabilitySettings
from core_infrastructure.observability.ports import ObservabilityManager
from core_infrastructure.permission.adapters.in_memory_permission_adapter import (
    InMemoryPermissionAdapter,
)
from core_infrastructure.permission.models import (
    DelegationRecord,
    PermissionConfig,
    PermissionResult,
)
from core_infrastructure.permission.ports import (
    Action,
    PermissionDecision,
    PermissionManager,
    PrincipalType,
)
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import InMemoryRateLimitAdapter
from core_infrastructure.ratelimit.adapters.token_bucket_adapter import TokenBucketAdapter
from core_infrastructure.ratelimit.models import BucketState, RateLimitConfig, RateLimitHeaders
from core_infrastructure.ratelimit.ports import RateLimiterManager
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter
from core_infrastructure.secrets.models import SecretConfig, SecretRef, SecretValue
from core_infrastructure.secrets.ports import SecretManager
from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus, QueueConfig
from core_infrastructure.taskqueue.ports import TaskQueueManager

# InMemoryUpdateAdapter (zero optional deps)
from core_infrastructure.update.adapters.in_memory_update_adapter import (
    InMemoryUpdateAdapter,
)

# Update Manager (Protocols + models — zero optional deps)
from core_infrastructure.update.models import (
    ArtifactMeta,
    ReleaseMetadata,
    RollbackState,
    UpdateConfig,
)
from core_infrastructure.update.ports import (
    AvailableRelease,
    Channel,
    UpdateArtifact,
    UpdateManager,
    UpdateResult,
)

# ---------------------------------------------------------------------------
# Optional adapters — gracefully degrade if optional deps are missing
# ---------------------------------------------------------------------------

# Auth adapters (need: python-jose)
try:
    from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter
    from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
except ImportError:
    JwtAuthAdapter = None  # type: ignore[assignment,misc]
    StaticAuthAdapter = None  # type: ignore[assignment,misc]

# Licence adapters (need: python-jose)
try:
    from core_infrastructure.licence.adapters.jwt_licence_adapter import (
        JwtLicenceAdapter,
    )
except ImportError:
    JwtLicenceAdapter = None  # type: ignore[assignment,misc]

# Cache adapters (need: redis)
try:
    from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
except ImportError:
    MemoryCacheAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.cache.adapters.redis_cache_adapter import RedisCacheAdapter
except ImportError:
    RedisCacheAdapter = None  # type: ignore[assignment,misc]

# Database adapters (need: sqlalchemy, asyncpg)
try:
    from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
except ImportError:
    MemoryDatabaseAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.database.adapters.sqlalchemy_adapter import SQLAlchemyAdapter
except ImportError:
    SQLAlchemyAdapter = None  # type: ignore[assignment,misc]

# Secret adapters (need: cryptography)
try:
    from core_infrastructure.secrets.adapters.encrypted_secret_adapter import EncryptedSecretAdapter
except ImportError:
    EncryptedSecretAdapter = None  # type: ignore[assignment,misc]

# Observability adapters (need: opentelemetry)
try:
    from core_infrastructure.observability.adapters.otel_adapter import OTelAdapter
except ImportError:
    OTelAdapter = None  # type: ignore[assignment,misc]

# External API adapters (need: aiohttp, tenacity)
try:
    from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter
except ImportError:
    MockHTTPAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.external_api.adapters.resilient_http_adapter import ResilientHTTPAdapter
except ImportError:
    ResilientHTTPAdapter = None  # type: ignore[assignment,misc]

# File reader adapter (need: aiofiles)
try:
    from core_infrastructure.file_reader.adapters.local_file_reader_adapter import (
        LocalFileReaderAdapter,
    )
except ImportError:
    LocalFileReaderAdapter = None  # type: ignore[assignment,misc]

# File storage adapters (need: aiofiles, aiobotocore, gcloud-aio-storage, azure-storage-blob)
try:
    from core_infrastructure.filestorage.adapters.local_storage_adapter import LocalStorageAdapter
except ImportError:
    LocalStorageAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
except ImportError:
    MemoryStorageAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.filestorage.adapters.s3_storage_adapter import S3StorageAdapter
except ImportError:
    S3StorageAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.filestorage.adapters.gcs_storage_adapter import GcsStorageAdapter
except ImportError:
    GcsStorageAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.filestorage.adapters.azure_storage_adapter import AzureStorageAdapter
except ImportError:
    AzureStorageAdapter = None  # type: ignore[assignment,misc]

# Task queue adapters (no optional deps for memory adapter)
try:
    from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import MemoryTaskQueueAdapter
except ImportError:
    MemoryTaskQueueAdapter = None  # type: ignore[assignment,misc]

# Dependency adapters (no optional deps)
try:
    from core_infrastructure.dependency.adapters.importlib_dependency_adapter import (
        ImportlibDependencyAdapter,
    )
except ImportError:
    ImportlibDependencyAdapter = None  # type: ignore[assignment,misc]

try:
    from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import (
        InMemoryDependencyAdapter,
    )
except ImportError:
    InMemoryDependencyAdapter = None  # type: ignore[assignment,misc]

# Dynamic prompting adapters
try:
    from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import (
        ConditionalPromptAdapter,
    )
except ImportError:
    ConditionalPromptAdapter = None  # type: ignore[assignment,misc]

# Alert adapters
try:
    from core_infrastructure.alert.adapters.dispatch_alert_adapter import DispatchAlertAdapter
except ImportError:
    DispatchAlertAdapter = None  # type: ignore[assignment,misc]

# Permission adapters (need: pycasbin)
try:
    from core_infrastructure.permission.adapters.casbin_permission_adapter import (
        CasbinPermissionAdapter,
    )
except ImportError:
    CasbinPermissionAdapter = None  # type: ignore[assignment,misc]

# Feature flag adapters (need: watchfiles, pyyaml)
try:
    from core_infrastructure.feature_flags.adapters.file_feature_flag_adapter import (
        FileFeatureFlagAdapter,
    )
except ImportError:
    FileFeatureFlagAdapter = None  # type: ignore[assignment,misc]

# Update adapters (need: cryptography, ExternalAPIManager)
try:
    from core_infrastructure.update.adapters.http_update_adapter import (
        HttpUpdateAdapter,
    )
except ImportError:
    HttpUpdateAdapter = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Package metadata
# ---------------------------------------------------------------------------

__version__ = "0.1.2"
