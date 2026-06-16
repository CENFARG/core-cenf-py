"""CENF ExternalAPIManager models — ApiResponse, CircuitState, RetryPolicy, RequestConfig.

Defines the Pydantic models for the external API client: HTTP response
representation, circuit breaker states, retry policy configuration, and
request bundling.

Security: ApiResponse.body is untyped (Any) — callers MUST validate response
    bodies before use. Never log full response bodies without sanitization.
Observability: Every request/response is logged at DEBUG level with status_code
    and elapsed_ms. Circuit transitions emit counters under cenf.external_api.*.
@ai-directive: Circuit breaker thresholds are set per-host. Retryable statuses
    (429, 502, 503, 504) are configured via RetryPolicy.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CircuitState(StrEnum):
    """Circuit breaker states for per-host failure tracking.

    Transitions:
        CLOSED → OPEN (after threshold consecutive failures)
        OPEN → HALF_OPEN (after recovery timeout)
        HALF_OPEN → CLOSED (on successful request)
        HALF_OPEN → OPEN (on failure)
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ApiResponse(BaseModel):
    """HTTP response from an external API call.

    Represents the complete response: status code, headers, body, and
    elapsed time. Used for both successful and error responses.

    Attributes:
        status_code: HTTP status code (0 for connection errors).
        headers: Response headers as a dict.
        body: Parsed response body (dict or other).
        elapsed_ms: Request duration in milliseconds.
    """

    status_code: int = Field(..., ge=0, description="HTTP status code.")
    headers: dict[str, str] = Field(default_factory=dict, description="Response headers.")
    body: Any = Field(default=None, description="Parsed response body.")
    elapsed_ms: float = Field(default=0.0, ge=0, description="Request duration in ms.")


class RetryPolicy(BaseModel):
    """Retry policy for HTTP request retries with exponential backoff.

    Controls retry behavior on transient failures. Only retryable statuses
    (429, 502, 503, 504 by default) trigger retries. Exponential backoff
    with optional jitter prevents thundering herd on recovery.

    Attributes:
        max_retries: Maximum number of retry attempts.
        backoff_base: Base for exponential backoff (delay = base^attempt * factor).
        backoff_factor: Multiplier for backoff calculation.
        jitter: Whether to add random jitter to backoff delays.
        retryable_statuses: HTTP status codes that trigger a retry.
    """

    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts.")
    backoff_base: float = Field(default=2.0, gt=0, description="Base for exponential backoff.")
    backoff_factor: float = Field(default=1.0, gt=0, description="Multiplier for backoff.")
    jitter: bool = Field(default=True, description="Add random jitter to backoff delays.")
    retryable_statuses: list[int] = Field(
        default=[429, 502, 503, 504],
        description="HTTP status codes that trigger retries.",
    )


class RequestConfig(BaseModel):
    """Bundled configuration for an HTTP request.

    Combines method, URL, headers, body, timeout, and retry policy into
    a single object for use with the ExternalAPIManager.request() method.

    Attributes:
        method: HTTP method (GET, POST, PUT, DELETE, etc.).
        url: Full request URL.
        headers: Request headers dict.
        body: Optional request body (will be JSON-encoded).
        timeout: Request timeout in seconds.
        retry_policy: Retry policy for this request.
    """

    method: str = Field(..., min_length=1, max_length=16, description="HTTP method.")
    url: str = Field(..., min_length=1, max_length=2048, description="Full request URL.")
    headers: dict[str, str] = Field(default_factory=dict, description="Request headers.")
    body: dict[str, Any] | None = Field(default=None, description="Optional request body.")
    timeout: float = Field(default=30.0, gt=0, description="Request timeout in seconds.")
    retry_policy: RetryPolicy = Field(
        default_factory=RetryPolicy,
        description="Retry policy for this request.",
    )
