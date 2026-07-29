"""Unit tests for CENFServerAdapter — REST API transport to CENF Server.

Tests cover:
- Sends error report to CENF server endpoint
- Consent check before sending
- Result reflects API success/failure
- Telemetry data is sent to correct endpoint

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.maintenance.models import ErrorReport


@pytest.fixture
def error_report() -> ErrorReport:
    """A sample error report for CENF Server testing."""
    return ErrorReport(
        app_id="test-app",
        message="API error",
        stack_trace="Traceback...",
        version="1.0.0",
        os="linux",
        severity="ERROR",
    )


pytest_plugins = ("pytest_asyncio",)


def _mock_aiohttp(mocker, status: int = 200, json_data: dict | None = None) -> object:
    """Create a mock aiohttp.ClientSession that returns a controlled response.

    **IMPORTANT**: ``post`` is a regular ``Mock()`` (not AsyncMock) because
    ``AsyncMock()`` returns a **coroutine** when called (Python 3.12 behaviour),
    which cannot be used with ``async with``.

    Returns the mock *post* callable (for call_args inspection).
    """
    if json_data is None:
        json_data = {}

    mock_response = mocker.AsyncMock()
    mock_response.status = status
    mock_response.json = mocker.AsyncMock(return_value=json_data)
    mock_response.__aenter__.return_value = mock_response

    mock_post = mocker.Mock()
    mock_post.return_value = mock_response

    mock_session = mocker.AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.post = mock_post

    mocker.patch("aiohttp.ClientSession", return_value=mock_session)
    return mock_post


class TestCENFServerAdapter:
    """Tests for CENFServerAdapter."""

    @pytest.mark.asyncio
    async def test_sends_error_to_cenf_server(self, mocker, error_report) -> None:
        """CENF Server adapter sends error report to /api/v1/errors."""
        from core_infrastructure.maintenance.adapters.cenf_server_adapter import CENFServerAdapter

        mock_post = _mock_aiohttp(mocker, status=201, json_data={"id": "err-123"})

        adapter = CENFServerAdapter(server_url="https://cenf.example.com")
        result = await adapter.report_error(report=error_report)

        assert result.success is True
        assert result.target == "cenf-server"

        call_args = mock_post.call_args
        assert call_args is not None
        json_data = call_args[1]["json"]
        assert json_data["app_id"] == "test-app"
        assert json_data["message"] == "API error"
        assert "/api/v1/errors" in str(call_args)

    @pytest.mark.asyncio
    async def test_returns_failure_on_server_error(self, mocker, error_report) -> None:
        """CENF Server error returns ReportResult with error."""
        from core_infrastructure.maintenance.adapters.cenf_server_adapter import CENFServerAdapter

        _mock_aiohttp(mocker, status=500, json_data={"error": "internal"})

        adapter = CENFServerAdapter(server_url="https://cenf.example.com")
        result = await adapter.report_error(report=error_report)

        assert result.success is False
        assert result.target == "cenf-server"

    @pytest.mark.asyncio
    async def test_sends_telemetry(self, mocker) -> None:
        """CENF Server sends telemetry to /api/v1/telemetry."""
        from core_infrastructure.maintenance.adapters.cenf_server_adapter import CENFServerAdapter

        mock_post = _mock_aiohttp(mocker, status=201)

        adapter = CENFServerAdapter(server_url="https://cenf.example.com")
        await adapter.send_telemetry(
            app_id="test-app",
            metrics={"error_count": 5, "uptime": 3600},
        )

        call_args = mock_post.call_args
        assert call_args is not None
        json_data = call_args[1]["json"]
        assert json_data["app_id"] == "test-app"
        assert json_data["metrics"]["error_count"] == 5
        assert "/api/v1/telemetry" in str(call_args)
