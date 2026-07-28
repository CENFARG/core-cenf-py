"""PipUpdateAdapter — Python CLI update via Git SHAs with pip install.

Uses pip install git+https://github.com/org/repo.git@<SHA> to update Python
CLI applications. Maintains update_state.json for current version tracking
and rollback to previous stable SHA.

No direct SOTA precedent — custom design per CENF research (July 2026).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from core_infrastructure.common.errors import PermanentError, TransientError
from core_infrastructure.update.ports import (
    AvailableRelease,
    Channel,
    UpdateArtifact,
    UpdateResult,
)

logger = logging.getLogger(__name__)

_STATE_SCHEMA = {"current_sha", "previous_stable_sha", "app_id", "updated_at"}
"""Required keys in update_state.json."""


class _PipUpdateArtifact:
    """Minimal artifact for pip-based updates."""

    def __init__(self, target_sha: str) -> None:
        self._sha = target_sha

    def url(self) -> str:
        return ""

    def platform(self) -> str:
        return "python-cli"

    def arch(self) -> str:
        return "any"

    def kind(self) -> str:
        return "pip-git"

    def hash(self) -> str:
        return self._sha

    def signature(self) -> str | None:
        return None


class _PipAvailableRelease:
    """Release metadata for a pip-based update."""

    def __init__(self, version_str: str, sha: str) -> None:
        self._v = version_str
        self._sha = sha

    def version(self) -> str:
        return self._v

    def channel(self) -> Channel:
        return "stable"

    def artifacts(self) -> list[UpdateArtifact]:
        return [_PipUpdateArtifact(self._sha)]

    def metadata(self) -> dict:
        return {"sha": self._sha}


class _PipUpdateResult:
    def __init__(self, success: bool, version: str | None = None, error: str | None = None):
        self._ok = success
        self._ver = version
        self._err = error

    def success(self) -> bool:
        return self._ok

    def new_version(self) -> str | None:
        return self._ver

    def error(self) -> str | None:
        return self._err


class PipUpdateAdapter:
    """Update adapter for Python CLI apps via pip install git+https@SHA.

    Manages update_state.json for version tracking and rollback.
    Uses subprocess to invoke pip install for actual installation.
    """

    def __init__(
        self,
        app_id: str,
        repo_url: str,
        state_file: Path | None = None,
    ) -> None:
        self._app_id = app_id
        self._repo_url = repo_url.rstrip("/")
        self._state_file = state_file or Path("update_state.json")
        self._current_sha = ""
        self._previous_stable_sha = ""
        self._load_state()

    # ------------------------------------------------------------------ helpers

    def _load_state(self) -> None:
        """Load update state from JSON file or initialize defaults."""
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._current_sha = data.get("current_sha", "")
            self._previous_stable_sha = data.get("previous_stable_sha", "")
        except (FileNotFoundError, json.JSONDecodeError):
            self._current_sha = ""
            self._previous_stable_sha = ""

    def _save_state(self, new_sha: str, previous_sha: str) -> None:
        """Persist update state to JSON file."""
        self._state_file.write_text(
            json.dumps({
                "app_id": self._app_id,
                "current_sha": new_sha,
                "previous_stable_sha": previous_sha,
                "updated_at": datetime.now(datetime.UTC).isoformat(),
            }, indent=2),
            encoding="utf-8",
        )

    async def _fetch_head_sha(self) -> str:
        """Fetch remote HEAD SHA from GitHub API or equivalent."""
        url = f"{self._repo_url}/commits/main"
        proc = await asyncio.create_subprocess_exec(
            "gh", "api", url, "--jq", ".sha",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise TransientError(f"Failed to fetch HEAD SHA: {stderr.decode().strip()}")
        return stdout.decode().strip()

    async def _pip_install(self, sha: str) -> None:
        """Execute pip install for a specific Git SHA."""
        install_target = f"git+{self._repo_url}.git@{sha}"
        proc = await asyncio.create_subprocess_exec(
            "pip", "install", "--upgrade", install_target,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise TransientError(f"pip install failed: {stderr.decode().strip()}")

    # ------------------------------------------------------------ Protocol impl

    async def get_current_version(self, *, app_id: str = "") -> str:
        if not self._current_sha:
            return "0.0.0"
        return self._current_sha

    async def check_for_updates(
        self, *, app_id: str = "", channel: Channel = "stable"
    ) -> AvailableRelease | None:
        try:
            remote_sha = await self._fetch_head_sha()
        except Exception as e:
            raise TransientError(f"Update check failed: {e}") from e

        if remote_sha != self._current_sha:
            return _PipAvailableRelease(version_str=remote_sha[:7], sha=remote_sha)
        return None

    async def download_update(
        self, *, app_id: str = "", release: AvailableRelease
    ) -> UpdateArtifact:
        sha = release.metadata().get("sha", release.version())
        try:
            await self._pip_install(sha)
        except Exception as e:
            raise TransientError(f"Download/install failed: {e}") from e
        return _PipUpdateArtifact(sha)

    async def apply_update(
        self, *, app_id: str = "", artifact: UpdateArtifact
    ) -> UpdateResult:
        new_sha = artifact.hash()
        previous = self._current_sha

        try:
            self._save_state(new_sha, previous)
            self._current_sha = new_sha
            self._previous_stable_sha = previous
            return _PipUpdateResult(success=True, version=new_sha[:7])
        except Exception as e:
            return _PipUpdateResult(success=False, error=str(e))

    async def rollback(self, *, app_id: str = "") -> UpdateResult:
        if not self._previous_stable_sha:
            raise PermanentError("No rollback state available")

        try:
            await self._pip_install(self._previous_stable_sha)
            self._save_state(self._previous_stable_sha, self._current_sha)
            self._current_sha = self._previous_stable_sha
            return _PipUpdateResult(success=True, version=self._previous_stable_sha[:7])
        except Exception as e:
            return _PipUpdateResult(success=False, error=str(e))
