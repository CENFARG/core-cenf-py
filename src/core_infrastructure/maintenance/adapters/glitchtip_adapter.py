"""GlitchTipAdapter — self-hosted Sentry-compatible error backend.

Sends errors to a GlitchTip (self-hosted Sentry) instance using the
Sentry-compatible store API. Supports DSN-based configuration with
automatic host, protocol, and project ID extraction.

Security:
    - DSN contains a secret key — never log the full DSN.
    - Data is sent over HTTPS in production.
Observability:
    - Fire-and-forget: never blocks the main flow.
    - Sentry-compatible payload format.
@ai-directive: Use GlitchTipAdapter to send errors to a self-hosted
    Sentry-compatible backend (GlitchTip). Errors are sent to the
    store endpoint with Sentry-compatible format.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from urllib.parse import urlparse

import aiohttp

from core_infrastructure.maintenance.models import ErrorReport, ReportResult


class GlitchTipAdapter:
    """GlitchTip (Sentry-compatible) error reporting adapter.

    Sends errors to a GlitchTip instance using its Sentry-compatible
    store API. DSN format: ``scheme://key@host/project_id``

    Usage::

        adapter = GlitchTipAdapter(dsn="https://key@glitchtip.example.com/1")
        result = await adapter.report_error(report=error_report)
    """

    def __init__(self, dsn: str) -> None:
        """Initialize the GlitchTip adapter.

        Args:
            dsn: GlitchTip DSN (e.g., "https://key@glitchtip.example.com/1").
        """
        self._dsn = dsn
        self._parsed_dsn = self._parse_dsn(dsn)

    @staticmethod
    def _parse_dsn(dsn: str) -> dict[str, str]:
        """Parse a GlitchTip DSN into components.

        Args:
            dsn: The DSN string to parse.

        Returns:
            dict: Parsed components with keys: scheme, public_key, host, port, project_id.
        """
        parsed = urlparse(dsn)
        host = parsed.hostname or "localhost"
        port = str(parsed.port) if parsed.port else ("443" if parsed.scheme == "https" else "80")
        project_id = parsed.path.strip("/").split("/")[0] if parsed.path else "1"
        return {
            "scheme": parsed.scheme,
            "public_key": parsed.username or "",
            "host": host,
            "port": port,
            "project_id": project_id,
        }

    async def report_error(self, *, report: ErrorReport) -> ReportResult:
        """Send an error to GlitchTip via the Sentry-compatible store API.

        Args:
            report: The ErrorReport to send.

        Returns:
            ReportResult: Success or failure result.
        """
        try:
            dsn = self._parsed_dsn
            scheme = dsn["scheme"]
            host = dsn["host"]
            port = dsn["port"]
            project_id = dsn["project_id"]
            public_key = dsn["public_key"]

            base_url = f"{scheme}://{host}"
            if port not in ("80", "443"):
                base_url += f":{port}"

            url = f"{base_url}/api/{project_id}/store/"

            # Sentry-compatible payload
            payload: dict[str, object] = {
                "event_id": _generate_event_id(),
                "message": report.message,
                "culprit": report.app_id,
                "timestamp": report.timestamp.isoformat(),
                "level": report.severity.lower(),
                "platform": "python",
                "sentry.interfaces.Exception": {
                    "values": [
                        {
                            "type": report.message.split(":")[0] if ":" in report.message else "Error",
                            "value": report.message,
                            "stacktrace": {
                                "frames": _parse_stack_frames(report.stack_trace),
                            },
                        }
                    ],
                },
                "tags": {
                    "app_id": report.app_id,
                    "version": report.version,
                    "os": report.os,
                },
                "extra": report.context or {},
            }

            headers = {
                "X-Sentry-Auth": (
                    f"Sentry sentry_version=7, sentry_key={public_key}, "
                    f"sentry_client=core-cenf-m24/0.1.0"
                ),
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session, session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 400:
                    body = await resp.json()
                    error_msg = str(body.get("error", body.get("detail", f"HTTP {resp.status}")))
                    return ReportResult(
                        success=False,
                        target="glitchtip",
                        error=error_msg,
                    )

            return ReportResult(success=True, target="glitchtip")

        except Exception as exc:
            return ReportResult(
                success=False,
                target="glitchtip",
                error=str(exc),
            )


def _generate_event_id() -> str:
    """Generate a 32-char hex event ID (Sentry-compatible).

    Returns:
        str: A 32-character lowercase hex string.
    """
    import hashlib
    import os

    return hashlib.md5(os.urandom(32)).hexdigest()


def _parse_stack_frames(stack_trace: str) -> list[dict[str, str]]:
    """Parse a stack trace string into Sentry-compatible frame objects.

    Args:
        stack_trace: The raw stack trace string.

    Returns:
        list[dict]: List of frame objects with filename, function, lineno.
    """
    frames: list[dict[str, str]] = []
    for line in stack_trace.split("\n"):
        line = line.strip()
        if 'File "' in line:
            # Parse:   File "path/to/file.py", line 10, in function_name
            try:
                parts = line.split('"')
                filename = parts[1] if len(parts) > 1 else "<unknown>"
                rest = parts[2] if len(parts) > 2 else ""
                lineno = ""
                func = "<module>"
                if "line " in rest:
                    lineno_part = rest.split("line ")[1].split(",")[0].strip()
                    lineno = lineno_part
                if "in " in rest:
                    func = rest.split("in ")[1].strip()
                frames.append({
                    "filename": filename,
                    "function": func,
                    "lineno": lineno,
                })
            except (IndexError, ValueError):
                frames.append({"filename": "<unknown>", "function": "<module>", "lineno": "0"})
    return frames
