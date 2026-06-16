"""Unit tests for ConfigManager Protocol and CoreSettings Pydantic model.

Tests cover:
- ConfigManager Protocol contract (all required methods present)
- CoreSettings Pydantic model validation and defaults
- ConfigManager Protocol is runtime-checkable

Author: CENF AI Team
Version: 0.1.0
"""

import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.config.models import CoreSettings
from core_infrastructure.config.ports import ConfigManager


class TestConfigManagerProtocol:
    """Verify ConfigManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """ConfigManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(ConfigManager, "_is_runtime_protocol") or hasattr(
            ConfigManager, "__protocol_attrs__"
        )

    def test_has_get_env_method(self) -> None:
        """Protocol requires get_env() -> Env."""
        assert hasattr(ConfigManager, "get_env")

    def test_has_get_string_method(self) -> None:
        """Protocol requires get_string(key, default_value)."""
        assert hasattr(ConfigManager, "get_string")

    def test_has_get_number_method(self) -> None:
        """Protocol requires get_number(key, default_value)."""
        assert hasattr(ConfigManager, "get_number")

    def test_has_get_boolean_method(self) -> None:
        """Protocol requires get_boolean(key, default_value)."""
        assert hasattr(ConfigManager, "get_boolean")

    def test_has_get_json_method(self) -> None:
        """Protocol requires get_json(key, default_value)."""
        assert hasattr(ConfigManager, "get_json")

    def test_has_get_section_method(self) -> None:
        """Protocol requires get_section(namespace)."""
        assert hasattr(ConfigManager, "get_section")

    def test_has_reload_method(self) -> None:
        """Protocol requires async reload() method."""
        assert hasattr(ConfigManager, "reload")

    def test_has_get_json_schema_method(self) -> None:
        """Protocol requires get_json_schema() -> dict."""
        assert hasattr(ConfigManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all ConfigManager methods satisfies the protocol."""

        class ValidConfig:
            def get_env(self) -> str: ...
            def get_string(self, key: str, default_value: str | None = None) -> str: ...
            def get_number(self, key: str, default_value: float | None = None) -> float: ...
            def get_boolean(self, key: str, default_value: bool | None = None) -> bool: ...
            def get_json(self, key: str, default_value=None): ...
            def get_section(self, namespace: str): ...
            async def reload(self) -> None: ...
            def get_json_schema(self) -> dict: ...

        assert isinstance(ValidConfig(), ConfigManager)

    def test_class_missing_get_string_fails_protocol(self) -> None:
        """A class without get_string() does NOT satisfy ConfigManager."""

        class Incomplete:
            def get_env(self) -> str: ...
            async def reload(self) -> None: ...

        assert not isinstance(Incomplete(), ConfigManager)


class TestCoreSettings:
    """Verify CoreSettings Pydantic model validation and defaults."""

    def test_default_values(self) -> None:
        """CoreSettings creates with sensible defaults."""
        settings = CoreSettings()
        assert settings.env == "dev"
        assert settings.app_name == "cenf-core"
        assert settings.version == "0.1.0"
        assert settings.log_level == "INFO"

    def test_custom_values_accepted(self) -> None:
        """CoreSettings accepts valid custom values."""
        settings = CoreSettings(
            env="prod",
            app_name="my-app",
            version="2.0.0",
            log_level="ERROR",
        )
        assert settings.env == "prod"
        assert settings.app_name == "my-app"
        assert settings.version == "2.0.0"
        assert settings.log_level == "ERROR"

    def test_invalid_env_fails_validation(self) -> None:
        """env must be one of local/dev/staging/prod."""
        with pytest.raises(PydanticValidationError):
            CoreSettings(env="invalid")

    def test_valid_env_local(self) -> None:
        """'local' is a valid env."""
        settings = CoreSettings(env="local")
        assert settings.env == "local"

    def test_valid_env_dev(self) -> None:
        """'dev' is a valid env."""
        settings = CoreSettings(env="dev")
        assert settings.env == "dev"

    def test_valid_env_staging(self) -> None:
        """'staging' is a valid env."""
        settings = CoreSettings(env="staging")
        assert settings.env == "staging"

    def test_valid_env_prod(self) -> None:
        """'prod' is a valid env."""
        settings = CoreSettings(env="prod")
        assert settings.env == "prod"

    def test_empty_app_name_fails(self) -> None:
        """app_name must be at least 1 character."""
        with pytest.raises(PydanticValidationError):
            CoreSettings(app_name="")

    def test_app_name_exceeds_128_chars_fails(self) -> None:
        """app_name max 128 characters."""
        with pytest.raises(PydanticValidationError):
            CoreSettings(app_name="x" * 129)

    def test_invalid_version_pattern_fails(self) -> None:
        """version must match semver pattern."""
        with pytest.raises(PydanticValidationError):
            CoreSettings(version="v1")

    def test_invalid_log_level_fails(self) -> None:
        """log_level must be DEBUG/INFO/WARNING/ERROR."""
        with pytest.raises(PydanticValidationError):
            CoreSettings(log_level="TRACE")  # type: ignore[arg-type]

    def test_valid_log_levels_accepted(self) -> None:
        """All four valid log levels are accepted."""
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            settings = CoreSettings(log_level=level)
            assert settings.log_level == level

    def test_model_json_schema_is_valid(self) -> None:
        """CoreSettings.model_json_schema() returns valid JSON Schema."""
        schema = CoreSettings.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        # Verify it can be serialized to JSON
        json_str = json.dumps(schema)
        assert len(json_str) > 0
        assert json.loads(json_str) == schema
