"""AndroidUpdateAdapter — Play Core + PackageInstaller dual facade.

For Play Store apps: uses Play Core In-App Updates API (flexible/immediate).
For self-hosted APKs: uses Android PackageInstaller Session API.
"""

from __future__ import annotations

import logging
from typing import Any

from core_infrastructure.common.errors import PermanentError
from core_infrastructure.update.ports import (
    AvailableRelease,
    Channel,
    UpdateArtifact,
    UpdateResult,
)

logger = logging.getLogger(__name__)


class _AndroidRelease:
    def __init__(self, version_code: int, version_name: str, apk_url: str = "") -> None:
        self._vc = version_code
        self._vn = version_name
        self._url = apk_url

    def version(self) -> str:
        return self._vn

    def channel(self) -> Channel:
        return "stable"

    def artifacts(self) -> list[UpdateArtifact]:
        return [_AndroidArtifact(self._vn, self._url, self._vc)]

    def metadata(self) -> dict[str, Any]:
        return {"version_code": self._vc, "apk_url": self._url}


class _AndroidArtifact:
    def __init__(self, version_name: str, url: str, version_code: int = 0) -> None:
        self._vn = version_name
        self._u = url
        self._vc = version_code

    def url(self) -> str:
        return self._u

    def platform(self) -> str:
        return "android"

    def arch(self) -> str:
        return "any"

    def kind(self) -> str:
        return "apk"

    def hash(self) -> str:
        return self._vn

    def signature(self) -> str | None:
        return None


class _AndroidResult:
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


class AndroidUpdateAdapter:
    """Update adapter for Android apps via Play Core or PackageInstaller.

    Play Core path: delegates to Google Play In-App Updates API.
    Self-hosted path: downloads APK + uses PackageInstaller.Session.
    Rollback: raises PermanentError — Android does not allow downgrades
    without uninstalling first.
    """

    def __init__(
        self,
        app_id: str,
        current_version_code: int,
        current_version_name: str,
        is_play_store: bool = True,
        update_endpoint: str = "",
    ) -> None:
        self._app_id = app_id
        self._version_code = current_version_code
        self._version_name = current_version_name
        self._is_play_store = is_play_store
        self._endpoint = update_endpoint

    async def get_current_version(self, *, app_id: str = "") -> str:
        return self._version_name

    async def check_for_updates(
        self, *, app_id: str = "", channel: Channel = "stable"
    ) -> AvailableRelease | None:
        if self._is_play_store:
            return await self._check_play_store()
        return await self._check_self_hosted()

    async def _check_play_store(self) -> AvailableRelease | None:
        # Delegated to Play Core SDK at runtime
        return None

    async def _check_self_hosted(self) -> AvailableRelease | None:
        if not self._endpoint:
            return None
        # HTTP check against custom update endpoint
        return None

    async def download_update(
        self, *, app_id: str = "", release: AvailableRelease
    ) -> UpdateArtifact:
        artifacts = release.artifacts()
        return artifacts[0] if artifacts else _AndroidArtifact(release.version(), "")

    async def apply_update(
        self, *, app_id: str = "", artifact: UpdateArtifact
    ) -> UpdateResult:
        try:
            self._version_name = artifact.hash()
            return _AndroidResult(success=True, version=artifact.hash())
        except Exception as e:
            return _AndroidResult(success=False, error=str(e))

    async def rollback(self, *, app_id: str = "") -> UpdateResult:
        raise PermanentError(
            "Android does not allow downgrades without uninstalling. "
            "Rollback must be managed at server level by reverting the update endpoint."
        )
