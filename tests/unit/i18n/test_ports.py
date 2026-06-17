"""Unit tests for I18nManager Protocol and I18nConfig Pydantic model.

Tests cover:
- I18nManager Protocol contract (all required methods present)
- I18nConfig Pydantic model validation and defaults
- I18nManager Protocol is runtime-checkable

Author: CENF AI Team
Version: 0.1.0
"""

import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.i18n.models import I18nConfig
from core_infrastructure.i18n.ports import I18nManager


class TestI18nManagerProtocol:
    """Verify I18nManager Protocol defines all required methods."""

    def test_protocol_has_set_locale(self) -> None:
        """Protocol requires set_locale(locale: str) -> None."""
        assert hasattr(I18nManager, "set_locale")

    def test_protocol_has_t(self) -> None:
        """Protocol requires t(key, **params) -> str."""
        assert hasattr(I18nManager, "t")

    def test_protocol_has_get_available_locales(self) -> None:
        """Protocol requires get_available_locales() -> list[str]."""
        assert hasattr(I18nManager, "get_available_locales")

    def test_protocol_has_load_translations(self) -> None:
        """Protocol requires load_translations(path, locale) -> None."""
        assert hasattr(I18nManager, "load_translations")

    def test_protocol_has_get_json_schema(self) -> None:
        """Protocol requires get_json_schema() -> dict[str, Any]."""
        assert hasattr(I18nManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all I18nManager methods satisfies the protocol."""

        from typing import Any

        class ValidI18n:
            def set_locale(self, locale: str) -> None: ...
            def t(self, key: str, **params: Any) -> str: ...
            def get_available_locales(self) -> list[str]: ...
            def load_translations(self, path: str, locale: str) -> None: ...
            def get_json_schema(self) -> dict[str, Any]: ...

        assert isinstance(ValidI18n(), I18nManager)

    def test_class_missing_t_fails_protocol(self) -> None:
        """A class without t() does NOT satisfy I18nManager."""

        class Incomplete:
            def set_locale(self, locale: str) -> None: ...
            def get_available_locales(self) -> list[str]: ...

        assert not isinstance(Incomplete(), I18nManager)


class TestI18nConfig:
    """Verify I18nConfig Pydantic model validation and defaults."""

    def test_default_values(self) -> None:
        """I18nConfig creates with sensible defaults."""
        config = I18nConfig()
        assert config.default_locale == "en"
        assert config.translations_dir == "translations"
        assert config.fallback_locale == "en"

    def test_custom_values_accepted(self) -> None:
        """I18nConfig accepts valid custom values."""
        config = I18nConfig(
            default_locale="es",
            translations_dir="i18n",
            fallback_locale="en",
        )
        assert config.default_locale == "es"
        assert config.translations_dir == "i18n"
        assert config.fallback_locale == "en"

    def test_empty_default_locale_fails(self) -> None:
        """default_locale must be non-empty."""
        with pytest.raises(PydanticValidationError):
            I18nConfig(default_locale="")

    def test_empty_translations_dir_fails(self) -> None:
        """translations_dir must be non-empty."""
        with pytest.raises(PydanticValidationError):
            I18nConfig(translations_dir="")

    def test_model_json_schema_is_valid(self) -> None:
        """I18nConfig.model_json_schema() returns valid JSON Schema."""
        schema = I18nConfig.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        json_str = json.dumps(schema)
        assert len(json_str) > 0
        assert json.loads(json_str) == schema
