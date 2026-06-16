"""CENF LoggerManager — structured logging with structlog and contextvars injection.

Implements multi-profile logging: dev (colored console), test (silent/NullHandler),
and prod (JSON-structured output). Every log record automatically includes
correlation_id, tenant_id, trace_id, and span_id from contextvars.

Security: mask() truncates sensitive values before they reach log output.
Observability: All log records carry trace context for distributed tracing.
@ai-directive: All managers log exclusively through this module.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter
from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter
from core_infrastructure.logger.models import LoggerSettings
from core_infrastructure.logger.ports import LoggerManager

__all__ = [
    "InMemoryLoggerAdapter",
    "LoggerManager",
    "LoggerSettings",
    "StructlogAdapter",
]
