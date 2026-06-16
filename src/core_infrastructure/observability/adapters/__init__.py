"""Observability adapters — concrete implementations of ObservabilityManager Protocol.

- OTelAdapter: Production adapter using OpenTelemetry SDK.
- InMemoryObservabilityAdapter: Test double that collects metrics/spans in memory.
- NoopObservabilityAdapter: No-op for tests that don't need observability assertions.

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

__all__ = [
    "InMemoryObservabilityAdapter",
    "NoopObservabilityAdapter",
    "OTelAdapter",
]
