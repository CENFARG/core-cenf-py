"""Unit tests for LoggerManager Protocol and LoggerSettings Pydantic model.

Tests cover:
- LoggerManager Protocol contract (all required methods present)
- LoggerManager Protocol is runtime-checkable
- LoggerSettings Pydantic model validation and defaults
- LoggerSettings JSON Schema generation

Author: CENF AI Team
Version: 0.1.0
"""

import json

import pytest
from pydantic import ValidationError as PydanticValidationError


class TestLoggerManagerProtocol:
    """Verify LoggerManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """LoggerManager Protocol is decorated with @runtime_checkable."""
        from core_infrastructure.logger.ports import LoggerManager
        assert hasattr(LoggerManager, "_is_runtime_protocol") or hasattr(
            LoggerManager, "__protocol_attrs__"
        )

    def test_has_debug_method(self) -> None:
        """Protocol requires debug(message, **kwargs)."""
        from core_infrastructure.logger.ports import LoggerManager
        assert hasattr(LoggerManager, "debug")

    def test_has_info_method(self) -> None:
        """Protocol requires info(message, **kwargs)."""
        from core_infrastructure.logger.ports import LoggerManager
        assert hasattr(LoggerManager, "info")

    def test_has_warn_method(self) -> None:
        """Protocol requires warn(message, **kwargs)."""
        from core_infrastructure.logger.ports import LoggerManager
        assert hasattr(LoggerManager, "warn")

    def test_has_error_method(self) -> None:
        """Protocol requires error(message, exc=None, **kwargs)."""
        from core_infrastructure.logger.ports import LoggerManager
        assert hasattr(LoggerManager, "error")

    def test_has_bind_method(self) -> None:
        """Protocol requires bind(**kwargs) -> LoggerManager."""
        from core_infrastructure.logger.ports import LoggerManager
        assert hasattr(LoggerManager, "bind")

    def test_has_mask_method(self) -> None:
        """Protocol requires mask(value, visible_chars=4) -> str."""
        from core_infrastructure.logger.ports import LoggerManager
        assert hasattr(LoggerManager, "mask")

    def test_has_get_json_schema_method(self) -> None:
        """Protocol requires get_json_schema() -> dict."""
        from core_infrastructure.logger.ports import LoggerManager
        assert hasattr(LoggerManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all LoggerManager methods satisfies the protocol."""
        from core_infrastructure.logger.ports import LoggerManager

        class ValidLogger:
            def debug(self, message: str, **kwargs) -> None: ...
            def info(self, message: str, **kwargs) -> None: ...
            def warn(self, message: str, **kwargs) -> None: ...
            def error(self, message: str, exc=None, **kwargs) -> None: ...
            def bind(self, **kwargs): ...
            def mask(self, value: str, visible_chars: int = 4) -> str: ...
            def get_json_schema(self) -> dict: ...

        assert isinstance(ValidLogger(), LoggerManager)

    def test_class_missing_bind_fails_protocol(self) -> None:
        """A class without bind() does NOT satisfy LoggerManager."""
        from core_infrastructure.logger.ports import LoggerManager

        class IncompleteLogger:
            def debug(self, message: str, **kwargs) -> None: ...
            def info(self, message: str, **kwargs) -> None: ...

        assert not isinstance(IncompleteLogger(), LoggerManager)


class TestLoggerSettings:
    """Verify LoggerSettings Pydantic model validation and defaults."""

    def test_default_values(self) -> None:
        """LoggerSettings creates with sensible defaults."""
        from core_infrastructure.logger.models import LoggerSettings
        settings = LoggerSettings()
        assert settings.profile == "dev"
        assert settings.log_level == "INFO"
        assert settings.output_path is None
        assert settings.include_timestamp is True
        assert settings.max_stack_depth == 10

    def test_custom_values_accepted(self) -> None:
        """LoggerSettings accepts valid custom values."""
        from core_infrastructure.logger.models import LoggerSettings
        settings = LoggerSettings(
            profile="prod",
            log_level="ERROR",
            output_path="/var/log/app.log",
            include_timestamp=False,
            max_stack_depth=20,
        )
        assert settings.profile == "prod"
        assert settings.log_level == "ERROR"
        assert settings.output_path == "/var/log/app.log"
        assert settings.include_timestamp is False
        assert settings.max_stack_depth == 20

    def test_invalid_profile_fails_validation(self) -> None:
        """profile must be dev/test/prod."""
        from core_infrastructure.logger.models import LoggerSettings
        with pytest.raises(PydanticValidationError):
            LoggerSettings(profile="invalid")

    def test_valid_profile_dev(self) -> None:
        """'dev' is a valid profile."""
        from core_infrastructure.logger.models import LoggerSettings
        settings = LoggerSettings(profile="dev")
        assert settings.profile == "dev"

    def test_valid_profile_test(self) -> None:
        """'test' is a valid profile — silent/NullHandler output."""
        from core_infrastructure.logger.models import LoggerSettings
        settings = LoggerSettings(profile="test")
        assert settings.profile == "test"

    def test_valid_profile_prod(self) -> None:
        """'prod' is a valid profile — JSON output."""
        from core_infrastructure.logger.models import LoggerSettings
        settings = LoggerSettings(profile="prod")
        assert settings.profile == "prod"

    def test_invalid_log_level_fails(self) -> None:
        """log_level must be DEBUG/INFO/WARNING/ERROR."""
        from core_infrastructure.logger.models import LoggerSettings
        with pytest.raises(PydanticValidationError):
            LoggerSettings(log_level="TRACE")  # type: ignore[arg-type]

    def test_valid_log_levels_accepted(self) -> None:
        """All four valid log levels are accepted."""
        from core_infrastructure.logger.models import LoggerSettings
        for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
            settings = LoggerSettings(log_level=level)
            assert settings.log_level == level

    def test_max_stack_depth_out_of_range_fails(self) -> None:
        """max_stack_depth must be between 1 and 50."""
        from core_infrastructure.logger.models import LoggerSettings
        with pytest.raises(PydanticValidationError):
            LoggerSettings(max_stack_depth=0)
        with pytest.raises(PydanticValidationError):
            LoggerSettings(max_stack_depth=51)

    def test_model_json_schema_is_valid(self) -> None:
        """LoggerSettings.model_json_schema() returns valid JSON Schema."""
        from core_infrastructure.logger.models import LoggerSettings
        schema = LoggerSettings.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        json_str = json.dumps(schema)
        assert len(json_str) > 0
        assert json.loads(json_str) == schema
