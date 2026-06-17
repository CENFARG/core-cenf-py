"""Unit tests for InMemoryI18nAdapter — dict-backed I18nManager test double.

Tests cover:
- Simple translation without params
- Translation with params (str.format)
- Missing key fallback
- set_locale switching
- Nested key traversal (dot notation)
- load_translations merging
- get_available_locales

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.i18n.adapters.in_memory_i18n_adapter import InMemoryI18nAdapter


class TestInMemoryAdapter:
    """Verify InMemoryI18nAdapter satisfies the I18nManager contract."""

    def test_simple_translation(self) -> None:
        """t() returns translated string for active locale without params."""
        adapter = InMemoryI18nAdapter(
            translations={"en": {"greeting": "Hello"}},
            default_locale="en",
        )
        assert adapter.t("greeting") == "Hello"

    def test_translation_with_params(self) -> None:
        """t() substitutes parameters via str.format."""
        adapter = InMemoryI18nAdapter(
            translations={"en": {"greeting": "Hello {name}"}},
            default_locale="en",
        )
        assert adapter.t("greeting", name="Gonzalo") == "Hello Gonzalo"

    def test_missing_key_returns_fallback(self) -> None:
        """t() returns [missing: key] instead of crashing on unknown key."""
        adapter = InMemoryI18nAdapter(
            translations={"en": {"greeting": "Hello"}},
            default_locale="en",
        )
        assert adapter.t("nonexistent") == "[missing: nonexistent]"

    def test_set_locale_switches_language(self) -> None:
        """set_locale() switches active language for translations."""
        adapter = InMemoryI18nAdapter(
            translations={
                "en": {"greeting": "Hello"},
                "es": {"greeting": "Hola"},
            },
            default_locale="en",
        )
        assert adapter.t("greeting") == "Hello"
        adapter.set_locale("es")
        assert adapter.t("greeting") == "Hola"

    def test_nested_key_traversal(self) -> None:
        """t() resolves dot-notation keys to traverse nested dict."""
        adapter = InMemoryI18nAdapter(
            translations={
                "en": {
                    "errors": {
                        "not_found": "Not found",
                        "server_error": "Internal error",
                    }
                }
            },
            default_locale="en",
        )
        assert adapter.t("errors.not_found") == "Not found"
        assert adapter.t("errors.server_error") == "Internal error"

    def test_load_translations_merges_new_keys(self) -> None:
        """load_translations() merges new translations into existing locale."""
        adapter = InMemoryI18nAdapter(
            translations={"en": {"greeting": "Hello"}},
            default_locale="en",
        )
        adapter.load_translations({"farewell": "Goodbye"}, "en")
        # After loading, new keys should be available
        assert adapter.t("farewell") == "Goodbye"

    def test_get_available_locales(self) -> None:
        """get_available_locales() returns all loaded locales."""
        adapter = InMemoryI18nAdapter(
            translations={
                "en": {"greeting": "Hello"},
                "es": {"greeting": "Hola"},
            },
            default_locale="en",
        )
        locales = adapter.get_available_locales()
        assert sorted(locales) == ["en", "es"]

    def test_default_locale_en_when_not_specified(self) -> None:
        """Default locale is 'en' when not explicitly set."""
        adapter = InMemoryI18nAdapter(
            translations={"en": {"greeting": "Hello"}},
        )
        assert adapter.t("greeting") == "Hello"

    def test_fallback_locale_used_when_key_missing_in_active(self) -> None:
        """Fallback to fallback_locale when key is missing in active locale."""
        adapter = InMemoryI18nAdapter(
            translations={
                "es": {"greeting": "Hola"},  # es doesn't have farewell
                "en": {"greeting": "Hello", "farewell": "Goodbye"},
            },
            default_locale="es",
            fallback_locale="en",
        )
        adapter.set_locale("es")
        # Key exists in es
        assert adapter.t("greeting") == "Hola"
        # Key missing in es, falls back to en
        assert adapter.t("farewell") == "Goodbye"

    def test_get_json_schema_returns_dict(self) -> None:
        """get_json_schema() returns a non-empty dict."""
        adapter = InMemoryI18nAdapter(
            translations={"en": {"greeting": "Hello"}},
        )
        schema = adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    def test_load_translations_from_dict(self) -> None:
        """load_translations() with a dict merges into existing translations."""
        adapter = InMemoryI18nAdapter(
            translations={"en": {"greeting": "Hello"}},
            default_locale="en",
        )
        adapter.load_translations({"farewell": "Goodbye"}, "en")
        assert adapter.t("farewell") == "Goodbye"
        # Original key still present
        assert adapter.t("greeting") == "Hello"
