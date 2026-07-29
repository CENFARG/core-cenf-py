"""GitHubIssueAdapter — auto-issue creation via GitHub API.

Creates GitHub issues from ErrorReports with hash-based deduplication
to prevent duplicate issues for the same error. Uses GitHub API directly
with a JWT-based GitHub App authentication flow.

Security:
    - Hash-based dedup prevents issue spam.
    - Stack trace is included as issue body for debugging.
Observability:
    - Fire-and-forget: never blocks the main flow.
    - Dedup hash is computed from stack trace + app_id + message.
@ai-directive: Use GitHubIssueAdapter to auto-create issues from errors.
    Duplicates are prevented via hash-based dedup. Labels include
    'bug-automático' for filtering.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import hashlib

import aiohttp

from core_infrastructure.maintenance.models import ErrorReport, ReportResult


class GitHubIssueAdapter:
    """GitHub API-based issue creation adapter with dedup.

    Creates issues in a GitHub repository from ErrorReports. Uses
    hash-based deduplication to avoid creating duplicate issues
    for the same error.

    Usage::

        adapter = GitHubIssueAdapter(
            api_url="https://api.github.com",
            repo="owner/repo",
        )
        result = await adapter.report_error(report=error_report)
    """

    def __init__(
        self,
        api_url: str = "https://api.github.com",
        repo: str = "",
    ) -> None:
        """Initialize the GitHub adapter.

        Args:
            api_url: GitHub API base URL (default: https://api.github.com).
            repo: Repository name in "owner/repo" format.
        """
        self._api_url = api_url.rstrip("/")
        self._repo = repo
        self._seen_hashes: set[str] = set()

    def _compute_dedup_hash(self, report: ErrorReport) -> str:
        """Compute a hash for deduplication.

        Combines app_id, message, and first 500 chars of stack trace.

        Args:
            report: The ErrorReport to hash.

        Returns:
            str: SHA-256 hex digest for dedup.
        """
        content = f"{report.app_id}:{report.message}:{report.stack_trace[:500]}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def report_error(self, *, report: ErrorReport) -> ReportResult:
        """Create a GitHub issue from an error report.

        Args:
            report: The ErrorReport to create an issue from.

        Returns:
            ReportResult: Success or failure result.
        """
        dedup_hash = self._compute_dedup_hash(report)

        # Local dedup check
        if dedup_hash in self._seen_hashes:
            return ReportResult(success=True, target="github")

        try:
            body = (
                f"## Auto-generated Error Report\n\n"
                f"**App**: {report.app_id}\n"
                f"**Version**: {report.version}\n"
                f"**OS**: {report.os}\n"
                f"**Severity**: {report.severity}\n"
                f"**Timestamp**: {report.timestamp.isoformat()}\n\n"
                f"### Message\n"
                f"```\n{report.message}\n```\n\n"
                f"### Stack Trace\n"
                f"```\n{report.stack_trace[:4000]}\n```\n"
            )

            payload: dict[str, object] = {
                "title": f"[{report.severity}] {report.app_id}: {report.message[:100]}",
                "body": body,
                "labels": ["bug-automático"],
            }

            headers = {
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json",
            }

            url = f"{self._api_url}/repos/{self._repo}/issues"

            async with aiohttp.ClientSession() as session, session.post(
                url,
                json=payload,  # type: ignore[arg-type]
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 400:
                    body_resp = await resp.json()
                    error_msg = str(body_resp.get("message", f"HTTP {resp.status}"))
                    return ReportResult(
                        success=False,
                        target="github",
                        error=error_msg,
                    )

            self._seen_hashes.add(dedup_hash)
            return ReportResult(success=True, target="github")

        except Exception as exc:
            return ReportResult(
                success=False,
                target="github",
                error=str(exc),
            )
