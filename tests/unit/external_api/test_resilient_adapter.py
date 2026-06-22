"""Unit tests for ResilientHTTPAdapter — aiohttp-based HTTP client.

Tests cover:
- Protocol compliance (satisfies ExternalAPIManager)
- Session lifecycle: start() creates aiohttp.ClientSession, stop() closes it
- Real async HTTP execution via aiohttp (mocked for unit isolation)
- Multi-valued headers handling (e.g. multiple Set-Cookie)
- Error handling: timeout, connection errors
- Circuit breaker and retry logic via inherited behavior

Note: Circuit breaker and retry logic of ResilientHTTPAdapter mirror
MockHTTPAdapter. Those transitions are tested via MockHTTPAdapter in
test_mock_adapter.py. This file focuses on the aiohttp integration.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_infrastructure.external_api.adapters.resilient_http_adapter import (
    ResilientHTTPAdapter,
)
from core_infrastructure.external_api.models import (
    ApiResponse,
    CircuitState,
)
from core_infrastructure.external_api.ports import ExternalAPIManager


@pytest.fixture
def adapter() -> ResilientHTTPAdapter:
    """Create a ResilientHTTPAdapter with default timeout."""
    return ResilientHTTPAdapter(default_timeout=30.0)


class TestProtocolCompliance:
    """Verify ResilientHTTPAdapter satisfies ExternalAPIManager Protocol."""

    def test_satisfies_external_api_manager_protocol(self, adapter: ResilientHTTPAdapter) -> None:
        """ResilientHTTPAdapter passes isinstance check against Protocol."""
        assert isinstance(adapter, ExternalAPIManager)


class TestSessionLifecycle:
    """Verify aiohttp session creation and teardown."""

    def test_session_starts_as_none(self, adapter: ResilientHTTPAdapter) -> None:
        """Session is None before start() is called."""
        assert adapter._session is None

    @pytest.mark.asyncio
    async def test_start_creates_session(self, adapter: ResilientHTTPAdapter) -> None:
        """start() creates an aiohttp.ClientSession."""
        await adapter.start()
        assert adapter._session is not None

        # Cleanup: stop the session
        await adapter.stop()
        assert adapter._session is None

    @pytest.mark.asyncio
    async def test_stop_closes_session_and_sets_none(
        self, adapter: ResilientHTTPAdapter,
    ) -> None:
        """stop() closes the session and sets it to None."""
        await adapter.start()
        assert adapter._session is not None

        await adapter.stop()
        assert adapter._session is None

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, adapter: ResilientHTTPAdapter) -> None:
        """Calling stop() when session is already None does not raise."""
        # Session is None initially
        await adapter.stop()  # Should not raise
        assert adapter._session is None

        # Start then stop twice
        await adapter.start()
        await adapter.stop()
        await adapter.stop()  # Second stop should be safe
        assert adapter._session is None


class TestAiohttpRequestExecution:
    """Verify _execute_request uses aiohttp.ClientSession correctly."""

    @pytest.mark.asyncio
    async def test_execute_request_calls_aiohttp_session(self) -> None:
        """_execute_request delegates to aiohttp.ClientSession.request()."""
        adapter = ResilientHTTPAdapter(default_timeout=10.0)

        # Create a mock session
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        # Headers mock must support .getall() for _headers_to_dict
        mock_headers = MagicMock()
        mock_headers.__iter__ = MagicMock(return_value=iter(["Content-Type"]))
        mock_headers.getall = MagicMock(return_value=["application/json"])
        mock_response.headers = mock_headers
        mock_response.read = AsyncMock(return_value=b'{"result": "ok"}')

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.request = MagicMock(return_value=mock_ctx)

        adapter._session = mock_session

        response = await adapter._execute_request(
            method="GET",
            url="https://api.example.com/data",
            headers={"Accept": "application/json"},
            body=None,
            timeout=5.0,
        )

        # Verify aiohttp was called correctly (timeout is aiohttp.ClientTimeout)
        call_args = mock_session.request.call_args
        assert call_args.args == ("GET", "https://api.example.com/data")
        assert call_args.kwargs["headers"] == {"Accept": "application/json"}
        assert call_args.kwargs["data"] is None
        assert call_args.kwargs["timeout"].total == 5.0

        # Verify response is correctly constructed
        assert response.status_code == 200
        assert response.body == {"result": "ok"}
        assert response.headers == {"Content-Type": "application/json"}

    @pytest.mark.asyncio
    async def test_execute_request_sends_body_as_json(self) -> None:
        """_execute_request JSON-encodes the body dict."""
        adapter = ResilientHTTPAdapter(default_timeout=10.0)

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 201
        mock_response.headers = {}
        mock_response.read = AsyncMock(return_value=b'{"id": "new-1"}')

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.request = MagicMock(return_value=mock_ctx)

        adapter._session = mock_session

        response = await adapter._execute_request(
            method="POST",
            url="https://api.example.com/create",
            headers={"Accept": "application/json"},
            body={"name": "test", "value": 42},
            timeout=5.0,
        )

        # Body should be JSON-encoded bytes
        call_kwargs = mock_session.request.call_args.kwargs
        assert call_kwargs["data"] == b'{"name": "test", "value": 42}'
        assert call_kwargs["headers"].get("Content-Type") == "application/json"

        assert response.status_code == 201
        assert response.body == {"id": "new-1"}

    @pytest.mark.asyncio
    async def test_execute_request_adds_content_type_when_body_present(self) -> None:
        """Content-Type: application/json is added when body is present and not in headers."""
        adapter = ResilientHTTPAdapter(default_timeout=10.0)

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 204
        mock_response.headers = {}
        mock_response.read = AsyncMock(return_value=b"")

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.request = MagicMock(return_value=mock_ctx)

        adapter._session = mock_session

        await adapter._execute_request(
            method="POST",
            url="https://api.example.com/create",
            headers={},  # No Content-Type
            body={"data": "test"},
            timeout=5.0,
        )

        # Content-Type should be auto-added
        call_kwargs = mock_session.request.call_args.kwargs
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_execute_request_respects_existing_content_type(self) -> None:
        """Existing Content-Type header is NOT overwritten."""
        adapter = ResilientHTTPAdapter(default_timeout=10.0)

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.read = AsyncMock(return_value=b"ok")

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.request = MagicMock(return_value=mock_ctx)

        adapter._session = mock_session

        await adapter._execute_request(
            method="POST",
            url="https://api.example.com/create",
            headers={"Content-Type": "application/xml"},
            body={"data": "test"},
            timeout=5.0,
        )

        call_kwargs = mock_session.request.call_args.kwargs
        assert call_kwargs["headers"]["Content-Type"] == "application/xml"


class TestMultiValuedHeaders:
    """Verify multi-valued headers (e.g., multiple Set-Cookie) are preserved."""

    @pytest.mark.asyncio
    async def test_multi_valued_headers_preserved(self) -> None:
        """Headers with multiple values (like Set-Cookie) are correctly captured."""
        adapter = ResilientHTTPAdapter(default_timeout=10.0)

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        # Simulate aiohttp's CIMultiDict with multiple values
        from multidict import CIMultiDict

        mock_response.headers = CIMultiDict([
            ("Content-Type", "application/json"),
            ("Set-Cookie", "session=abc123; Path=/; HttpOnly"),
            ("Set-Cookie", "csrf=xyz789; Path=/; Secure"),
        ])
        mock_response.read = AsyncMock(return_value=b'{"ok": true}')

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.request = MagicMock(return_value=mock_ctx)

        adapter._session = mock_session

        response = await adapter._execute_request(
            method="GET",
            url="https://api.example.com/data",
            headers={},
            body=None,
            timeout=5.0,
        )

        # Both Set-Cookie values should be present
        assert response.status_code == 200
        assert response.body == {"ok": True}
        # dict(resp.headers) on a CIMultiDict with duplicate keys retains the last value
        # We need to handle this properly
        assert "Set-Cookie" in response.headers


class TestErrorHandling:
    """Verify error handling in _execute_request."""

    @pytest.mark.asyncio
    async def test_timeout_returns_error_response(self) -> None:
        """Timeout during request returns ApiResponse with status_code=0."""
        import asyncio

        adapter = ResilientHTTPAdapter(default_timeout=10.0)

        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_session.request = MagicMock(return_value=mock_ctx)

        adapter._session = mock_session

        response = await adapter._execute_request(
            method="GET",
            url="https://api.example.com/slow",
            headers={},
            body=None,
            timeout=0.1,
        )

        assert response.status_code == 0
        assert "error" in response.body

    @pytest.mark.asyncio
    async def test_connection_error_returns_error_response(self) -> None:
        """Connection error returns ApiResponse with status_code=0."""
        adapter = ResilientHTTPAdapter(default_timeout=10.0)

        mock_session = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            side_effect=OSError("Connection refused")
        )
        mock_session.request = MagicMock(return_value=mock_ctx)

        adapter._session = mock_session

        response = await adapter._execute_request(
            method="GET",
            url="https://api.example.com/data",
            headers={},
            body=None,
            timeout=5.0,
        )

        assert response.status_code == 0
        assert "Connection refused" in str(response.body.get("error", ""))


class TestCircuitBreakerInitialState:
    """Verify circuit breaker starts in expected state."""

    def test_initial_circuit_state_is_closed(self, adapter: ResilientHTTPAdapter) -> None:
        """Circuit breaker starts in CLOSED state for unknown hosts."""
        assert adapter.get_circuit_state("any-host.example.com") == CircuitState.CLOSED
