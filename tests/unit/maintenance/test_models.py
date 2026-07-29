"""Unit tests for M24 MaintenanceManager models.

Tests ErrorReport, ConsentResult, ReportResult, and MaintenanceConfig
instantiation, validation, and serialization.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core_infrastructure.maintenance.models import (
    ConsentResult,
    ErrorReport,
    MaintenanceConfig,
    ReportResult,
)


class TestErrorReport:
    """Tests for ErrorReport model."""

    def test_minimal_instantiation(self) -> None:
        """ErrorReport can be created with required fields."""
        report = ErrorReport(
            app_id="test-app",
            message="Something went wrong",
            stack_trace='Traceback...\n  File "test.py", line 1, in <module>',
            version="1.0.0",
            os="linux",
        )
        assert report.app_id == "test-app"
        assert report.message == "Something went wrong"
        assert "Traceback" in report.stack_trace

    def test_with_all_fields(self) -> None:
        """ErrorReport can be created with all optional fields."""
        now = datetime.now(UTC)
        report = ErrorReport(
            app_id="test-app",
            message="Error with context",
            stack_trace="Traceback...",
            version="1.0.0",
            os="windows",
            arch="x64",
            python_version="3.12.0",
            timestamp=now,
            context={"user": "test"},
            severity="ERROR",
            tags={"env": "prod"},
        )
        assert report.arch == "x64"
        assert report.python_version == "3.12.0"
        assert report.severity == "ERROR"
        assert report.context == {"user": "test"}

    def test_severity_default(self) -> None:
        """ErrorReport defaults severity to ERROR."""
        report = ErrorReport(
            app_id="test-app",
            message="err",
            stack_trace="",
            version="1.0.0",
            os="linux",
        )
        assert report.severity == "ERROR"

    def test_invalid_severity_raises(self) -> None:
        """ErrorReport raises ValidationError for invalid severity."""
        with pytest.raises(ValidationError):
            ErrorReport(
                app_id="test-app",
                message="err",
                stack_trace="",
                version="1.0.0",
                os="linux",
                severity="INVALID",
            )


class TestConsentResult:
    """Tests for ConsentResult model."""

    def test_minimal_instantiation(self) -> None:
        """ConsentResult can be created with required fields."""
        now = datetime.now(UTC)
        result = ConsentResult(
            app_id="test-app",
            user_id="user-1",
            status="GRANTED",
            timestamp=now,
        )
        assert result.app_id == "test-app"
        assert result.user_id == "user-1"
        assert result.status == "GRANTED"

    def test_revoked_status(self) -> None:
        """ConsentResult supports REVOKED status."""
        now = datetime.now(UTC)
        result = ConsentResult(
            app_id="test-app",
            user_id="user-1",
            status="REVOKED",
            timestamp=now,
        )
        assert result.status == "REVOKED"

    def test_invalid_status_raises(self) -> None:
        """ConsentResult raises ValidationError for invalid status."""
        with pytest.raises(ValidationError):
            ConsentResult(
                app_id="test-app",
                user_id="user-1",
                status="INVALID",
                timestamp=datetime.now(UTC),
            )


class TestReportResult:
    """Tests for ReportResult model."""

    def test_success_result(self) -> None:
        """ReportResult with success=True."""
        result = ReportResult(success=True, target="discord")
        assert result.success is True
        assert result.target == "discord"
        assert result.error is None

    def test_failure_result(self) -> None:
        """ReportResult with success=False and error."""
        result = ReportResult(
            success=False, target="github", error="API rate limit exceeded"
        )
        assert result.success is False
        assert result.error == "API rate limit exceeded"

    def test_error_defaults_none(self) -> None:
        """ReportResult.error defaults to None."""
        result = ReportResult(success=True, target="discord")
        assert result.error is None


class TestMaintenanceConfig:
    """Tests for MaintenanceConfig model."""

    def test_minimal_config(self) -> None:
        """MaintenanceConfig with defaults."""
        config = MaintenanceConfig()
        assert config.enabled is False
        assert config.consent_required is True
        assert config.app_id == ""

    def test_full_config(self) -> None:
        """MaintenanceConfig with all fields."""
        config = MaintenanceConfig(
            enabled=True,
            consent_required=True,
            app_id="my-app",
            app_version="2.0.0",
            github_repo="owner/repo",
            github_app_id="12345",
            discord_webhook_url="https://discord.com/api/webhooks/xxx",
            cenf_server_url="https://cenf.example.com",
            glitchtip_dsn="https://key@glitchtip.example.com/1",
            telemetry_enabled=True,
            error_sample_rate=0.5,
        )
        assert config.enabled is True
        assert config.github_repo == "owner/repo"
        assert config.error_sample_rate == 0.5

    def test_invalid_sample_rate_raises(self) -> None:
        """MaintenanceConfig raises for sample rate > 1.0."""
        with pytest.raises(ValidationError):
            MaintenanceConfig(error_sample_rate=1.5)
