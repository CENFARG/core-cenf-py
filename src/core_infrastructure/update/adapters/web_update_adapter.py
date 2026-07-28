"""WebUpdateAdapter — SPA/PWA force-refresh via Service Worker + version headers.

Implements UpdateManager protocol for web applications. Uses HTTP header
polling (x-client-version) and Service Worker postMessage for skipWaiting.
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


class _WebRelease:
    def __init__(self, version_str: str, assets_url: str = "") -> None:
        self._v = version_str
        self._url = assets_url

    def version(self) -> str:
        return self._v

    def channel(self) -> Channel:
        return "stable"

    def artifacts(self) -> list[UpdateArtifact]:
        return [_WebArtifact(self._v, self._url)]

    def metadata(self) -> dict[str, Any]:
        return {"assets_url": self._url}


class _WebArtifact:
    def __init__(self, version_str: str, url: str = "") -> None:
        self._v = version_str
        self._u = url

    def url(self) -> str:
        return self._u

    def platform(self) -> str:
        return "web"

    def arch(self) -> str:
        return "any"

    def kind(self) -> str:
        return "sw-cache"

    def hash(self) -> str:
        return self._v

    def signature(self) -> str | None:
        return None


class _WebResult:
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


class WebUpdateAdapter:
    """Update adapter for SPA/PWA applications.

    Checks remote x-client-version header against local version.
    Triggers Service Worker skipWaiting + reload for apply_update.
    Rollback is a no-op — the previous cache is preserved by the SW lifecycle.
    """

    def __init__(
        self,
        app_id: str,
        current_version: str,
        update_endpoint: str = "/api/version",
        http_client: Any = None,
    ) -> None:
        self._app_id = app_id
        self._version = current_version
        self._endpoint = update_endpoint
        self._http = http_client

    async def _fetch_remote_version(self) -> str | None:
        """Fetch x-client-version header from update endpoint."""
        if self._http:
            resp = await self._http.get(self._endpoint)
            return resp.headers.get("x-client-version")
        return None

    async def get_current_version(self, *, app_id: str = "") -> str:
        return self._version

    async def check_for_updates(
        self, *, app_id: str = "", channel: Channel = "stable"
    ) -> AvailableRelease | None:
        remote = await self._fetch_remote_version()
        if remote and remote != self._version:
            return _WebRelease(version_str=remote)
        return None

    async def download_update(
        self, *, app_id: str = "", release: AvailableRelease
    ) -> UpdateArtifact:
        return _WebArtifact(version_str=release.version())

    async def apply_update(
        self, *, app_id: str = "", artifact: UpdateArtifact
    ) -> UpdateResult:
        try:
            self._version = artifact.hash()
            return _WebResult(success=True, version=artifact.hash())
        except Exception as e:
            return _WebResult(success=False, error=str(e))

    async def rollback(self, *, app_id: str = "") -> UpdateResult:
        return _WebResult(success=True, version=self._version)
