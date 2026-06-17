"""I18nManager Protocol — the contract every i18n adapter must satisfy.

Defines the multi-language translation interface consumed by all
infrastructure managers and CENF applications. Adapters (YAML-backed,
in-memory test double) implement this Protocol.

Security: Translation keys are developer-controlled; user input is only
    passed as **params for substitution, never as keys.
Observability: get_json_schema() enables LLM agents to discover available
    locales and configuration keys.
@ai-directive: NEVER throw on missing translation — return [missing: key]
    as a visible fallback so developers can spot untranslated strings.

Author: CENF AI Team
Version: 0.1.0
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class I18nManager(Protocol):
    """Multi-language translation contract for all CENF applications.

    All adapters read the active locale from ConfigManager at construction
    and support switching at runtime via set_locale(). Translations are
    stored as nested dicts keyed by locale, with dot-notation traversal
    for nested keys (e.g., "errors.not_found").

    Rules:
        - t() MUST NEVER raise — return [missing: key] for missing keys.
        - Parameter substitution uses str.format() semantics.
        - load_translations() merges new keys into the locale dict.
        - set_locale() switches the active language immediately.

    @ai-directive: When adding a new locale, update the YAML file AND
        ensure both adapters handle the new locale correctly.
    """

    def set_locale(self, locale: str) -> None:
        """Switch the active language locale.

        Args:
            locale: Language code (e.g., ``"es"``, ``"en"``).
        """
        ...

    def t(self, key: str, **params: Any) -> str:
        """Translate a key with optional parameter substitution.

        Args:
            key: Dot-notation translation key (e.g., ``"greeting"`` or
                ``"errors.not_found"``).
            **params: Optional format parameters for str.format().

        Returns:
            str: The translated string, or ``"[missing: {key}]"`` if the
                key is not found in any locale.
        """
        ...

    def get_available_locales(self) -> list[str]:
        """Return all currently loaded locales.

        Returns:
            list[str]: Sorted list of locale codes (e.g., ``["en", "es"]``).
        """
        ...

    def load_translations(self, path: str | dict[str, Any], locale: str) -> None:
        """Load translations into a locale.

        Args:
            path: Path to a YAML translation file, or a dict of translations.
            locale: Target locale code.
        """
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing I18nConfig.

        Used by LLM agents for tool discovery (AX — Agent Experience).

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        ...
