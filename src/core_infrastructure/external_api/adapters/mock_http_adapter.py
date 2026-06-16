"""MockHTTPAdapter — configurable mock HTTP adapter for testing.

Provides a fully-configurable ExternalAPIManager implementation that returns
predefined responses without making real HTTP requests. Supports:
- Per-method+URL response configuration
- Response sequences (multiple successive responses for the same endpoint)
- Circuit breaker state injection and recovery simulation
- Timeout simulation

Security: This adapter exists for testing only. NEVER use in production.
Observability: Circuit transitions are tracked per-host.
@ai-directive: Mock adapter supports all circuit breaker transitions including
    manual state injection via set_circuit_state() and force_recovery().

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import time as _time
from typing import Any
from urllib.parse import urlparse

from core_infrastructure.external_api.models import (
    ApiResponse,
    CircuitState,
    RetryPolicy,
)


class MockHTTPAdapter:
    """Configurable mock HTTP adapter for unit testing.

    Returns predefined responses based on method+URL matching. Supports
    circuit breaker state transitions, response sequences, and timeout
    simulation.

    Usage::

        adapter = MockHTTPAdapter()
        adapter.set_response("GET", "https://api.example.com/data",
                           status_code=200, body={"ok": True})
        resp = await adapter.get("https://api.example.com/data")
    """

    _CIRCUIT_THRESHOLD = 5
    _RECOVERY_TIMEOUT = 30.0

    def __init__(self) -> None:
        # Response store: key = (method, url) → (status_code, body, headers)
        self._responses: dict[tuple[str, str], tuple[int, Any, dict[str, str]]] = {}
        # Sequence store: key → list of (status_code, body)
        self._sequences: dict[tuple[str, str], list[tuple[int, Any]]] = {}
        self._sequence_index: dict[tuple[str, str], int] = {}
        # Circuit breaker state per host
        self._circuits: dict[str, CircuitState] = {}
        self._failure_counts: dict[str, int] = {}
        self._last_failure_time: dict[str, float] = {}
        self._recovery_forced: dict[str, bool] = {}
        # Timeout simulation
        self._timeouts: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Configuration API
    # ------------------------------------------------------------------

    def set_response(
        self,
        method: str,
        url: str,
        *,
        status_code: int,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Configure a response for a specific method+URL.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full request URL.
            status_code: HTTP status code to return.
            body: Response body (default None → empty dict).
            headers: Response headers (default empty dict).
        """
        self._responses[(method.upper(), url)] = (
            status_code,
            body if body is not None else {},
            headers if headers is not None else {},
        )

    def set_response_sequence(
        self,
        method: str,
        url: str,
        responses: list[tuple[int, Any]],
    ) -> None:
        """Configure a sequence of responses for repeated calls.

        Each call to the same method+URL returns the next response in
        the sequence. After exhaustion, the last response repeats.

        Args:
            method: HTTP method.
            url: Full request URL.
            responses: List of (status_code, body) tuples.
        """
        key = (method.upper(), url)
        self._sequences[key] = responses
        self._sequence_index[key] = 0

    def set_circuit_state(self, host: str, state: CircuitState) -> None:
        """Manually set the circuit breaker state for a host.

        Args:
            host: Hostname to set state for.
            state: Desired circuit state.
        """
        self._circuits[host] = state

    def force_recovery(self, host: str) -> None:
        """Force a host's circuit from OPEN to HALF_OPEN.

        Simulates the recovery timeout expiring.

        Args:
            host: Hostname to force recovery for.
        """
        self._recovery_forced[host] = True
        self._circuits[host] = CircuitState.HALF_OPEN

    def set_timeout(self, url: str, timeout_seconds: float) -> None:
        """Configure a timeout threshold for a URL.

        Args:
            url: URL that should simulate a timeout.
            timeout_seconds: Request duration that triggers timeout.
        """
        self._timeouts[url] = timeout_seconds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_host(url: str) -> str:
        """Extract hostname from a URL string.

        Args:
            url: Full URL string.

        Returns:
            str: Hostname extracted from the URL.
        """
        parsed = urlparse(url)
        return parsed.hostname or url

    def _get_response(
        self, method: str, url: str
    ) -> tuple[int, Any, dict[str, str]]:
        """Get the configured response for a method+URL.

        Checks sequences first, then single responses, then default.

        Args:
            method: HTTP method.
            url: Full request URL.

        Returns:
            tuple: (status_code, body, headers).
        """
        key = (method.upper(), url)

        # Check sequences
        if key in self._sequences:
            seq = self._sequences[key]
            idx = self._sequence_index[key]
            if idx < len(seq):
                status, body = seq[idx]
                self._sequence_index[key] = idx + 1
                return status, body, {}
            else:
                # Exhausted — repeat last response
                status, body = seq[-1]
                return status, body, {}

        # Check single responses
        if key in self._responses:
            return self._responses[key]

        # Default
        return 200, {}, {}

    def _update_circuit(self, host: str, success: bool) -> None:
        """Update circuit breaker state after a request.

        Args:
            host: Hostname for the circuit.
            success: Whether the request succeeded.
        """
        current: CircuitState = self._circuits.get(host, CircuitState.CLOSED)

        if current == CircuitState.OPEN:
            # Check recovery
            if host in self._recovery_forced:
                current = CircuitState.HALF_OPEN
                del self._recovery_forced[host]
                self._circuits[host] = current
            else:
                return  # Still OPEN — reject

        if current == CircuitState.CLOSED:
            if success:
                self._failure_counts[host] = 0
            else:
                self._failure_counts[host] = self._failure_counts.get(host, 0) + 1
                if self._failure_counts[host] >= self._CIRCUIT_THRESHOLD:
                    self._circuits[host] = CircuitState.OPEN
                    self._last_failure_time[host] = _time.monotonic()

        elif current == CircuitState.HALF_OPEN:
            if success:
                self._circuits[host] = CircuitState.CLOSED
                self._failure_counts[host] = 0
            else:
                self._circuits[host] = CircuitState.OPEN

    # ------------------------------------------------------------------
    # Public API — ExternalAPIManager Protocol
    # ------------------------------------------------------------------

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> ApiResponse:
        """Execute a mock HTTP request with circuit breaker and retry.

        Args:
            method: HTTP method.
            url: Full request URL.
            headers: Optional request headers.
            body: Optional request body.
            timeout: Optional timeout in seconds.
            retry_policy: Optional retry policy.

        Returns:
            ApiResponse: The mock response.
        """
        host = self._extract_host(url)

        # Check if circuit is OPEN
        circuit = self._circuits.get(host, CircuitState.CLOSED)
        if circuit == CircuitState.OPEN and host not in self._recovery_forced:
            return ApiResponse(status_code=503, body={"error": "circuit open"}, elapsed_ms=0.0)

        # Determine retry policy
        if retry_policy is None:
            retry_policy = RetryPolicy()

        # Timeout simulation
        if url in self._timeouts:
            sim_timeout = self._timeouts[url]
            if timeout is not None and timeout < sim_timeout:
                return ApiResponse(status_code=0, body={"error": "timeout"}, elapsed_ms=timeout * 1000)

        # Attempt with retries
        last_response: ApiResponse | None = None
        for attempt in range(retry_policy.max_retries + 1):
            status, resp_body, resp_headers = self._get_response(method, url)

            is_success = 200 <= status < 300
            is_retryable = status in retry_policy.retryable_statuses
            is_last_attempt = attempt == retry_policy.max_retries

            if is_success or not is_retryable or is_last_attempt:
                self._update_circuit(host, is_success)
                return ApiResponse(
                    status_code=status,
                    body=resp_body,
                    headers=resp_headers,
                    elapsed_ms=1.0,
                )

            last_response = ApiResponse(status_code=status, body=resp_body, headers=resp_headers, elapsed_ms=1.0)

        # Exhausted retries
        self._update_circuit(host, False)
        return last_response or ApiResponse(status_code=503, body={"error": "exhausted"}, elapsed_ms=1.0)

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ApiResponse:
        """Convenience method for HTTP GET.

        Args:
            url: Full request URL.
            headers: Optional request headers.
            timeout: Optional timeout in seconds.

        Returns:
            ApiResponse: The mock response.
        """
        return await self.request("GET", url, headers=headers, timeout=timeout)

    async def post(
        self,
        url: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> ApiResponse:
        """Convenience method for HTTP POST.

        Args:
            url: Full request URL.
            body: Optional request body.
            headers: Optional request headers.
            timeout: Optional timeout in seconds.

        Returns:
            ApiResponse: The mock response.
        """
        return await self.request("POST", url, headers=headers, body=body, timeout=timeout)

    def get_circuit_state(self, host: str) -> CircuitState:
        """Get the current circuit breaker state for a host.

        Args:
            host: Hostname.

        Returns:
            CircuitState: Current circuit state.
        """
        return self._circuits.get(host, CircuitState.CLOSED)
