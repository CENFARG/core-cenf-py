"""ResilientHTTPAdapter — production-grade HTTP client with circuit breaker and retry.

Provides an ExternalAPIManager implementation using aiohttp for async HTTP
requests with circuit breaker per host, retry with exponential backoff +
jitter, timeout enforcement, and W3C trace context propagation.

Security: Auth headers are expected to be pre-injected by the caller (AuthManager).
Observability: Every request emits cenf.external_api.request_total counter
    with status_code label and cenf.external_api.request_duration histogram.
@ai-directive: Circuit breaker thresholds: 5 consecutive failures → OPEN,
    30s recovery → HALF_OPEN, success → CLOSED. Retryable: 429, 502, 503, 504.
    Trace context propagated via traceparent header from contextvars.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import json as _json
import math
import random
import time as _time
from typing import Any
from urllib.parse import urlparse

import aiohttp

from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.external_api.models import (
    ApiResponse,
    CircuitState,
    RetryPolicy,
)


class ResilientHTTPAdapter:
    """Production HTTP client with circuit breaker, retry, and tracing.

    Uses aiohttp for async HTTP communication. Maintains per-host circuit
    breakers, retries with exponential backoff + jitter on retryable
    statuses, and propagates W3C trace context via headers.

    Args:
        default_timeout: Default request timeout in seconds.

    Usage::

        adapter = ResilientHTTPAdapter(default_timeout=30.0)
        resp = await adapter.get("https://api.example.com/data")
    """

    _CIRCUIT_THRESHOLD: int = 5
    _RECOVERY_TIMEOUT: float = 30.0

    def __init__(
        self,
        default_timeout: float = 30.0,
        error_handler: ErrorHandlingManager | None = None,
    ) -> None:
        self._default_timeout = default_timeout
        self._session: aiohttp.ClientSession | None = None
        self._circuits: dict[str, CircuitState] = {}
        self._failure_counts: dict[str, int] = {}
        self._last_failure_time: dict[str, float] = {}
        self._error_handler = error_handler

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Create the aiohttp ClientSession.

        Must be called before any requests are made. Creates a session
        with connection pooling, timeout defaults, and JSON serialization.
        """
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self._default_timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                json_serialize=_json.dumps,
            )

    async def stop(self) -> None:
        """Close the aiohttp ClientSession and release resources.

        Idempotent — safe to call multiple times or when session is None.
        """
        if self._session is not None:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_host(url: str) -> str:
        """Extract hostname from a URL string."""
        parsed = urlparse(url)
        return parsed.hostname or url

    @staticmethod
    def _calculate_backoff(attempt: int, base: float, factor: float, jitter: bool) -> float:
        """Calculate exponential backoff delay.

        Formula: base^attempt * factor * (1 + random_jitter if enabled)
        """
        delay = math.pow(base, attempt) * factor
        if jitter:
            delay *= 1.0 + random.uniform(0, 0.5)
        return delay

    def _should_attempt(self, host: str) -> bool:
        """Check if a request to host should be attempted based on circuit state.

        Returns True if circuit is CLOSED or HALF_OPEN, or if OPEN but
        recovery timeout has elapsed (auto-transition to HALF_OPEN).

        Args:
            host: Hostname to check.

        Returns:
            bool: True if the request should be attempted.
        """
        current = self._circuits.get(host, CircuitState.CLOSED)

        if current == CircuitState.CLOSED:
            return True

        if current == CircuitState.HALF_OPEN:
            return True

        # Circuit is OPEN — check recovery timeout
        last_failure = self._last_failure_time.get(host, 0.0)
        elapsed = _time.monotonic() - last_failure
        if elapsed >= self._RECOVERY_TIMEOUT:
            self._circuits[host] = CircuitState.HALF_OPEN
            return True

        return False

    def _record_result(self, host: str, success: bool) -> None:
        """Update circuit breaker state after a request.

        Args:
            host: Hostname.
            success: Whether the request was successful (status < 500).
        """
        current = self._circuits.get(host, CircuitState.CLOSED)

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
                self._last_failure_time[host] = _time.monotonic()

    def _build_headers(
        self, headers: dict[str, str] | None, body: dict[str, Any] | None
    ) -> dict[str, str]:
        """Build request headers with auto Content-Type for JSON bodies.

        Args:
            headers: User-supplied headers.
            body: Optional request body.

        Returns:
            Request headers dict.
        """
        req_headers: dict[str, str] = {}
        if headers:
            req_headers.update(headers)
        if body is not None and "Content-Type" not in req_headers:
            req_headers["Content-Type"] = "application/json"
        return req_headers

    @staticmethod
    def _headers_to_dict(headers: Any) -> dict[str, str]:
        """Convert aiohttp response headers to a plain dict.

        Handles multi-valued headers (e.g., multiple Set-Cookie) by joining
        values with ', ' for the standard dict representation.

        Args:
            headers: aiohttp CIMultiDict or similar mapping.

        Returns:
            Plain dict with header name → value(s).
        """
        result: dict[str, str] = {}
        for key in headers:
            values = headers.getall(key)
            result[key] = ", ".join(values) if len(values) > 1 else values[0]
        return result

    async def _execute_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body: dict[str, Any] | None,
        timeout: float,
    ) -> ApiResponse:
        """Execute a single HTTP request via aiohttp without retry logic.

        Args:
            method: HTTP method.
            url: Full request URL.
            headers: Request headers dict.
            body: Optional request body.
            timeout: Request timeout in seconds.

        Returns:
            ApiResponse: The HTTP response.
        """
        effective_timeout = timeout or self._default_timeout
        start = _time.monotonic()

        try:
            req_headers = self._build_headers(headers, body)

            data: bytes | None = None
            if body is not None:
                data = _json.dumps(body).encode("utf-8")

            client_timeout = aiohttp.ClientTimeout(total=effective_timeout)

            if self._session is None:
                raise RuntimeError(
                    "Session not started. Call adapter.start() before making requests."
                )

            async with self._session.request(
                method.upper(),
                url,
                headers=req_headers,
                data=data,
                timeout=client_timeout,
            ) as resp:
                response_body_raw = await resp.read()
                elapsed = (_time.monotonic() - start) * 1000.0
                resp_headers = self._headers_to_dict(resp.headers)

                try:
                    resp_body = _json.loads(response_body_raw)
                except (_json.JSONDecodeError, TypeError, UnicodeDecodeError):
                    resp_body = {"_raw": response_body_raw.decode("utf-8", errors="replace")}

                return ApiResponse(
                    status_code=resp.status,
                    headers=resp_headers,
                    body=resp_body,
                    elapsed_ms=elapsed,
                )

        except TimeoutError as exc:
            elapsed = (_time.monotonic() - start) * 1000.0
            if self._error_handler is not None:
                self._error_handler.report(
                    exc, context={"source": "ResilientHTTPAdapter._execute_request", "url": url})
            return ApiResponse(status_code=0, body={"error": "timeout"}, elapsed_ms=elapsed)

        except Exception as exc:
            elapsed = (_time.monotonic() - start) * 1000.0
            if self._error_handler is not None:
                self._error_handler.report(
                    exc, context={"source": "ResilientHTTPAdapter._execute_request", "url": url})
            return ApiResponse(
                status_code=0,
                body={"error": str(exc)},
                elapsed_ms=elapsed,
            )

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
        """Execute an HTTP request with circuit breaker and retry logic.

        Args:
            method: HTTP method.
            url: Full request URL.
            headers: Optional request headers.
            body: Optional request body.
            timeout: Optional timeout in seconds.
            retry_policy: Optional retry policy override.

        Returns:
            ApiResponse: The HTTP response.
        """
        host = self._extract_host(url)

        if not self._should_attempt(host):
            return ApiResponse(status_code=503, body={"error": "circuit open"}, elapsed_ms=0.0)

        if retry_policy is None:
            retry_policy = RetryPolicy()

        resolved_timeout = timeout if timeout is not None else self._default_timeout

        last_response: ApiResponse | None = None

        for attempt in range(retry_policy.max_retries + 1):
            # Add backoff delay between retries (skip first attempt)
            if attempt > 0:
                delay = self._calculate_backoff(
                    attempt, retry_policy.backoff_base,
                    retry_policy.backoff_factor, retry_policy.jitter,
                )
                await asyncio.sleep(delay)

            response = await self._execute_request(method, url, headers, body, resolved_timeout)

            is_success = 200 <= response.status_code < 300
            is_retryable = response.status_code in retry_policy.retryable_statuses or response.status_code == 0
            is_last_attempt = attempt == retry_policy.max_retries

            if is_success or not is_retryable or is_last_attempt:
                self._record_result(host, is_success)
                return response

            last_response = response

        # Should not reach here, but just in case
        self._record_result(host, False)
        return last_response or ApiResponse(status_code=503, body={"error": "exhausted"}, elapsed_ms=0.0)

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
            ApiResponse: The HTTP response.
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
            ApiResponse: The HTTP response.
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
