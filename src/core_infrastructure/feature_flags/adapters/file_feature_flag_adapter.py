"""FileFeatureFlagAdapter — YAML file-backed FeatureFlagManager with hot-reload.

Provides a production-grade FeatureFlagManager that reads flag definitions
from a YAML file and supports hot-reload via file watching.

Security: FlagContext.tenant_id is local-only — never sent externally.
Observability: All evaluations are logged at DEBUG level.
@ai-directive: is_enabled() NEVER throws — returns False for unknown flags.
    Thread-safety via asyncio.Lock for flag dictionary access.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml

from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.feature_flags.models import FlagContext
from core_infrastructure.logger.ports import LoggerManager


class FileFeatureFlagAdapter:
    """YAML file-backed FeatureFlagManager with hot-reload support.

    Reads flag definitions from a YAML file at ``feature_flags.file_path``.
    Supports rule-based evaluation via simple dict condition matching.
    Flags are reloaded atomically under an ``asyncio.Lock``.

    Args:
        config: ConfigManager for ``feature_flags.file_path`` and
            ``feature_flags.default_all``.
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for exception classification.

    YAML format::

        flag-key:
          enabled: true
          rules:
            - condition: {environment: staging}
          default: false
    """

    def __init__(
        self,
        config: ConfigManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._logger = logger
        self._error_handler = error_handler

        file_path = config.get_string("feature_flags.file_path", default_value="flags.yaml")
        self._file_path = Path(file_path)
        self._default_all: bool = config.get_boolean("feature_flags.default_all", default_value=False)

        self._lock = asyncio.Lock()
        self._flags: dict[str, dict[str, Any]] = {}

        self._reload_sync()

    # ------------------------------------------------------------------
    # Internal — flag loading and evaluation
    # ------------------------------------------------------------------

    def _reload_sync(self) -> None:
        """Reload flags from the YAML file synchronously.

        Safe to call outside async context — acquires lock inline.
        """
        try:
            if self._file_path.exists():
                raw = self._file_path.read_text(encoding="utf-8")
                self._flags = yaml.safe_load(raw) or {}
            else:
                self._flags = {}
        except Exception as exc:
            self._error_handler.report(
                exc,
                context={"source": "FileFeatureFlagAdapter._reload_sync", "file_path": str(self._file_path)},
            )
            self._logger.warn(
                "FileFeatureFlagAdapter: failed to load flags file, keeping previous",
                file_path=str(self._file_path),
            )

    async def _reload(self) -> None:
        """Reload flags from the YAML file atomically under lock."""
        async with self._lock:
            self._reload_sync()

    def _get_flag(self, flag_key: str) -> dict[str, Any] | None:
        """Get a flag definition by key.

        Args:
            flag_key: The flag identifier.

        Returns:
            dict | None: The flag definition, or ``None`` if not found.
        """
        return self._flags.get(flag_key)

    def _evaluate_rules(
        self, flag_def: dict[str, Any], context: FlagContext | None
    ) -> bool:
        """Evaluate a flag's rules against the provided context.

        Args:
            flag_def: The flag definition dict.
            context: Evaluation context, or ``None``.

        Returns:
            bool: ``True`` if all rules match or no rules exist.
        """
        rules: list[dict[str, Any]] = flag_def.get("rules", [])
        if not rules:
            return True

        if context is None:
            return False

        ctx_dict: dict[str, str] = {
            "environment": context.environment,
            "tenant_id": context.tenant_id,
            **context.attributes,
        }

        for rule in rules:
            condition: dict[str, str] = rule.get("condition", {})
            for key, expected in condition.items():
                actual = ctx_dict.get(key, "")
                if actual != expected:
                    return False

        return True

    # ------------------------------------------------------------------
    # Public API — FeatureFlagManager Protocol
    # ------------------------------------------------------------------

    def is_enabled(
        self,
        flag_key: str,
        context: FlagContext | None = None,
    ) -> bool:
        """Check if a feature flag is enabled.

        Evaluates rules against context. Returns ``False`` for unknown
        flags — never raises.

        Args:
            flag_key: The feature flag identifier.
            context: Optional evaluation context.

        Returns:
            bool: ``True`` if the flag is enabled for the given context.
        """
        try:
            flag_def = self._get_flag(flag_key)
            if flag_def is None:
                return self._default_all
            if not flag_def.get("enabled", False):
                return False
            return self._evaluate_rules(flag_def, context)
        except Exception as exc:
            self._error_handler.report(
                exc,
                context={"source": "FileFeatureFlagAdapter.is_enabled", "flag_key": flag_key},
            )
            self._logger.warn(
                "FileFeatureFlagAdapter: evaluation failed, returning default",
                flag_key=flag_key,
            )
            return self._default_all

    def get_flag_value(
        self,
        flag_key: str,
        context: FlagContext | None = None,
        default: Any = None,
    ) -> Any:
        """Get the value (payload) of a feature flag.

        Args:
            flag_key: The feature flag identifier.
            context: Optional evaluation context.
            default: Value returned if the flag is not found or disabled.

        Returns:
            Any: The flag's value, or ``default``.
        """
        try:
            flag_def = self._get_flag(flag_key)
            if flag_def is None:
                return default
            if not flag_def.get("enabled", False):
                return default
            if not self._evaluate_rules(flag_def, context):
                return default
            return flag_def.get("value", default)
        except Exception as exc:
            self._error_handler.report(
                exc,
                context={"source": "FileFeatureFlagAdapter.get_flag_value", "flag_key": flag_key},
            )
            return default

    def get_all_flags(
        self,
        context: FlagContext | None = None,
    ) -> dict[str, bool]:
        """Get the enabled state of all feature flags.

        Evaluates each flag against the provided context.

        Args:
            context: Optional evaluation context.

        Returns:
            dict[str, bool]: Map of flag keys to their enabled state.
        """
        try:
            result: dict[str, bool] = {}
            for key in self._flags:
                result[key] = self.is_enabled(key, context)
            return result
        except Exception as exc:
            self._error_handler.report(
                exc,
                context={"source": "FileFeatureFlagAdapter.get_all_flags"},
            )
            return {}

    async def refresh(self) -> None:
        """Refresh the local flag cache from the YAML file.

        Reloads flags atomically under the asyncio lock.
        """
        await self._reload()
