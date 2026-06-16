"""ExternalAPIManager Protocol — the contract every HTTP client adapter must satisfy.

Defines the async HTTP client interface consumed by infrastructure managers
that need to communicate with external services. Includes circuit breaker
state inspection for resilience monitoring.

Security: Auth headers are handled by AuthManager, not by this Protocol.
    Never pass raw credentials in the headers dict — use AuthManager.
Observability: All requests auto-inject traceparent from contextvars.
    Elapsed_ms and status_code are emitted via ObservabilityManager.
@ai-directive: Circuit breaker is per-host — hosts are extracted from URL.
    get_circuit_state() is synchronous (reads cached state, no I/O).

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core_infrastructure.external_api.models import ApiResponse, CircuitState, RetryPolicy


@runtime_checkable
class ExternalAPIManager(Protocol):
    """Async HTTP client contract with circuit breaker and retry support.

    All infrastructure managers that need outbound HTTP communication
    consume this interface. Concrete adapters provide resilient HTTP
    with circuit breaking, retry, and trace context propagation.

    Rules:
        - request() is the core method — get() and post() are convenience wrappers.
        - All methods return ApiResponse — never raise on HTTP errors.
        - Circuit breaker opens after 5 consecutive failures per host.
        - OPEN → HALF_OPEN after 30s recovery timeout.
        - HALF_OPEN → CLOSED on first successful request.
        - Retryable statuses: 429, 502, 503, 504.
        - W3C trace context propagation via traceparent header.
    """

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> ApiResponse:
        """Execute an HTTP request with circuit breaker and retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.).
            url: Full request URL.
            headers: Optional request headers.
            body: Optional request body (JSON-serializable dict).
            timeout: Optional timeout in seconds (overrides default).
            retry_policy: Optional retry policy override.

        Returns:
            ApiResponse: The HTTP response (success or error).
        """
        ...

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ApiResponse:
        """Convenience method for HTTP GET requests.

        Args:
            url: Full request URL.
            headers: Optional request headers.
            timeout: Optional timeout in seconds.

        Returns:
            ApiResponse: The HTTP response.
        """
        ...

    async def post(
        self,
        url: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ApiResponse:
        """Convenience method for HTTP POST requests.

        Args:
            url: Full request URL.
            body: Optional request body (JSON-serializable dict).
            headers: Optional request headers.
            timeout: Optional timeout in seconds.

        Returns:
            ApiResponse: The HTTP response.
        """
        ...

    def get_circuit_state(self, host: str) -> CircuitState:
        """Get the current circuit breaker state for a host.

        Args:
            host: The hostname (extracted from URL).

        Returns:
            CircuitState: Current circuit state (CLOSED/OPEN/HALF_OPEN).
        """
        ...
