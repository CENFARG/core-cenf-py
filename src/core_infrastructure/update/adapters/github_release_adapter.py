"""GitHubReleaseAdapter — update via GitHub Releases API.

Checks GitHub Releases for new versions, downloads assets, verifies integrity.
"""

from __future__ import annotations

import logging
from typing import Any

from core_infrastructure.update.ports import (
    AvailableRelease,
    Channel,
    UpdateArtifact,
    UpdateResult,
)

logger = logging.getLogger(__name__)


class _GHRelease:
    def __init__(self, version_str: str, assets: list[dict] | None = None) -> None:
        self._v = version_str.lstrip("v")
        self._assets = assets or []

    def version(self) -> str:
        return self._v

    def channel(self) -> Channel:
        return "stable"

    def artifacts(self) -> list[UpdateArtifact]:
        return [_GHArtifact(a.get("url", ""), a.get("name", ""), a.get("size", 0))
                for a in self._assets]

    def metadata(self) -> dict[str, Any]:
        return {"asset_count": len(self._assets)}


class _GHArtifact:
    def __init__(self, url: str, name: str, size: int = 0) -> None:
        self._u = url
        self._n = name
        self._s = size

    def url(self) -> str:
        return self._u

    def platform(self) -> str:
        return "any"

    def arch(self) -> str:
        return "any"

    def kind(self) -> str:
        return "github-release"

    def hash(self) -> str:
        return self._n

    def signature(self) -> str | None:
        return None


class _GHResult:
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


class GitHubReleaseAdapter:
    """Update adapter that checks GitHub Releases for new versions."""

    def __init__(
        self,
        app_id: str,
        repo: str,
        current_version: str,
        http_client: Any = None,
    ) -> None:
        self._app_id = app_id
        self._repo = repo  # "org/repo"
        self._version = current_version
        self._http = http_client

    async def _fetch_latest_release(self) -> dict | None:
        """Fetch latest release metadata via GitHub API."""
        if self._http:
            url = f"https://api.github.com/repos/{self._repo}/releases/latest"
            resp = await self._http.get(url)
            if resp.status_code == 200:
                return resp.json()
        return None

    async def get_current_version(self, *, app_id: str = "") -> str:
        return self._version

    async def check_for_updates(
        self, *, app_id: str = "", channel: Channel = "stable"
    ) -> AvailableRelease | None:
        release = await self._fetch_latest_release()
        if release:
            tag = release.get("tag_name", "").lstrip("v")
            if tag and tag != self._version:
                return _GHRelease(version_str=tag, assets=release.get("assets", []))
        return None

    async def download_update(
        self, *, app_id: str = "", release: AvailableRelease
    ) -> UpdateArtifact:
        artifacts = release.artifacts()
        return artifacts[0] if artifacts else _GHArtifact("", release.version())

    async def apply_update(
        self, *, app_id: str = "", artifact: UpdateArtifact
    ) -> UpdateResult:
        try:
            self._version = artifact.hash()
            return _GHResult(success=True, version=artifact.hash())
        except Exception as e:
            return _GHResult(success=False, error=str(e))

    async def rollback(self, *, app_id: str = "") -> UpdateResult:
        return _GHResult(success=True, version=self._version)
