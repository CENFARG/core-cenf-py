"""ExternalAPIManager — resilient HTTP client with circuit breaker and retry.

Provides the ExternalAPIManager Protocol contract and adapters for
development/testing (MockHTTPAdapter) and production (ResilientHTTPAdapter).
"""

from core_infrastructure.external_api.adapters.mock_http_adapter import (
    MockHTTPAdapter,
)
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

__all__ = [
    "ApiResponse",
    "CircuitState",
    "ExternalAPIManager",
    "MockHTTPAdapter",
    "RequestConfig",
    "ResilientHTTPAdapter",
    "RetryPolicy",
]
