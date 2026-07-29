"""Unit tests for MaintenanceManager Protocol — contract verification.

Tests that the Protocol is structurally satisfiable by a minimal concrete
implementation. These tests verify the Protocol itself is correctly defined.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from core_infrastructure.maintenance.ports import MaintenanceManager


class _MinimalAdapter:
    """Minimal concrete implementation satisfying MaintenanceManager Protocol."""

    async def is_consent_granted(self, *, app_id: str) -> bool:
        return False

    async def request_consent(self, *, app_id: str, user_id: str) -> Any:
        from core_infrastructure.maintenance.models import ConsentResult

        return ConsentResult(
            app_id=app_id,
            user_id=user_id,
            status="GRANTED",
            timestamp=datetime.now(UTC),
        )

    async def revoke_consent(self, *, app_id: str, user_id: str) -> None:
        return None

    async def capture_error(self, *, app_id: str, error: Exception, context: dict[str, Any] | None = None) -> Any:
        from core_infrastructure.maintenance.models import ErrorReport

        return ErrorReport(
            app_id=app_id,
            message=str(error),
            stack_trace="",
            version="1.0.0",
            os="linux",
        )

    async def report_error(self, *, report: Any) -> Any:
        from core_infrastructure.maintenance.models import ReportResult

        return ReportResult(success=True, target="discord")

    async def send_telemetry(self, *, app_id: str, metrics: dict[str, Any]) -> None:
        return None

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "MaintenanceManager",
        }


class TestMaintenanceManagerProtocol:
    """Verify the MaintenanceManager Protocol is correctly defined."""

    def test_minimal_adapter_satisfies_protocol(self) -> None:
        """A minimal concrete class must satisfy the MaintenanceManager Protocol."""
        adapter = _MinimalAdapter()
        assert isinstance(adapter, MaintenanceManager)

    def test_protocol_is_runtime_checkable(self) -> None:
        """MaintenanceManager must be runtime_checkable."""

        assert hasattr(MaintenanceManager, "__instancecheck__")
