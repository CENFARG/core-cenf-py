"""ExternalAPIManager adapter implementations.

- MockHTTPAdapter: Configurable mock responses for testing.
- ResilientHTTPAdapter: Production HTTP client with circuit breaker.
"""

from core_infrastructure.external_api.adapters.mock_http_adapter import (
    MockHTTPAdapter,
)
from core_infrastructure.external_api.adapters.resilient_http_adapter import (
    ResilientHTTPAdapter,
)

__all__ = ["MockHTTPAdapter", "ResilientHTTPAdapter"]
