"""Unit tests for YamlI18nAdapter — YAML-backed I18nManager implementation.

Tests cover:
- Simple translation without params
- Translation with params (str.format)
- Missing key fallback
- set_locale switching
- Nested key traversal (dot notation)
- load_translations merging
- Locale read from ConfigManager
- get_available_locales

Author: CENF AI Team
Version: 0.1.0
"""

import tempfile
from pathlib import Path

from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.i18n.adapters.yaml_i18n_adapter import YamlI18nAdapter
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter


class TestYamlAdapter:
    """Verify YamlI18nAdapter satisfies the I18nManager contract."""

    @staticmethod
    def _make_config(locale: str = "en") -> InMemoryConfigAdapter:
        """Create an InMemoryConfigAdapter with i18n.locale set."""
        return InMemoryConfigAdapter({"i18n": {"locale": locale}})

    @staticmethod
    def _make_logger() -> InMemoryLoggerAdapter:
        """Create an InMemoryLoggerAdapter."""
        return InMemoryLoggerAdapter()

    def test_simple_translation(self) -> None:
        """t() returns translated string for active locale without params."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        adapter.load_translations({"greeting": "Hello"}, "en")
        assert adapter.t("greeting") == "Hello"

    def test_translation_with_params(self) -> None:
        """t() substitutes parameters via str.format."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        adapter.load_translations({"greeting": "Hello {name}"}, "en")
        assert adapter.t("greeting", name="Gonzalo") == "Hello Gonzalo"

    def test_missing_key_returns_fallback(self) -> None:
        """t() returns [missing: key] instead of crashing on unknown key."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        assert adapter.t("nonexistent") == "[missing: nonexistent]"

    def test_set_locale_switches_language(self) -> None:
        """set_locale() switches active language for translations."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        adapter.load_translations({"greeting": "Hello"}, "en")
        adapter.load_translations({"greeting": "Hola"}, "es")
        assert adapter.t("greeting") == "Hello"
        adapter.set_locale("es")
        assert adapter.t("greeting") == "Hola"

    def test_nested_key_traversal(self) -> None:
        """t() resolves dot-notation keys to traverse nested dict."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        adapter.load_translations(
            {"errors": {"not_found": "Not found", "server_error": "Internal error"}},
            "en",
        )
        assert adapter.t("errors.not_found") == "Not found"
        assert adapter.t("errors.server_error") == "Internal error"

    def test_load_translations_merges_new_keys(self) -> None:
        """load_translations() merges new translations into existing locale."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        adapter.load_translations({"greeting": "Hello"}, "en")
        adapter.load_translations({"farewell": "Goodbye"}, "en")
        assert adapter.t("greeting") == "Hello"
        assert adapter.t("farewell") == "Goodbye"

    def test_locale_read_from_config(self) -> None:
        """Active locale is read from config.get_string('i18n.locale')."""
        config = InMemoryConfigAdapter({"i18n": {"locale": "es"}})
        logger = self._make_logger()
        adapter = YamlI18nAdapter(config_manager=config, logger_manager=logger)
        adapter.load_translations({"greeting": "Hola"}, "es")
        adapter.load_translations({"greeting": "Hello"}, "en")
        # Config says es, so default locale should be es
        assert adapter.t("greeting") == "Hola"

    def test_get_available_locales(self) -> None:
        """get_available_locales() returns all loaded locales."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        adapter.load_translations({"greeting": "Hello"}, "en")
        adapter.load_translations({"greeting": "Hola"}, "es")
        locales = adapter.get_available_locales()
        assert sorted(locales) == ["en", "es"]

    def test_get_json_schema_returns_dict(self) -> None:
        """get_json_schema() returns a non-empty dict."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        schema = adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    def test_fallback_locale_used_when_key_missing_in_active(self) -> None:
        """Fallback to fallback_locale when key is missing in active locale."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("es"),
            logger_manager=self._make_logger(),
            fallback_locale="en",
        )
        adapter.load_translations({"greeting": "Hola"}, "es")
        adapter.load_translations({"greeting": "Hello", "farewell": "Goodbye"}, "en")
        # Key exists in es
        assert adapter.t("greeting") == "Hola"
        # Key missing in es, falls back to en
        assert adapter.t("farewell") == "Goodbye"

    def test_load_yaml_file(self) -> None:
        """load_translations() reads a YAML file and loads its contents."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        # Create a temp YAML file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write("greeting: Hello from file\nfarewell: Bye from file\n")
            f.flush()
            temp_path = f.name

        try:
            adapter.load_translations(temp_path, "en")
            assert adapter.t("greeting") == "Hello from file"
            assert adapter.t("farewell") == "Bye from file"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_missing_key_with_params_returns_fallback(self) -> None:
        """Missing key with params still returns [missing: key] prefix."""
        adapter = YamlI18nAdapter(
            config_manager=self._make_config("en"),
            logger_manager=self._make_logger(),
        )
        result = adapter.t("missing.welcome", user="Bob")
        assert result == "[missing: missing.welcome]"
