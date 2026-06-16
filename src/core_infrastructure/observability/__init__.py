"""CENF ObservabilityManager — OpenTelemetry-based telemetry and tracing.

Implements distributed tracing and RED metrics (Rate, Errors, Duration)
with graceful degradation. Supports dev mode (console exporter) and
prod mode (OTLP exporter). Trace context is synced to contextvars
for downstream LoggerManager injection.

Security: No PII, credentials, or session tokens in span attributes.
Observability: All counters and spans use the ``cenf.*`` namespace.
@ai-directive: All managers emit telemetry exclusively through this module.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)
from core_infrastructure.observability.adapters.noop_observability_adapter import (
    NoopObservabilityAdapter,
)
from core_infrastructure.observability.adapters.otel_adapter import OTelAdapter
from core_infrastructure.observability.models import ObservabilitySettings
from core_infrastructure.observability.ports import ObservabilityManager

__all__ = [
    "InMemoryObservabilityAdapter",
    "NoopObservabilityAdapter",
    "OTelAdapter",
    "ObservabilityManager",
    "ObservabilitySettings",
]
