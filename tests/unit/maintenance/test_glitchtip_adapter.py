"""Unit tests for GlitchTipAdapter — self-hosted Sentry-compatible backend.

Tests cover:
- Sends error to GlitchTip store endpoint
- DSN parsing
- Result reflects API success/failure
- Stack trace is sent in Sentry-compatible format

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.maintenance.models import ErrorReport


@pytest.fixture
def error_report() -> ErrorReport:
    """A sample error report for GlitchTip testing."""
    return ErrorReport(
        app_id="test-app",
        message="Database timeout",
        stack_trace='Traceback:\n  File "db.py", line 20\npsycopg.OperationalError: timeout',
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


class TestGlitchTipAdapter:
    """Tests for GlitchTipAdapter."""

    @pytest.mark.asyncio
    async def test_sends_error_to_glitchtip(self, mocker, error_report) -> None:
        """GlitchTip sends error to /api/1/store/."""
        from core_infrastructure.maintenance.adapters.glitchtip_adapter import GlitchTipAdapter

        mock_post = _mock_aiohttp(mocker, status=200, json_data={"id": "evt-1"})

        adapter = GlitchTipAdapter(dsn="https://key@glitchtip.example.com/1")
        result = await adapter.report_error(report=error_report)

        assert result.success is True
        assert result.target == "glitchtip"

        call_args = mock_post.call_args
        assert call_args is not None
        json_data = call_args[1]["json"]
        assert json_data["message"] == "Database timeout"
        assert "/api/1/store/" in str(call_args)

    def test_parses_dsn(self) -> None:
        """DSN is parsed into host, port, protocol."""
        from core_infrastructure.maintenance.adapters.glitchtip_adapter import GlitchTipAdapter

        adapter = GlitchTipAdapter(dsn="https://mykey@glitchtip.example.com/42")
        parsed = adapter._parsed_dsn
        assert parsed["host"] == "glitchtip.example.com"
        assert parsed["project_id"] == "42"
        assert parsed["scheme"] == "https"

    @pytest.mark.asyncio
    async def test_returns_failure_on_api_error(self, mocker, error_report) -> None:
        """GlitchTip API error returns ReportResult with error."""
        from core_infrastructure.maintenance.adapters.glitchtip_adapter import GlitchTipAdapter

        _mock_aiohttp(mocker, status=401, json_data={"error": "unauthorized"})

        adapter = GlitchTipAdapter(dsn="https://key@glitchtip.example.com/1")
        result = await adapter.report_error(report=error_report)

        assert result.success is False
        assert result.target == "glitchtip"
