"""YamlI18nAdapter — YAML-backed I18nManager production adapter.

Provides multi-language translation support by reading YAML files per
locale and storing them in a nested dict. The active locale is controlled
by ConfigManager (``i18n.locale`` key) and can be switched at runtime.

Translations support str.format() parameter substitution with dot-notation
key traversal for nested keys (e.g., ``"errors.not_found"``).

Security: Translation files are plain YAML — no code execution.
Observability: Locale switches log at INFO level; missing keys log at
    WARNING level via LoggerManager.
@ai-directive: NEVER throw on missing translation — return ``[missing: key]``
    as a visible fallback.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.i18n.models import I18nConfig
from core_infrastructure.logger.ports import LoggerManager


class YamlI18nAdapter:
    """YAML-backed I18nManager for production use.

    Reads locale from ConfigManager at construction (``"i18n.locale"`` key,
    defaults to ``"en"``). Translations are loaded via ``load_translations()``
    from YAML files or dicts.

    Args:
        config_manager: ConfigManager for reading active locale.
        logger_manager: LoggerManager for visibility into locale switches.
        fallback_locale: Locale to use when a key is missing in the active
            locale. Defaults to ``"en"``.
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        logger_manager: LoggerManager,
        fallback_locale: str = "en",
    ) -> None:
        self._config: ConfigManager = config_manager
        self._logger: LoggerManager = logger_manager
        self._fallback_locale: str = fallback_locale
        self._translations: dict[str, dict[str, Any]] = {}
        # Read active locale from config
        self._locale: str = self._config.get_string("i18n.locale", "en")

    # ------------------------------------------------------------------
    # Public API — I18nManager Protocol
    # ------------------------------------------------------------------

    def set_locale(self, locale: str) -> None:
        """Switch the active language locale.

        Emits an INFO log recording the locale transition.

        Args:
            locale: Language code (e.g., ``"es"``, ``"en"``).
        """
        old = self._locale
        self._locale = locale
        self._logger.info(
            "I18n locale switched",
            old_locale=old,
            new_locale=locale,
        )

    def t(self, key: str, **params: Any) -> str:
        """Translate a key with optional parameter substitution.

        Traverses the nested translations dict using dot-notation.
        Falls back to ``fallback_locale`` if key is not found in the
        active locale. If the key is not found in any locale, returns
        ``"[missing: {key}]"``.

        Args:
            key: Dot-notation translation key.
            **params: Optional format parameters for str.format().

        Returns:
            str: The translated string, or ``"[missing: {key}]"``.
        """
        value = self._resolve_key(key)
        if value is None:
            self._logger.warn(
                "I18n missing translation",
                key=key,
                locale=self._locale,
            )
            return f"[missing: {key}]"
        if params:
            return str(value).format(**params)
        return str(value)

    def get_available_locales(self) -> list[str]:
        """Return all currently loaded locales.

        Returns:
            list[str]: Sorted list of locale codes.
        """
        return sorted(self._translations.keys())

    def load_translations(self, path: str | dict[str, Any], locale: str) -> None:
        """Load translations into a locale from a YAML file or dict.

        If ``path`` is a dict, it is merged directly. If it is a string
        path to a YAML file, the file is parsed and merged. If the file
        does not exist, a warning is logged and no data is loaded.

        Args:
            path: Either a dict of translations or a file path.
            locale: Target locale code.
        """
        if isinstance(path, dict):
            self._merge_into_locale(locale, path)
            return

        file_path = Path(path)
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict):
                    self._merge_into_locale(locale, data)
                    self._logger.info(
                        "I18n translations loaded",
                        path=str(file_path),
                        locale=locale,
                        key_count=len(data),
                    )
                else:
                    self._logger.warn(
                        "I18n YAML file root is not a mapping",
                        path=str(file_path),
                        locale=locale,
                    )
            except yaml.YAMLError as exc:
                self._logger.warn(
                    "I18n failed to parse YAML file",
                    path=str(file_path),
                    locale=locale,
                    error=str(exc),
                )
        else:
            self._logger.warn(
                "I18n translation file not found",
                path=str(file_path),
                locale=locale,
            )

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing I18nConfig.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return I18nConfig.model_json_schema()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_key(self, key: str) -> Any | None:
        """Traverse translations dict using dot-notation key.

        Tries the active locale first, then the fallback locale.

        Args:
            key: Dot-separated key path.

        Returns:
            Any: The resolved value, or ``None`` if not found.
        """
        for locale in (self._locale, self._fallback_locale):
            result = self._traverse(self._translations.get(locale, {}), key)
            if result is not None:
                return result
        return None

    @staticmethod
    def _traverse(data: dict[str, Any], key: str) -> Any | None:
        """Walk a nested dict using dot-separated keys.

        Args:
            data: The dict to traverse.
            key: Dot-separated key path.

        Returns:
            Any: The leaf value, or ``None`` if any segment is missing.
        """
        parts = key.split(".")
        current: Any = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    @staticmethod
    def _merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> None:
        """Recursively merge overlay into base (mutates base).

        Args:
            base: Target dict to merge into.
            overlay: Source dict with new/updated keys.
        """
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                YamlI18nAdapter._merge_dicts(base[key], value)
            else:
                base[key] = deepcopy(value) if isinstance(value, dict) else value

    def _merge_into_locale(self, locale: str, data: dict[str, Any]) -> None:
        """Merge translation data into the given locale.

        Args:
            locale: Target locale code.
            data: Translation key-value pairs to merge.
        """
        if locale not in self._translations:
            self._translations[locale] = {}
        self._merge_dicts(self._translations[locale], data)
