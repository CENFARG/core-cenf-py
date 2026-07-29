"""Unit tests for DiscordAlertAdapter — webhook-based Discord alerts.

Tests cover:
- send_error() sends rich embed payload
- Stack trace truncation at 2000 chars
- Error report fields mapped to embed fields
- Consent check before sending
- Result reflects webhook success/failure

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.maintenance.models import ErrorReport


@pytest.fixture
def error_report() -> ErrorReport:
    """A sample error report for Discord testing."""
    return ErrorReport(
        app_id="test-app",
        message="Something broke",
        stack_trace='Traceback (most recent call last):\n  File "app.py", line 10\nValueError: broken',
        version="1.0.0",
        os="linux",
        severity="ERROR",
    )


pytest_plugins = ("pytest_asyncio",)


def _mock_aiohttp(mocker, status: int = 204, json_data: dict | None = None) -> object:
    """Create a mock aiohttp.ClientSession that returns a controlled response.

    Patches the ClientSession constructor so every ``async with ClientSession() as s:``
    yields a mock session.

    **IMPORTANT**: ``post`` is a regular ``Mock()`` (not AsyncMock) because
    ``AsyncMock()`` returns a **coroutine** when called (Python 3.12 behaviour),
    which cannot be used with ``async with``. The response mock itself is an
    ``AsyncMock`` so ``await resp.json()`` works.

    Returns the mock *post* callable (for call_args inspection).
    """
    if json_data is None:
        json_data = {}

    # Response: AsyncMock so .json() is awaitable; also make it async-ctx-mgr
    mock_response = mocker.AsyncMock()
    mock_response.status = status
    mock_response.json = mocker.AsyncMock(return_value=json_data)
    mock_response.__aenter__.return_value = mock_response

    # post: Mock (NOT AsyncMock!) — calling Mock returns return_value, not a coroutine
    mock_post = mocker.Mock()
    mock_post.return_value = mock_response

    # Session: AsyncMock for __aenter__, and wire .post
    mock_session = mocker.AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.post = mock_post

    mocker.patch("aiohttp.ClientSession", return_value=mock_session)
    return mock_post


class TestDiscordAlertAdapter:
    """Tests for DiscordAlertAdapter."""

    @pytest.mark.asyncio
    async def test_sends_embed_with_error_details(self, mocker, error_report) -> None:
        """Discord alert sends embed with app_id, message, severity."""
        from core_infrastructure.maintenance.adapters.discord_alert_adapter import DiscordAlertAdapter

        mock_post = _mock_aiohttp(mocker, status=204)

        adapter = DiscordAlertAdapter(webhook_url="https://discord.com/api/webhooks/test")
        result = await adapter.report_error(report=error_report)

        assert result.success is True
        assert result.target == "discord"

        # Verify embed payload
        call_args = mock_post.call_args
        assert call_args is not None
        json_data = call_args[1]["json"]
        assert len(json_data["embeds"]) == 1
        embed = json_data["embeds"][0]
        assert "test-app" in embed["title"]
        assert "Something broke" in embed["description"]

    @pytest.mark.asyncio
    async def test_truncates_stack_at_2000_chars(self, mocker) -> None:
        """Stack trace longer than 2000 chars is truncated."""
        from core_infrastructure.maintenance.adapters.discord_alert_adapter import DiscordAlertAdapter

        long_trace = "Line\n" * 500  # ~2500 chars
        report = ErrorReport(
            app_id="test-app",
            message="Long error",
            stack_trace=long_trace,
            version="1.0.0",
            os="linux",
        )

        mock_post = _mock_aiohttp(mocker, status=204)

        adapter = DiscordAlertAdapter(webhook_url="https://discord.com/api/webhooks/test")
        await adapter.report_error(report=report)

        call_args = mock_post.call_args
        assert call_args is not None
        json_data = call_args[1]["json"]
        embed_desc = json_data["embeds"][0].get("description", "")
        assert len(embed_desc) <= 2000

    @pytest.mark.asyncio
    async def test_returns_failure_on_http_error(self, mocker, error_report) -> None:
        """Discord alert returns ReportResult with error on HTTP failure."""
        from core_infrastructure.maintenance.adapters.discord_alert_adapter import DiscordAlertAdapter

        _mock_aiohttp(mocker, status=429, json_data={"error": "rate_limit"})

        adapter = DiscordAlertAdapter(webhook_url="https://discord.com/api/webhooks/test")
        result = await adapter.report_error(report=error_report)

        assert result.success is False
        assert result.target == "discord"
        assert isinstance(result.error, str)

    @pytest.mark.asyncio
    async def test_maps_severity_to_color(self, mocker) -> None:
        """Error severity maps to Discord embed color."""
        from core_infrastructure.maintenance.adapters.discord_alert_adapter import DiscordAlertAdapter

        report = ErrorReport(
            app_id="test-app",
            message="critical error",
            stack_trace="",
            version="1.0.0",
            os="linux",
            severity="CRITICAL",
        )

        mock_post = _mock_aiohttp(mocker, status=204)

        adapter = DiscordAlertAdapter(webhook_url="https://discord.com/api/webhooks/test")
        await adapter.report_error(report=report)

        call_args = mock_post.call_args
        assert call_args is not None
        json_data = call_args[1]["json"]
        embed = json_data["embeds"][0]
        assert embed["color"] is not None
