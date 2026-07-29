"""CENFServerAdapter — REST API transport to CENF Server.

Sends error reports and telemetry to a central CENF Server via REST
API. Uses aiohttp for async HTTP transport. Fire-and-forget semantics
to avoid blocking the main application flow.

Security:
    - Server URL is configurable, never hardcoded.
    - Errors are sent over HTTPS in production.
Observability:
    - Telemetry is sent to a separate endpoint from errors.
@ai-directive: Use CENFServerAdapter to send error reports and telemetry
    to the central CENF Server. Errors go to /api/v1/errors, telemetry
    goes to /api/v1/telemetry. Always fire-and-forget.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

import aiohttp

from core_infrastructure.maintenance.models import ErrorReport, ReportResult


class CENFServerAdapter:
    """REST API adapter for CENF Server error reporting and telemetry.

    Sends error reports to POST /api/v1/errors and telemetry to
    POST /api/v1/telemetry on the configured CENF Server.

    Usage::

        adapter = CENFServerAdapter(server_url="https://cenf.example.com")
        result = await adapter.report_error(report=error_report)
        await adapter.send_telemetry(app_id="my-app", metrics={"errors": 5})
    """

    def __init__(self, server_url: str = "") -> None:
        """Initialize the CENF Server adapter.

        Args:
            server_url: Base URL of the CENF Server (e.g., https://cenf.example.com).
        """
        self._server_url = server_url.rstrip("/")

    async def report_error(self, *, report: ErrorReport) -> ReportResult:
        """Send an error report to the CENF Server.

        Args:
            report: The ErrorReport to send.

        Returns:
            ReportResult: Success or failure result.
        """
        try:
            url = f"{self._server_url}/api/v1/errors"
            payload = report.model_dump()
            # Convert datetime to isoformat for JSON serialization
            payload["timestamp"] = payload["timestamp"].isoformat()

            async with aiohttp.ClientSession() as session, session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.json()
                    error_msg = str(body.get("error", body.get("message", f"HTTP {resp.status}")))
                    return ReportResult(
                        success=False,
                        target="cenf-server",
                        error=error_msg,
                    )

            return ReportResult(success=True, target="cenf-server")

        except Exception as exc:
            return ReportResult(
                success=False,
                target="cenf-server",
                error=str(exc),
            )

    async def send_telemetry(
        self,
        *,
        app_id: str,
        metrics: dict[str, Any],
    ) -> None:
        """Send telemetry metrics to the CENF Server.

        Args:
            app_id: The application identifier.
            metrics: Dictionary of metric key-value pairs.
        """
        try:
            url = f"{self._server_url}/api/v1/telemetry"
            payload: dict[str, object] = {
                "app_id": app_id,
                "metrics": {k: v for k, v in metrics.items()},
            }

            async with aiohttp.ClientSession() as session, session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 400:
                    pass  # Fire-and-forget: ignore errors

        except Exception:
            pass  # Fire-and-forget: never block
