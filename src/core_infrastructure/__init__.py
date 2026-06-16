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

__version__ = "0.1.0-dev"
__all__ = [
    "AsyncLifecycle",
    "AuthConfig",
    "AuthError",
    "AuthManager",
    "CacheManager",
    "CapturingErrorAdapter",
    "CenfError",
    "ClassificationAdapter",
    "ConfigManager",
    "ContextValidation",
    "CoreSettings",
    "DatabaseManager",
    "ErrorClassification",
    "ErrorContext",
    "ErrorHandlingManager",
    "ErrorReport",
    "ErrorType",
    "ExternalAPIManager",
    "FeatureFlagManager",
    "FileStorageManager",
    "HealthStatus",
    "InMemoryConfigAdapter",
    "InMemoryLoggerAdapter",
    "InMemoryObservabilityAdapter",
    "JwtAuthAdapter",
    "LifecycleManager",
    "LoggerManager",
    "LoggerSettings",
    "NoopObservabilityAdapter",
    "OTelAdapter",
    "ObservabilityManager",
    "ObservabilitySettings",
    "PermanentError",
    "PydanticConfigAdapter",
    "RateLimitError",
    "SecretManager",
    "StaticAuthAdapter",
    "StructlogAdapter",
    "TaskQueueManager",
    "TokenClaims",
    "TransientError",
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
