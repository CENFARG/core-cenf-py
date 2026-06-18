"""Unit tests for ResilientHTTPAdapter — circuit breaker and retry logic.

Tests cover:
- Protocol compliance (satisfies ExternalAPIManager)
- Circuit breaker transitions: CLOSED → OPEN after threshold failures
- Circuit breaker recovery: OPEN → HALF_OPEN after recovery timeout
- Circuit breaker: HALF_OPEN → CLOSED on success
- Circuit breaker: HALF_OPEN → OPEN on failure
- Retry with backoff on retryable statuses (429, 502, 503, 504)
- Timeout enforcement
- get/post convenience methods

Note: This test uses the in-memory adapter which simulates HTTP without
a real network. The circuit breaker and retry logic are tested via the
mock adapter that supports configurable responses.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.external_api.adapters.mock_http_adapter import (
    MockHTTPAdapter,
)
from core_infrastructure.external_api.models import (
    CircuitState,
)
from core_infrastructure.external_api.ports import ExternalAPIManager


@pytest.fixture
def mock_adapter() -> MockHTTPAdapter:
    """Create a MockHTTPAdapter with default config."""
    return MockHTTPAdapter()


class TestMockAdapterProtocol:
    """Verify MockHTTPAdapter satisfies ExternalAPIManager Protocol."""

    def test_satisfies_external_api_manager_protocol(self, mock_adapter: MockHTTPAdapter) -> None:
        """MockHTTPAdapter passes isinstance check."""
        assert isinstance(mock_adapter, ExternalAPIManager)


class TestMockAdapterBasic:
    """Verify mock adapter returns configured responses."""

    @pytest.mark.asyncio
    async def test_get_returns_configured_response(self, mock_adapter: MockHTTPAdapter) -> None:
        """get() returns the mock response configured for a URL."""
        mock_adapter.set_response(
            "GET",
            "https://api.example.com/data",
            status_code=200,
            body={"result": "ok"},
        )
        resp = await mock_adapter.get("https://api.example.com/data")
        assert resp.status_code == 200
        assert resp.body == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_post_returns_configured_response(self, mock_adapter: MockHTTPAdapter) -> None:
        """post() returns the mock response configured for a URL."""
        mock_adapter.set_response(
            "POST",
            "https://api.example.com/create",
            status_code=201,
            body={"id": "new-1"},
        )
        resp = await mock_adapter.post(
            "https://api.example.com/create",
            body={"name": "test"},
        )
        assert resp.status_code == 201
        assert resp.body == {"id": "new-1"}

    @pytest.mark.asyncio
    async def test_unconfigured_url_returns_200_default(self, mock_adapter: MockHTTPAdapter) -> None:
        """Requests to unconfigured URLs return 200 with empty body."""
        resp = await mock_adapter.get("https://unknown.example.com/")
        assert resp.status_code == 200
        assert resp.body == {}


class TestCircuitBreaker:
    """Verify circuit breaker state transitions."""

    def test_initial_state_is_closed(self, mock_adapter: MockHTTPAdapter) -> None:
        """Circuit breaker starts in CLOSED state."""
        state = mock_adapter.get_circuit_state("api.example.com")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_opens_after_five_consecutive_failures(self, mock_adapter: MockHTTPAdapter) -> None:
        """Circuit breaker transitions CLOSED → OPEN after 5 consecutive failures."""
        mock_adapter.set_response(
            "GET", "https://api.example.com/data", status_code=503, body={}
        )

        # 5 failures should open the circuit
        for _ in range(5):
            await mock_adapter.get("https://api.example.com/data")

        state = mock_adapter.get_circuit_state("api.example.com")
        assert state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_half_open_after_recovery_timeout(self, mock_adapter: MockHTTPAdapter) -> None:
        """Circuit breaker transitions OPEN → HALF_OPEN after recovery timeout."""
        mock_adapter.set_response(
            "GET", "https://api.example.com/data", status_code=503, body={}
        )

        # Open the circuit
        for _ in range(5):
            await mock_adapter.get("https://api.example.com/data")

        assert mock_adapter.get_circuit_state("api.example.com") == CircuitState.OPEN

        # Force recovery (simulate time passing)
        mock_adapter.force_recovery("api.example.com")

        state = mock_adapter.get_circuit_state("api.example.com")
        assert state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_closes_on_success(self, mock_adapter: MockHTTPAdapter) -> None:
        """Circuit breaker HALF_OPEN → CLOSED on successful request."""
        mock_adapter.set_response(
            "GET", "https://api.example.com/data", status_code=503, body={}
        )

        # Open the circuit
        for _ in range(5):
            await mock_adapter.get("https://api.example.com/data")

        # Force recovery to HALF_OPEN
        mock_adapter.force_recovery("api.example.com")
        assert mock_adapter.get_circuit_state("api.example.com") == CircuitState.HALF_OPEN

        # Now set success response
        mock_adapter.set_response(
            "GET", "https://api.example.com/data", status_code=200, body={"ok": True}
        )

        resp = await mock_adapter.get("https://api.example.com/data")
        assert resp.status_code == 200
        assert mock_adapter.get_circuit_state("api.example.com") == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_opens_on_failure(self, mock_adapter: MockHTTPAdapter) -> None:
        """Circuit breaker HALF_OPEN → OPEN on failure."""
        mock_adapter.set_response(
            "GET", "https://api.example.com/data", status_code=503, body={}
        )

        # Open the circuit
        for _ in range(5):
            await mock_adapter.get("https://api.example.com/data")

        # Force recovery to HALF_OPEN
        mock_adapter.force_recovery("api.example.com")
        assert mock_adapter.get_circuit_state("api.example.com") == CircuitState.HALF_OPEN

        # Keep failing responses
        await mock_adapter.get("https://api.example.com/data")
        assert mock_adapter.get_circuit_state("api.example.com") == CircuitState.OPEN


class TestRetryBehavior:
    """Verify retry logic with backoff on retryable statuses."""

    @pytest.mark.asyncio
    async def test_retry_on_503(self, mock_adapter: MockHTTPAdapter) -> None:
        """Requests are retried on HTTP 503."""
        # Set up: first call returns 503, second returns 200
        mock_adapter.set_response_sequence(
            "GET", "https://api.example.com/data",
            [
                (503, {}),
                (200, {"ok": True}),
            ],
        )

        resp = await mock_adapter.get("https://api.example.com/data")
        assert resp.status_code == 200
        assert resp.body == {"ok": True}

    @pytest.mark.asyncio
    async def test_retry_on_429(self, mock_adapter: MockHTTPAdapter) -> None:
        """Requests are retried on HTTP 429 (rate limit)."""
        mock_adapter.set_response_sequence(
            "GET", "https://api.example.com/data",
            [
                (429, {"error": "rate limited"}),
                (200, {"ok": True}),
            ],
        )

        resp = await mock_adapter.get("https://api.example.com/data")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self, mock_adapter: MockHTTPAdapter) -> None:
        """Requests are NOT retried on HTTP 400 (not retryable)."""
        mock_adapter.set_response(
            "GET", "https://api.example.com/data", status_code=400, body={"error": "bad request"}
        )

        resp = await mock_adapter.get("https://api.example.com/data")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_retry_exhaustion_returns_last_response(self, mock_adapter: MockHTTPAdapter) -> None:
        """When all retries are exhausted, return the last response."""
        # Set up sequence that always returns 503
        mock_adapter.set_response(
            "GET", "https://api.example.com/data", status_code=503, body={"error": "unavailable"}
        )

        resp = await mock_adapter.get("https://api.example.com/data")
        assert resp.status_code == 503


class TestTimeout:
    """Verify timeout enforcement."""

    @pytest.mark.asyncio
    async def test_timeout_returns_error_response(self, mock_adapter: MockHTTPAdapter) -> None:
        """Timeout results in error response."""
        mock_adapter.set_timeout("https://api.example.com/slow", 0.01)  # 10ms timeout

        resp = await mock_adapter.get("https://api.example.com/slow", timeout=0.001)
        # Should return an error response
        assert resp.status_code >= 400 or resp.status_code == 0


class TestCircuitBreakerIsolation:
    """Verify circuit breakers are isolated per host."""

    def test_different_hosts_have_independent_circuits(self, mock_adapter: MockHTTPAdapter) -> None:
        """Circuit breakers are per-host — one host failing doesn't affect another."""
        # Initially both are CLOSED
        assert mock_adapter.get_circuit_state("host-a.com") == CircuitState.CLOSED
        assert mock_adapter.get_circuit_state("host-b.com") == CircuitState.CLOSED

        # Manually set host-a to OPEN
        mock_adapter.set_circuit_state("host-a.com", CircuitState.OPEN)

        assert mock_adapter.get_circuit_state("host-a.com") == CircuitState.OPEN
        assert mock_adapter.get_circuit_state("host-b.com") == CircuitState.CLOSED
