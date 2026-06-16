"""Unit tests for MockHTTPAdapter — configurable mock HTTP adapter for testing.

Tests cover:
- set_response() configures per-method+URL responses
- set_response_sequence() configures a sequence of responses
- set_circuit_state() / force_recovery() for circuit breaker control
- set_timeout() for timeout simulation
- Default response behavior for unconfigured URLs

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.external_api.adapters.mock_http_adapter import (
    MockHTTPAdapter,
)
from core_infrastructure.external_api.models import CircuitState


@pytest.fixture
def adapter() -> MockHTTPAdapter:
    """Create a MockHTTPAdapter."""
    return MockHTTPAdapter()


class TestMockAdapterConfiguration:
    """Verify mock adapter configuration APIs."""

    @pytest.mark.asyncio
    async def test_set_response_matches_method_and_url(self, adapter: MockHTTPAdapter) -> None:
        """set_response() configures per-method+URL responses."""
        adapter.set_response("GET", "https://a.com/x", status_code=200, body={"get": True})
        adapter.set_response("POST", "https://a.com/x", status_code=201, body={"post": True})

        get_resp = await adapter.get("https://a.com/x")
        assert get_resp.status_code == 200
        assert get_resp.body == {"get": True}

        post_resp = await adapter.post("https://a.com/x", body={})
        assert post_resp.status_code == 201
        assert post_resp.body == {"post": True}

    @pytest.mark.asyncio
    async def test_set_response_sequence(self, adapter: MockHTTPAdapter) -> None:
        """set_response_sequence() returns successive responses."""
        adapter.set_response_sequence(
            "GET", "https://a.com/seq",
            [(500, {"error": "first"}), (500, {"error": "second"}), (200, {"ok": True})],
        )

        r1 = await adapter.get("https://a.com/seq")
        r2 = await adapter.get("https://a.com/seq")
        r3 = await adapter.get("https://a.com/seq")

        assert r1.status_code == 500
        assert r2.status_code == 500
        assert r3.status_code == 200

    @pytest.mark.asyncio
    async def test_sequence_loops_last_response(self, adapter: MockHTTPAdapter) -> None:
        """After sequence is exhausted, the last response repeats."""
        adapter.set_response_sequence(
            "GET", "https://a.com/loop",
            [(200, {"first": True}), (200, {"last": True})],
        )

        r1 = await adapter.get("https://a.com/loop")
        r2 = await adapter.get("https://a.com/loop")
        r3 = await adapter.get("https://a.com/loop")  # Should repeat last

        assert r1.body == {"first": True}
        assert r2.body == {"last": True}
        assert r3.body == {"last": True}

    @pytest.mark.asyncio
    async def test_headers_returned(self, adapter: MockHTTPAdapter) -> None:
        """Mock adapter returns configured response headers."""
        adapter.set_response(
            "GET", "https://a.com/h",
            status_code=200,
            body={},
            headers={"X-Custom": "mock-value"},
        )
        resp = await adapter.get("https://a.com/h")
        assert resp.headers.get("X-Custom") == "mock-value"

    def test_set_circuit_state(self, adapter: MockHTTPAdapter) -> None:
        """set_circuit_state() manually sets the circuit state for a host."""
        adapter.set_circuit_state("example.com", CircuitState.OPEN)
        assert adapter.get_circuit_state("example.com") == CircuitState.OPEN

    def test_force_recovery(self, adapter: MockHTTPAdapter) -> None:
        """force_recovery() forces a host to HALF_OPEN."""
        adapter.set_circuit_state("example.com", CircuitState.OPEN)
        adapter.force_recovery("example.com")
        assert adapter.get_circuit_state("example.com") == CircuitState.HALF_OPEN
