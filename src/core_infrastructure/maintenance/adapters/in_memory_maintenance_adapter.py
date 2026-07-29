"""InMemoryMaintenanceAdapter — dict-backed MaintenanceManager test double.

Provides a lightweight, zero-I/O adapter for unit testing components that
depend on MaintenanceManager. Consents, errors, and telemetry are stored
in memory and exposed via test helper methods for assertions.

Supports consent gating (default-off), PII scrubbing via pii_scrubber,
report storage, and telemetry capture.

Security: This adapter performs regex-based PII scrubbing. NEVER use
    it in production — it's a test-only adapter.
Observability: No RED metrics emitted — this is a test-only adapter.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from core_infrastructure.maintenance.consent_store import ConsentStore
from core_infrastructure.maintenance.models import ConsentResult, ErrorReport, ReportResult
from core_infrastructure.maintenance.pii_scrubber import scrub_pii


class InMemoryMaintenanceAdapter:
    """Dict-backed MaintenanceManager test double.

    Stores consents, errors, and metrics in memory for test assertions.
    All adapters are fire-and-forget — never block or raise.

    Usage::

        adapter = InMemoryMaintenanceAdapter()
        await adapter.request_consent(app_id="my-app", user_id="user-1")
        report = await adapter.capture_error(
            app_id="my-app", error=ValueError("fail"), context={"key": "val"},
        )
        await adapter.report_error(report=report)
        errors = adapter.get_captured_errors(app_id="my-app")
        reported = adapter.get_reported_errors()
    """

    def __init__(self) -> None:
        """Initialize the in-memory adapter with empty stores."""
        self._consent_store = ConsentStore()
        self._captured_errors: dict[str, list[ErrorReport]] = {}
        self._reported_errors: list[ErrorReport] = []

    # ── Test helpers ─────────────────────────────────────────────────────────

    def get_captured_errors(self, app_id: str) -> list[ErrorReport]:
        """Get all captured errors for an app (test helper).

        Args:
            app_id: The application identifier.

        Returns:
            list[ErrorReport]: Captured errors for the app.
        """
        return list(self._captured_errors.get(app_id, []))

    def get_reported_errors(self) -> list[ErrorReport]:
        """Get all reported errors (test helper).

        Returns:
            list[ErrorReport]: All errors that passed through report_error().
        """
        return list(self._reported_errors)

    def get_captured_metrics(self, app_id: str) -> list[dict[str, object]]:
        """Get all captured telemetry metrics for an app (test helper).

        Args:
            app_id: The application identifier.

        Returns:
            list[dict]: Telemetry metric batches for the app.
        """
        return self._consent_store.get_telemetry(app_id=app_id)

    # ── Public API — MaintenanceManager Protocol ────────────────────────────

    async def is_consent_granted(self, *, app_id: str) -> bool:
        """Check whether the user has granted telemetry consent.

        Args:
            app_id: The application identifier.

        Returns:
            bool: True if consent has been granted, False otherwise.
        """
        return self._consent_store.is_granted(app_id=app_id)

    async def request_consent(
        self,
        *,
        app_id: str,
        user_id: str,
    ) -> ConsentResult:
        """Record explicit user consent for telemetry.

        Args:
            app_id: The application identifier.
            user_id: The user identifier granting consent.

        Returns:
            ConsentResult: With status GRANTED and current timestamp.
        """
        record = self._consent_store.grant(app_id=app_id, user_id=user_id)
        timestamp = record.get("timestamp", datetime.now(UTC))
        return ConsentResult(
            app_id=app_id,
            user_id=user_id,
            status="GRANTED",
            timestamp=timestamp,  # type: ignore[arg-type]
        )

    async def revoke_consent(self, *, app_id: str, user_id: str) -> ConsentResult:
        """Revoke consent and purge all telemetry data.

        Args:
            app_id: The application identifier.
            user_id: The user identifier revoking consent.

        Returns:
            ConsentResult: With status REVOKED and current timestamp.
        """
        record = self._consent_store.revoke(app_id=app_id, user_id=user_id)
        timestamp = record.get("timestamp", datetime.now(UTC))
        return ConsentResult(
            app_id=app_id,
            user_id=user_id,
            status="REVOKED",
            timestamp=timestamp,  # type: ignore[arg-type]
        )

    async def capture_error(
        self,
        *,
        app_id: str,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> ErrorReport:
        """Capture an error with PII scrubbing.

        Args:
            app_id: The application identifier.
            error: The exception to capture.
            context: Optional dictionary of additional context.

        Returns:
            ErrorReport: PII-scrubbed error report.
        """
        stack = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        scrubbed_stack = scrub_pii(stack)
        message = scrub_pii(str(error))
        scrubbed_context: dict[str, Any] | None = None
        if context:
            scrubbed_context = dict(context)
            for key, value in scrubbed_context.items():
                if isinstance(value, str):
                    scrubbed_context[key] = scrub_pii(value)

        report = ErrorReport(
            app_id=app_id,
            message=message,
            stack_trace=scrubbed_stack,
            version="0.0.0",
            os=_detect_os(),
            context=scrubbed_context,
        )

        if app_id not in self._captured_errors:
            self._captured_errors[app_id] = []
        self._captured_errors[app_id].append(report)
        return report

    async def report_error(self, *, report: ErrorReport) -> ReportResult:
        """Send an ErrorReport to the configured transport.

        Checks consent before reporting. Without consent, returns error.

        Args:
            report: An ErrorReport to transmit.

        Returns:
            ReportResult: With success status and target identifier.
        """
        if not await self.is_consent_granted(app_id=report.app_id):
            return ReportResult(
                success=False,
                target="in_memory",
                error="Consent not granted for this app",
            )

        self._reported_errors.append(report)
        return ReportResult(success=True, target="in_memory")

    async def send_telemetry(
        self,
        *,
        app_id: str,
        metrics: dict[str, Any],
    ) -> None:
        """Send telemetry metrics via OTLP transport.

        Only stores if consent is granted.

        Args:
            app_id: The application identifier.
            metrics: Dictionary of metric key-value pairs.
        """
        self._consent_store.add_telemetry(
            app_id=app_id,
            metrics={k: v for k, v in metrics.items()},  # type: ignore[misc]
        )

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery.

        Returns:
            dict[str, Any]: JSON Schema describing the MaintenanceManager interface.
        """
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "MaintenanceManager",
            "type": "object",
            "description": (
                "Manages GDPR-compliant error reporting, PII scrubbing, "
                "telemetry transport, and structured issue creation."
            ),
            "properties": {
                "is_consent_granted": {
                    "type": "object",
                    "description": "Check whether the user has granted telemetry consent.",
                },
                "request_consent": {
                    "type": "object",
                    "description": "Record explicit user consent for telemetry.",
                },
                "revoke_consent": {
                    "type": "object",
                    "description": "Revoke consent and purge all telemetry data.",
                },
                "capture_error": {
                    "type": "object",
                    "description": "Capture an error with PII scrubbing.",
                },
                "report_error": {
                    "type": "object",
                    "description": "Send an ErrorReport to the configured transport.",
                },
                "send_telemetry": {
                    "type": "object",
                    "description": "Send telemetry metrics via OTLP transport.",
                },
            },
        }


def _detect_os() -> str:
    """Detect the current operating system.

    Returns:
        str: One of ``"windows"``, ``"macos"``, ``"linux"``.
    """
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
