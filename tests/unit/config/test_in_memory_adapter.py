"""Unit tests for InMemoryConfigAdapter — dict-backed ConfigManager test double.

Tests cover:
- Protocol compliance (satisfies ConfigManager)
- All get_* methods work with in-memory data
- Default value fallback
- get_section returns dict copies
- get_json_schema returns valid schema
- set_value for dynamic test data injection

Author: CENF AI Team
Version: 0.1.0
"""

import json

import pytest

from core_infrastructure.common.errors import ValidationError
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter
from core_infrastructure.config.ports import ConfigManager


@pytest.fixture
def in_memory_config() -> InMemoryConfigAdapter:
    """Create an InMemoryConfigAdapter with preset test data."""
    return InMemoryConfigAdapter(
        initial_data={
            "env": "dev",
            "app_name": "test-app",
            "version": "1.0.0",
            "log_level": "DEBUG",
            "database": {
                "host": "localhost",
                "port": 5432,
            },
            "features": {
                "enable_cache": True,
                "max_retries": 3,
            },
            "nested": {
                "json_value": '{"key": "nested-value"}',
            },
        }
    )


class TestInMemoryConfigAdapterProtocol:
    """Verify InMemoryConfigAdapter satisfies ConfigManager Protocol."""

    def test_satisfies_config_manager_protocol(self) -> None:
        """InMemoryConfigAdapter passes isinstance check against ConfigManager."""
        adapter = InMemoryConfigAdapter()
        assert isinstance(adapter, ConfigManager)

    def test_default_constructor_creates_valid_adapter(self) -> None:
        """Default constructor creates a working adapter with CoreSettings defaults."""
        adapter = InMemoryConfigAdapter()
        assert adapter.get_env() == "dev"
        assert adapter.get_string("app_name") == "cenf-core"


class TestInMemoryConfigAdapterGetters:
    """Verify all get_* methods with initial_data."""

    def test_get_env(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_env() returns the configured env value."""
        assert in_memory_config.get_env() == "dev"

    def test_get_string(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_string() retrieves string values."""
        assert in_memory_config.get_string("app_name") == "test-app"
        assert in_memory_config.get_string("log_level") == "DEBUG"

    def test_get_number(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_number() retrieves numeric values."""
        assert in_memory_config.get_number("database.port") == 5432
        assert in_memory_config.get_number("features.max_retries") == 3

    def test_get_boolean(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_boolean() retrieves boolean values."""
        assert in_memory_config.get_boolean("features.enable_cache") is True

    def test_get_json(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_json() deserializes JSON string values."""
        result = in_memory_config.get_json("nested.json_value")
        assert result == {"key": "nested-value"}

    def test_get_section(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_section() returns a dict of all keys under a namespace."""
        section = in_memory_config.get_section("database")
        assert section == {"host": "localhost", "port": 5432}

    def test_get_section_nonexistent_returns_empty_dict(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_section() for a nonexistent namespace returns {}."""
        assert in_memory_config.get_section("nonexistent") == {}

    def test_get_json_schema(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_json_schema() returns a valid JSON Schema dict."""
        schema = in_memory_config.get_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert json.dumps(schema)  # Must be serializable


class TestInMemoryConfigAdapterDefaults:
    """Verify default_value fallback behavior."""

    def test_get_string_with_default(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_string returns default_value when key is missing."""
        assert in_memory_config.get_string("nonexistent", default_value="fallback") == "fallback"

    def test_get_number_with_default(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_number returns default_value when key is missing."""
        assert in_memory_config.get_number("nonexistent", default_value=99.0) == 99.0

    def test_get_boolean_with_default(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_boolean returns default_value when key is missing."""
        assert in_memory_config.get_boolean("nonexistent", default_value=True) is True

    def test_get_json_with_default(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_json returns default_value when key is missing."""
        default_obj = {"default": True}
        assert in_memory_config.get_json("nonexistent", default_value=default_obj) == default_obj


class TestInMemoryConfigAdapterErrors:
    """Verify error handling for missing keys without defaults."""

    def test_missing_string_key_raises_validation_error(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_string without default raises ValidationError on missing key."""
        with pytest.raises(ValidationError):
            in_memory_config.get_string("completely.missing")

    def test_missing_number_key_raises_validation_error(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_number without default raises ValidationError on missing key."""
        with pytest.raises(ValidationError):
            in_memory_config.get_number("completely.missing")

    def test_missing_boolean_key_raises_validation_error(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """get_boolean without default raises ValidationError on missing key."""
        with pytest.raises(ValidationError):
            in_memory_config.get_boolean("completely.missing")


class TestInMemoryConfigAdapterMutable:
    """Verify adapter behavior with dynamic data injection via set_value."""

    def test_set_value_updates_get_string(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """set_value() allows injecting new values for testing."""
        in_memory_config.set_value("app_name", "updated-app")
        assert in_memory_config.get_string("app_name") == "updated-app"

    def test_set_value_nested_key(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """set_value() supports nested dot-notation keys."""
        in_memory_config.set_value("database.host", "prod-db")
        assert in_memory_config.get_string("database.host") == "prod-db"

    def test_set_value_new_section(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """set_value() can create new nested sections dynamically."""
        in_memory_config.set_value("new_section.new_key", "new_value")
        assert in_memory_config.get_string("new_section.new_key") == "new_value"

    def test_reload_is_noop(self, in_memory_config: InMemoryConfigAdapter) -> None:
        """reload() is a noop for in-memory adapter (does not raise)."""
        import asyncio
        asyncio.run(in_memory_config.reload())
        # State should be unchanged
        assert in_memory_config.get_string("app_name") == "test-app"
