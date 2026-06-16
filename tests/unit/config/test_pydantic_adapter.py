"""Unit tests for PydanticSettingsAdapter — production ConfigManager implementation.

Tests cover:
- YAML file loading and env var override (12-factor precedence)
- All get_* methods return correct types
- get_json_schema() returns valid JSON Schema
- Hot-reload support with asyncio.Lock protection
- Error handling: missing keys, invalid YAML, type coercion failures

Author: CENF AI Team
Version: 0.1.0
"""

import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from core_infrastructure.common.errors import PermanentError, ValidationError
from core_infrastructure.config.adapters.pydantic_config_adapter import PydanticConfigAdapter
from core_infrastructure.config.ports import ConfigManager


@pytest.fixture
def temp_yaml_config() -> str:
    """Write a minimal valid YAML config to a temp file and return its path."""
    config_data = {
        "env": "dev",
        "app_name": "test-app",
        "version": "0.1.0",
        "log_level": "INFO",
        "database": {
            "host": "localhost",
            "port": 5432,
        },
        "features": {
            "enable_cache": True,
            "max_retries": 3,
        },
        "nested": {
            "json_value": '{"key": "value"}',
        },
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        yaml.dump(config_data, f)
        return f.name


class TestPydanticConfigAdapterBasic:
    """Verify adapter satisfies ConfigManager Protocol and loads YAML."""

    def test_satisfies_config_manager_protocol(self) -> None:
        """PydanticConfigAdapter instances pass isinstance check against ConfigManager."""
        adapter = PydanticConfigAdapter()
        assert isinstance(adapter, ConfigManager)

    def test_get_env_from_yaml(self, temp_yaml_config: str) -> None:
        """get_env() returns the env value from the YAML file."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            assert adapter.get_env() == "dev"
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_get_string_from_yaml(self, temp_yaml_config: str) -> None:
        """get_string() retrieves string values from YAML."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            assert adapter.get_string("app_name") == "test-app"
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_get_number_from_yaml(self, temp_yaml_config: str) -> None:
        """get_number() retrieves numeric values from YAML."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            assert adapter.get_number("features.max_retries") == 3
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_get_boolean_from_yaml(self, temp_yaml_config: str) -> None:
        """get_boolean() retrieves boolean values from YAML."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            assert adapter.get_boolean("features.enable_cache") is True
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_get_json_from_yaml(self, temp_yaml_config: str) -> None:
        """get_json() deserializes JSON strings from YAML."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            result = adapter.get_json("nested.json_value")
            assert result == {"key": "value"}
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_get_section_from_yaml(self, temp_yaml_config: str) -> None:
        """get_section() returns a dict of all keys under a namespace."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            section = adapter.get_section("database")
            assert section == {"host": "localhost", "port": 5432}
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_get_json_schema_returns_valid_schema(self, temp_yaml_config: str) -> None:
        """get_json_schema() returns a valid JSON Schema dict."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            schema = adapter.get_json_schema()
            assert isinstance(schema, dict)
            assert "properties" in schema
            assert "env" in schema["properties"]
            # Must be serializable to JSON
            assert json.dumps(schema)
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)


class TestPydanticConfigAdapterDefaults:
    """Verify default values and default_value fallback parameters."""

    def test_get_string_with_default_fallback(self, temp_yaml_config: str) -> None:
        """get_string returns default_value when key is missing."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            assert adapter.get_string("nonexistent", default_value="fallback") == "fallback"
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_get_number_with_default_fallback(self, temp_yaml_config: str) -> None:
        """get_number returns default_value when key is missing."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            assert adapter.get_number("nonexistent", default_value=42.0) == 42.0
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_get_boolean_with_default_fallback(self, temp_yaml_config: str) -> None:
        """get_boolean returns default_value when key is missing."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            assert adapter.get_boolean("nonexistent", default_value=True) is True
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_default_values_when_no_yaml(self) -> None:
        """Adapter uses CoreSettings defaults when no YAML is provided."""
        adapter = PydanticConfigAdapter()
        assert adapter.get_env() == "dev"
        assert adapter.get_string("app_name") == "cenf-core"


class TestPydanticConfigAdapterErrors:
    """Verify error handling: missing keys, invalid YAML, type coercion."""

    def test_missing_key_without_default_raises_validation_error(self, temp_yaml_config: str) -> None:
        """get_string without default_value raises ValidationError on missing key."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            with pytest.raises(ValidationError):
                adapter.get_string("completely.missing.key")
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    def test_invalid_yaml_raises_permanent_error(self) -> None:
        """Loading malformed YAML raises PermanentError."""
        bad_yaml_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False, encoding="utf-8"
            ) as f:
                f.write("invalid: yaml: ::: syntax error\n  broken")
                bad_yaml_path = f.name

            with pytest.raises(PermanentError):
                PydanticConfigAdapter(config_path=bad_yaml_path)
        finally:
            if bad_yaml_path:
                Path(bad_yaml_path).unlink(missing_ok=True)

    def test_missing_file_raises_permanent_error(self) -> None:
        """Loading a nonexistent file raises PermanentError."""
        with pytest.raises(PermanentError):
            PydanticConfigAdapter(config_path="/nonexistent/path/config.yaml")


class TestPydanticConfigAdapterEnvOverride:
    """Verify 12-factor env var precedence over YAML."""

    def test_env_var_overrides_yaml_value(self, temp_yaml_config: str) -> None:
        """CENF_ prefixed env vars override YAML values."""
        try:
            os.environ["CENF_ENV"] = "prod"
            adapter = PydanticConfigAdapter(
                config_path=temp_yaml_config,
                env_prefix="CENF_",
            )
            assert adapter.get_env() == "prod"
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)
            os.environ.pop("CENF_ENV", None)

    def test_env_var_overrides_nested_yaml_value(self, temp_yaml_config: str) -> None:
        """CENF_ prefixed env vars override nested YAML keys via dot notation."""
        try:
            os.environ["CENF_DATABASE__HOST"] = "prod-db.example.com"
            adapter = PydanticConfigAdapter(
                config_path=temp_yaml_config,
                env_prefix="CENF_",
            )
            # When env var uses __ as separator, it should override the nested key
            assert adapter.get_string("database.host") == "prod-db.example.com"
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)
            os.environ.pop("CENF_DATABASE__HOST", None)


class TestPydanticConfigAdapterReload:
    """Verify hot-reload and reload concurrency protection."""

    @pytest.mark.asyncio
    async def test_reload_picks_up_yaml_changes(self, temp_yaml_config: str) -> None:
        """After modifying the YAML file, reload() picks up the changes."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            assert adapter.get_string("app_name") == "test-app"

            # Modify the YAML file
            with open(temp_yaml_config, "w", encoding="utf-8") as f:
                yaml.dump({"app_name": "reloaded-app", "env": "dev", "version": "0.1.0", "log_level": "INFO"}, f)

            await adapter.reload()
            assert adapter.get_string("app_name") == "reloaded-app"
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_reload_is_idempotent(self, temp_yaml_config: str) -> None:
        """Calling reload() multiple times does not corrupt state."""
        try:
            adapter = PydanticConfigAdapter(config_path=temp_yaml_config)
            await adapter.reload()
            await adapter.reload()
            # State should still be consistent
            assert adapter.get_string("app_name") == "test-app"
        finally:
            Path(temp_yaml_config).unlink(missing_ok=True)
