"""DiscordAlertAdapter — webhook-based Discord alerts for error reporting.

Sends rich embed messages to Discord via webhook URLs. Stack traces
longer than 2000 characters are truncated. Error severity maps to
embed color (ERROR=red, WARNING=yellow, CRITICAL=dark red).

Security:
    - Webhook URL is stored in config, never logged.
    - Stack traces are truncated to prevent abuse.
Observability:
    - Fire-and-forget: never blocks the main flow.
@ai-directive: Use DiscordAlertAdapter to send error alerts to Discord.
    Stack traces are truncated to 2000 chars. Never log the webhook URL.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import aiohttp

from core_infrastructure.maintenance.models import ErrorReport, ReportResult

_SEVERITY_COLORS: dict[str, int] = {
    "TRACE": 0x7289DA,  # Discord blurple
    "DEBUG": 0x808080,  # Gray
    "INFO": 0x00FF00,  # Green
    "WARNING": 0xFFFF00,  # Yellow
    "ERROR": 0xFF0000,  # Red
    "CRITICAL": 0x8B0000,  # Dark red
}

_MAX_STACK_LENGTH = 2000


class DiscordAlertAdapter:
    """Webhook-based Discord alert adapter.

    Sends error reports as rich Discord embeds. Stack traces are
    truncated to 2000 characters. Fire-and-forget semantics.

    Usage::

        adapter = DiscordAlertAdapter(webhook_url="https://discord.com/api/webhooks/...")
        result = await adapter.report_error(report=error_report)
    """

    def __init__(self, webhook_url: str) -> None:
        """Initialize the Discord adapter.

        Args:
            webhook_url: The Discord webhook URL.
        """
        self._webhook_url = webhook_url

    async def report_error(self, *, report: ErrorReport) -> ReportResult:
        """Send an error report as a Discord embed.

        Args:
            report: The ErrorReport to send.

        Returns:
            ReportResult: Success or failure result.
        """
        try:
            stack = report.stack_trace
            # Build description: message + stack (with truncation)
            desc = report.message
            if stack:
                desc = f"{report.message}\n\n{stack}"

            if len(desc) > _MAX_STACK_LENGTH:
                trunc_suffix = "\n... (truncated)"
                if stack and len(report.message) < _MAX_STACK_LENGTH:
                    # Keep the message, only truncate stack
                    prefix = f"{report.message}\n\n"
                    available = _MAX_STACK_LENGTH - len(prefix) - len(trunc_suffix)
                    desc = prefix + stack[:max(0, available)] + trunc_suffix
                else:
                    desc = desc[: _MAX_STACK_LENGTH - len(trunc_suffix)] + trunc_suffix

            embed: dict[str, object] = {
                "title": f"Error in {report.app_id} ({report.severity})",
                "description": desc,
                "color": _SEVERITY_COLORS.get(report.severity, 0xFF0000),
                "fields": [
                    {"name": "App", "value": report.app_id, "inline": True},
                    {"name": "Version", "value": report.version, "inline": True},
                    {"name": "OS", "value": report.os, "inline": True},
                    {"name": "Message", "value": report.message[:1000], "inline": False},
                ],
                "timestamp": report.timestamp.isoformat(),
            }

            payload: dict[str, object] = {
                "embeds": [embed],
                "username": "CENF Error Reporter",
            }

            async with aiohttp.ClientSession() as session, session.post(
                self._webhook_url,
                json=payload,  # type: ignore[arg-type]
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.json()
                    error_msg = str(body.get("error", body.get("message", f"HTTP {resp.status}")))
                    return ReportResult(
                        success=False,
                        target="discord",
                        error=error_msg,
                    )

            return ReportResult(success=True, target="discord")

        except Exception as exc:
            return ReportResult(
                success=False,
                target="discord",
                error=str(exc),
            )
