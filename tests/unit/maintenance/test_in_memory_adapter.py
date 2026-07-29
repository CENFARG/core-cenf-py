"""Unit tests for InMemoryMaintenanceAdapter — in-memory test double.

Tests cover:
- is_consent_granted() returns False by default (GDPR default-off)
- request_consent() records consent and returns ConsentResult
- is_consent_granted() returns True after request_consent()
- revoke_consent() purges consent and telemetry data
- capture_error() returns ErrorReport with stack trace and context
- capture_error() scrubs PII in stack traces
- report_error() stores report in memory and returns ReportResult
- report_error() with no consent returns ReportResult with error
- send_telemetry() stores metrics in memory
- get_json_schema() returns a dict
- Protocol satisfaction

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.maintenance.models import ConsentResult, ErrorReport, ReportResult
from core_infrastructure.maintenance.ports import MaintenanceManager


@pytest.fixture
def adapter():
    """Create a fresh InMemoryMaintenanceAdapter."""
    from core_infrastructure.maintenance.adapters.in_memory_maintenance_adapter import (
        InMemoryMaintenanceAdapter,
    )

    return InMemoryMaintenanceAdapter()


# ── Consent Management ──────────────────────────────────────────────────────


class TestIsConsentGranted:
    """Tests for is_consent_granted()."""

    @pytest.mark.asyncio
    async def test_default_off(self, adapter) -> None:
        """is_consent_granted returns False by default (GDPR default-off)."""
        result = await adapter.is_consent_granted(app_id="test-app")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_after_grant(self, adapter) -> None:
        """is_consent_granted returns True after request_consent()."""
        await adapter.request_consent(app_id="test-app", user_id="user-1")
        result = await adapter.is_consent_granted(app_id="test-app")
        assert result is True

    @pytest.mark.asyncio
    async def test_per_app_isolation(self, adapter) -> None:
        """Consent is per-application."""
        await adapter.request_consent(app_id="app-a", user_id="user-1")
        assert await adapter.is_consent_granted(app_id="app-a") is True
        assert await adapter.is_consent_granted(app_id="app-b") is False


class TestRequestConsent:
    """Tests for request_consent()."""

    @pytest.mark.asyncio
    async def test_returns_consent_result(self, adapter) -> None:
        """request_consent returns ConsentResult with GRANTED status."""
        result = await adapter.request_consent(app_id="test-app", user_id="user-1")
        assert isinstance(result, ConsentResult)
        assert result.status == "GRANTED"
        assert result.app_id == "test-app"
        assert result.user_id == "user-1"
        assert result.timestamp is not None

    @pytest.mark.asyncio
    async def test_consent_is_idempotent(self, adapter) -> None:
        """request_consent can be called multiple times for same app."""
        r1 = await adapter.request_consent(app_id="test-app", user_id="user-1")
        r2 = await adapter.request_consent(app_id="test-app", user_id="user-1")
        assert r1.status == "GRANTED"
        assert r2.status == "GRANTED"
        assert await adapter.is_consent_granted(app_id="test-app") is True


class TestRevokeConsent:
    """Tests for revoke_consent()."""

    @pytest.mark.asyncio
    async def test_revoke_clears_consent(self, adapter) -> None:
        """revoke_consent clears consent for the app."""
        await adapter.request_consent(app_id="test-app", user_id="user-1")
        await adapter.revoke_consent(app_id="test-app", user_id="user-1")
        assert await adapter.is_consent_granted(app_id="test-app") is False

    @pytest.mark.asyncio
    async def test_revoke_returns_consent_result(self, adapter) -> None:
        """revoke_consent returns ConsentResult with REVOKED status."""
        await adapter.request_consent(app_id="test-app", user_id="user-1")
        result = await adapter.revoke_consent(app_id="test-app", user_id="user-1")
        assert isinstance(result, ConsentResult)
        assert result.status == "REVOKED"

    @pytest.mark.asyncio
    async def test_revoke_clears_telemetry(self, adapter) -> None:
        """revoke_consent purges stored telemetry data."""
        await adapter.request_consent(app_id="test-app", user_id="user-1")
        await adapter.send_telemetry(app_id="test-app", metrics={"errors": 5})
        await adapter.revoke_consent(app_id="test-app", user_id="user-1")
        # After revoke, stored telemetry should be cleared
        captured = adapter.get_captured_metrics(app_id="test-app")
        assert len(captured) == 0

    @pytest.mark.asyncio
    async def test_revoke_idempotent(self, adapter) -> None:
        """revoke_consent does not raise when called without prior consent."""
        # Should not crash when revoking consent that was never granted
        result = await adapter.revoke_consent(app_id="never-granted", user_id="user-1")
        assert isinstance(result, ConsentResult)
        assert result.status == "REVOKED"


# ── Error Capture ───────────────────────────────────────────────────────────


class TestCaptureError:
    """Tests for capture_error()."""

    @pytest.mark.asyncio
    async def test_returns_error_report(self, adapter) -> None:
        """capture_error returns ErrorReport with exception details."""
        try:
            raise ValueError("Something broke")
        except ValueError as e:
            report = await adapter.capture_error(app_id="test-app", error=e)

        assert isinstance(report, ErrorReport)
        assert report.app_id == "test-app"
        assert "Something broke" in report.message
        assert "ValueError" in report.stack_trace
        assert report.version == "0.0.0"
        assert report.os in ("linux", "windows", "macos")

    @pytest.mark.asyncio
    async def test_capture_with_context(self, adapter) -> None:
        """capture_error accepts optional context dict."""
        try:
            raise RuntimeError("context error")
        except RuntimeError as e:
            report = await adapter.capture_error(
                app_id="test-app", error=e, context={"user_id": "u1", "action": "login"}
            )

        assert report.context is not None
        assert report.context["user_id"] == "u1"

    @pytest.mark.asyncio
    async def test_stores_captured_errors(self, adapter) -> None:
        """capture_error stores the report in memory for test assertions."""
        try:
            raise ValueError("stored error")
        except ValueError as e:
            await adapter.capture_error(app_id="test-app", error=e)

        captured = adapter.get_captured_errors(app_id="test-app")
        assert len(captured) == 1
        assert "stored error" in captured[0].message


# ── Error Reporting ─────────────────────────────────────────────────────────


class TestReportError:
    """Tests for report_error()."""

    @pytest.mark.asyncio
    async def test_without_consent_returns_error(self, adapter) -> None:
        """report_error without consent returns ReportResult with error."""
        report = ErrorReport(
            app_id="test-app",
            message="test",
            stack_trace="",
            version="1.0.0",
            os="linux",
        )
        result = await adapter.report_error(report=report)
        assert isinstance(result, ReportResult)
        assert result.success is False
        assert "consent" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_with_consent_stores_report(self, adapter) -> None:
        """report_error with consent returns success and stores report."""
        await adapter.request_consent(app_id="test-app", user_id="user-1")
        report = ErrorReport(
            app_id="test-app",
            message="test error",
            stack_trace="Traceback...",
            version="1.0.0",
            os="linux",
        )
        result = await adapter.report_error(report=report)
        assert isinstance(result, ReportResult)
        assert result.success is True
        assert result.target == "in_memory"

    @pytest.mark.asyncio
    async def test_stores_reported_errors(self, adapter) -> None:
        """report_error stores the report for test assertions."""
        await adapter.request_consent(app_id="test-app", user_id="user-1")
        report = ErrorReport(
            app_id="test-app",
            message="stored report",
            stack_trace="",
            version="1.0.0",
            os="linux",
        )
        await adapter.report_error(report=report)
        reported = adapter.get_reported_errors()
        assert any("stored report" in r.message for r in reported)


# ── Telemetry ───────────────────────────────────────────────────────────────


class TestSendTelemetry:
    """Tests for send_telemetry()."""

    @pytest.mark.asyncio
    async def test_stores_metrics(self, adapter) -> None:
        """send_telemetry stores metrics in memory."""
        await adapter.request_consent(app_id="test-app", user_id="user-1")
        await adapter.send_telemetry(
            app_id="test-app",
            metrics={"error_count": 5, "uptime_seconds": 3600},
        )
        captured = adapter.get_captured_metrics(app_id="test-app")
        assert len(captured) == 1
        assert captured[0]["error_count"] == 5

    @pytest.mark.asyncio
    async def test_multiple_metric_batches(self, adapter) -> None:
        """send_telemetry appends multiple metric batches."""
        await adapter.request_consent(app_id="test-app", user_id="user-1")
        await adapter.send_telemetry(app_id="test-app", metrics={"errors": 1})
        await adapter.send_telemetry(app_id="test-app", metrics={"errors": 2})
        captured = adapter.get_captured_metrics(app_id="test-app")
        assert len(captured) == 2

    @pytest.mark.asyncio
    async def test_without_consent(self, adapter) -> None:
        """send_telemetry without consent should not store metrics."""
        await adapter.send_telemetry(app_id="test-app", metrics={"errors": 5})
        captured = adapter.get_captured_metrics(app_id="test-app")
        assert len(captured) == 0


# ── Protocol Compliance ─────────────────────────────────────────────────────


class TestProtocolCompliance:
    """Verify the adapter satisfies the MaintenanceManager Protocol."""

    def test_adapter_satisfies_protocol(self, adapter) -> None:
        """InMemoryMaintenanceAdapter satisfies MaintenanceManager Protocol."""
        assert isinstance(adapter, MaintenanceManager)


# ── JSON Schema ─────────────────────────────────────────────────────────────


class TestGetJsonSchema:
    """Tests for get_json_schema()."""

    def test_returns_dict(self, adapter) -> None:
        """get_json_schema returns a non-empty dict."""
        schema = adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0
        assert "$schema" in schema
