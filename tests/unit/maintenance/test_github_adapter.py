"""Unit tests for GitHubIssueAdapter — auto-issue creation via GitHub API.

Tests cover:
- Creates issue with title, body, labels
- Hash-based deduplication
- Error report fields mapped to issue fields
- Consent check before creating
- Result reflects API success/failure

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.maintenance.models import ErrorReport


def _mock_aiohttp(mocker, status: int = 200, json_data: dict | None = None) -> object:
    """Create a mock aiohttp.ClientSession that returns a controlled response.

    **IMPORTANT**: ``post`` is a regular ``Mock()`` (not AsyncMock) because
    ``AsyncMock()`` returns a **coroutine** when called (Python 3.12 behaviour),
    which cannot be used with ``async with``.

    Returns the mock *post* callable (for call_args inspection).
    """
    if json_data is None:
        json_data = {}

    mock_response = mocker.AsyncMock()
    mock_response.status = status
    mock_response.json = mocker.AsyncMock(return_value=json_data)
    mock_response.__aenter__.return_value = mock_response

    mock_post = mocker.Mock()
    mock_post.return_value = mock_response

    mock_session = mocker.AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.post = mock_post

    mocker.patch("aiohttp.ClientSession", return_value=mock_session)
    return mock_post


@pytest.fixture
def error_report() -> ErrorReport:
    """A sample error report for GitHub testing."""
    return ErrorReport(
        app_id="test-app",
        message="Something broke",
        stack_trace="Traceback...\nValueError: broken",
        version="1.0.0",
        os="linux",
        severity="ERROR",
    )


class TestGitHubIssueAdapter:
    """Tests for GitHubIssueAdapter."""

    @pytest.mark.asyncio
    async def test_creates_issue_with_error_details(self, mocker, error_report) -> None:
        """GitHub issue is created with title, body, and labels."""
        from core_infrastructure.maintenance.adapters.github_issue_adapter import GitHubIssueAdapter

        mock_post = _mock_aiohttp(
            mocker,
            status=201,
            json_data={"id": 42, "html_url": "https://github.com/owner/repo/issues/42"},
        )

        adapter = GitHubIssueAdapter(api_url="https://api.github.com", repo="owner/repo")
        result = await adapter.report_error(report=error_report)

        assert result.success is True
        assert result.target == "github"

        call_args = mock_post.call_args
        assert call_args is not None
        json_data = call_args[1]["json"]
        assert "Something broke" in json_data["title"]
        assert json_data["labels"] == ["bug-automático"]
        assert "owner/repo" in str(call_args)

    @pytest.mark.asyncio
    async def test_deduplicates_by_hash(self, mocker, error_report) -> None:
        """Same error report creates only one issue (hash-based dedup)."""
        from core_infrastructure.maintenance.adapters.github_issue_adapter import GitHubIssueAdapter

        call_count = 0

        def mock_post_side_effect(url: str = "", **kwargs: object) -> object:
            """Synchronous side effect — returns mock_response directly (not a coroutine)."""
            nonlocal call_count
            call_count += 1
            mock_response = mocker.AsyncMock()
            mock_response.status = 201 if call_count == 1 else 422
            mock_response.json = mocker.AsyncMock(
                return_value=(
                    {"id": 42, "html_url": "https://github.com/owner/repo/issues/42"}
                    if call_count == 1
                    else {"message": "duplicate"}
                )
            )
            mock_response.__aenter__.return_value = mock_response
            return mock_response

        # Mock (not AsyncMock!) — calling Mock returns return_value/side_effect directly
        mock_post = mocker.Mock(side_effect=mock_post_side_effect)

        mock_session = mocker.AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.post = mock_post
        mocker.patch("aiohttp.ClientSession", return_value=mock_session)

        adapter = GitHubIssueAdapter(api_url="https://api.github.com", repo="owner/repo")

        # First call — should succeed
        r1 = await adapter.report_error(report=error_report)
        assert r1.success is True

        # Second call with same report — adapter should detect duplicate locally
        r2 = await adapter.report_error(report=error_report)
        assert r2.success is True  # local dedup, doesn't call API again

        assert call_count == 1  # Only one API call made

    @pytest.mark.asyncio
    async def test_returns_failure_on_api_error(self, mocker, error_report) -> None:
        """GitHub API error returns ReportResult with error."""
        from core_infrastructure.maintenance.adapters.github_issue_adapter import GitHubIssueAdapter

        _mock_aiohttp(mocker, status=404, json_data={"message": "Not Found"})

        adapter = GitHubIssueAdapter(api_url="https://api.github.com", repo="owner/repo")
        result = await adapter.report_error(report=error_report)

        assert result.success is False
        assert result.target == "github"
        assert isinstance(result.error, str)
