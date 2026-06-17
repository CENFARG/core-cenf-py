"""Unit tests for Email channel dispatch in DispatchAlertAdapter.

Tests cover:
- _dispatch_email calls smtplib.SMTP with correct parameters
- Graceful failure when SMTP is unreachable (logged, not raised)
- Email formatting: plain text MIMEText with title as subject, message as body
- AlertChannel.EMAIL is present in the enum

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import smtplib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_infrastructure.alert.adapters.dispatch_alert_adapter import (
    DispatchAlertAdapter,
)
from core_infrastructure.alert.models import AlertChannel
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter


@pytest.fixture
def config_manager() -> MagicMock:
    """Mock ConfigManager with email channel configuration."""
    mock = MagicMock()
    mock.get_section.return_value = {
        "channels": {
            "email": {
                "smtp_host": "smtp.example.com",
                "smtp_port": "587",
                "smtp_user": "alerts@example.com",
                "from_email": "alerts@example.com",
                "to_emails": "oncall@example.com, devops@example.com",
                "smtp_password_key": "alert.smtp_password",
            },
        }
    }
    return mock


@pytest.fixture
def secret_manager() -> MagicMock:
    """Mock SecretManager that returns SMTP password (async)."""
    mock = MagicMock()
    mock.get_secret = AsyncMock(return_value="test-password-123")
    return mock


@pytest.fixture
def logger_manager() -> MagicMock:
    """Mock LoggerManager for capturing log calls."""
    return MagicMock()


@pytest.fixture
def external_api_manager() -> MockHTTPAdapter:
    """MockHTTPAdapter (unused by email, but required by constructor)."""
    return MockHTTPAdapter()


@pytest.fixture
def error_manager() -> MagicMock:
    """Mock ErrorHandlingManager."""
    return MagicMock()


@pytest.fixture
def adapter(
    config_manager: MagicMock,
    secret_manager: MagicMock,
    logger_manager: MagicMock,
    external_api_manager: MockHTTPAdapter,
    error_manager: MagicMock,
) -> DispatchAlertAdapter:
    """Create a DispatchAlertAdapter with mocked dependencies including email config."""
    return DispatchAlertAdapter(
        config=config_manager,
        secret_manager=secret_manager,
        logger=logger_manager,
        external_api=external_api_manager,
        error_handler=error_manager,
    )


class TestAlertChannelEnum:
    """Verify AlertChannel has EMAIL member."""

    def test_email_in_alert_channel_enum(self) -> None:
        """AlertChannel.EMAIL exists and equals 'email'."""
        assert hasattr(AlertChannel, "EMAIL")
        assert AlertChannel.EMAIL == "email"


class TestEmailDispatch:
    """Verify _dispatch_email interacts with smtplib.SMTP correctly."""

    @pytest.mark.asyncio
    async def test_email_dispatched_with_correct_smtp_params(
        self,
        adapter: DispatchAlertAdapter,
        config_manager: MagicMock,
        secret_manager: MagicMock,
    ) -> None:
        """smtplib.SMTP is called with the configured host and port."""
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        with patch("smtplib.SMTP", mock_smtp):
            await adapter.send_alert(
                level=pytest.importorskip("core_infrastructure.alert.ports").AlertLevel.CRITICAL,
                title="DB Down",
                message="PostgreSQL unreachable",
            )

            mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)

    @pytest.mark.asyncio
    async def test_email_formatting(
        self,
        adapter: DispatchAlertAdapter,
    ) -> None:
        """Email is formatted as plain text with title as subject and message as body."""
        mock_smtp_instance = MagicMock()
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        from email.mime.text import MIMEText

        with patch("smtplib.SMTP", mock_smtp):
            await adapter.send_alert(
                level=pytest.importorskip("core_infrastructure.alert.ports").AlertLevel.CRITICAL,
                title="ALERT: DB Down",
                message="Database connection refused.",
            )

            # Verify send_message was called
            mock_smtp_instance.send_message.assert_called_once()
            msg = mock_smtp_instance.send_message.call_args[0][0]

            assert isinstance(msg, MIMEText)
            assert msg["Subject"] == "ALERT: DB Down"
            assert msg["From"] == "alerts@example.com"
            assert "oncall@example.com" in msg["To"]
            assert "devops@example.com" in msg["To"]


class TestEmailFailureGraceful:
    """Verify email failures are logged, not raised."""

    @pytest.mark.asyncio
    async def test_email_smtp_unreachable_logged_not_raised(
        self,
        adapter: DispatchAlertAdapter,
        logger_manager: MagicMock,
    ) -> None:
        """When smtplib.SMTP raises ConnectionRefusedError, error is logged."""
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        mock_smtp.side_effect = ConnectionRefusedError("Connection refused")

        with patch("smtplib.SMTP", mock_smtp):
            # Should NOT raise
            await adapter.send_alert(
                level=pytest.importorskip("core_infrastructure.alert.ports").AlertLevel.CRITICAL,
                title="Test Alert",
                message="Test message",
            )

            # Error should be logged
            logger_manager.error.assert_called()

    @pytest.mark.asyncio
    async def test_email_smtp_auth_failure_logged_not_raised(
        self,
        adapter: DispatchAlertAdapter,
        logger_manager: MagicMock,
    ) -> None:
        """When smtp login fails, error is logged but not propagated."""
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"Authentication failed"
        )
        mock_smtp = MagicMock(spec=smtplib.SMTP)
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        with patch("smtplib.SMTP", mock_smtp):
            # Should NOT raise
            await adapter.send_alert(
                level=pytest.importorskip("core_infrastructure.alert.ports").AlertLevel.CRITICAL,
                title="Auth Test",
                message="Should not crash on auth failure",
            )

            logger_manager.error.assert_called()

    @pytest.mark.asyncio
    async def test_email_missing_config_logs_warning(
        self,
        adapter: DispatchAlertAdapter,
        logger_manager: MagicMock,
    ) -> None:
        """When email config is missing required fields, warning is logged."""
        # Directly modify the adapter's alert config to have no channels
        adapter._alert_config.channels = {}

        await adapter.send_alert(
            level=pytest.importorskip("core_infrastructure.alert.ports").AlertLevel.CRITICAL,
            title="No Config",
            message="Should warn",
        )

        logger_manager.warn.assert_called()
