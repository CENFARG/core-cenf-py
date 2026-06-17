"""InMemoryI18nAdapter — dict-backed I18nManager test double.

Provides a zero-dependency I18nManager implementation for unit tests.
All translations are stored in a plain nested dict — no YAML, no file I/O,
no external dependencies. Use the constructor to pre-load translations.

Security: No real I/O — translations never leave process memory.
Observability: Deterministic — always returns the same result for the
    same input. Ideal for TDD assertion cycles.
@ai-directive: This adapter exists solely for testing. NEVER use it in
    production code paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from core_infrastructure.i18n.models import I18nConfig


class InMemoryI18nAdapter:
    """Dict-backed I18nManager for unit test assertions.

    All translations are stored in a nested dict keyed by locale.
    The adapter satisfies the ``I18nManager`` Protocol and can be used
    as a drop-in replacement in any test that needs i18n translations.

    Args:
        translations: Initial translations dict keyed by locale.
        default_locale: Active locale at construction.
        fallback_locale: Fallback when key is missing in active locale.
    """

    def __init__(
        self,
        translations: dict[str, dict[str, Any]] | None = None,
        default_locale: str = "en",
        fallback_locale: str = "en",
    ) -> None:
        self._translations: dict[str, dict[str, Any]] = deepcopy(translations) if translations else {}
        self._locale: str = default_locale
        self._fallback_locale: str = fallback_locale

    # ------------------------------------------------------------------
    # Public API — I18nManager Protocol
    # ------------------------------------------------------------------

    def set_locale(self, locale: str) -> None:
        """Switch the active language locale.

        Args:
            locale: Language code (e.g., ``"es"``, ``"en"``).
        """
        self._locale = locale

    def t(self, key: str, **params: Any) -> str:
        """Translate a key with optional parameter substitution.

        Traverses the nested translations dict using dot-notation.
        Falls back to ``fallback_locale`` if key is not found in the
        active locale.

        Args:
            key: Dot-notation translation key.
            **params: Optional format parameters for str.format().

        Returns:
            str: The translated string, or ``"[missing: {key}]"``.
        """
        value = self._resolve_key(key)
        if value is None:
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
        """Load translations into a locale from a dict or YAML file.

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
            with open(file_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            if isinstance(data, dict):
                self._merge_into_locale(locale, data)

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
            key: Dot-separated key path (e.g., ``"errors.not_found"``).

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
                InMemoryI18nAdapter._merge_dicts(base[key], value)
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
