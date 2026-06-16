"""Unit tests for StructlogAdapter — production LoggerManager using structlog.

Tests cover:
- StructlogAdapter satisfies LoggerManager Protocol
- Dev profile outputs colored console (captured via StringIO)
- Test profile produces no output (NullHandler/silent)
- Prod profile outputs JSON-formatted logs
- Contextvar injection: correlation_id, tenant_id, trace_id, span_id
- mask() works for sensitive data truncation
- bind() creates a bound logger with extra context
- get_json_schema() returns valid JSON Schema
- LoggerManager never raises (graceful degradation)

Author: CENF AI Team
Version: 0.1.0
"""

import io
import json as json_module
import sys

import pytest

from core_infrastructure.common.context import (
    set_correlation_id,
    set_span_id,
    set_tenant_id,
    set_trace_id,
)
from core_infrastructure.config.adapters.in_memory_config_adapter import (
    InMemoryConfigAdapter,
)


@pytest.fixture
def dev_config() -> InMemoryConfigAdapter:
    """Config with logger profile set to 'dev'."""
    return InMemoryConfigAdapter(
        initial_data={
            "logger": {
                "profile": "dev",
                "log_level": "DEBUG",
                "include_timestamp": True,
                "max_stack_depth": 10,
            }
        }
    )


@pytest.fixture
def test_config() -> InMemoryConfigAdapter:
    """Config with logger profile set to 'test'."""
    return InMemoryConfigAdapter(
        initial_data={
            "logger": {
                "profile": "test",
                "log_level": "DEBUG",
                "include_timestamp": True,
                "max_stack_depth": 10,
            }
        }
    )


@pytest.fixture
def prod_config() -> InMemoryConfigAdapter:
    """Config with logger profile set to 'prod'."""
    return InMemoryConfigAdapter(
        initial_data={
            "logger": {
                "profile": "prod",
                "log_level": "DEBUG",
                "include_timestamp": True,
                "max_stack_depth": 10,
            }
        }
    )


class TestStructlogAdapterProtocol:
    """Verify StructlogAdapter satisfies LoggerManager Protocol."""

    def test_satisfies_logger_manager_protocol(self, dev_config: InMemoryConfigAdapter) -> None:
        """StructlogAdapter passes isinstance check against LoggerManager."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter
        from core_infrastructure.logger.ports import LoggerManager

        adapter = StructlogAdapter(config=dev_config)
        assert isinstance(adapter, LoggerManager)


class TestStructlogAdapterDevProfile:
    """Verify dev profile produces colored console output."""

    def test_dev_profile_produces_output(self, dev_config: InMemoryConfigAdapter) -> None:
        """Dev profile logger writes to stdout (colored console)."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=dev_config)
        captured = io.StringIO()
        # Redirect stdout to capture console output
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            adapter.info("dev test message")
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert "dev test message" in output

    def test_dev_profile_includes_contextvars(self, dev_config: InMemoryConfigAdapter) -> None:
        """Dev output includes correlation_id and tenant_id from contextvars."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        set_correlation_id("corr-test-123")
        set_tenant_id("tenant-abc")

        adapter = StructlogAdapter(config=dev_config)
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            adapter.info("context test")
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert "corr-test-123" in output
        assert "tenant-abc" in output


class TestStructlogAdapterTestProfile:
    """Verify test profile is silent (NullHandler / no output)."""

    def test_test_profile_produces_no_output(self, test_config: InMemoryConfigAdapter) -> None:
        """Test profile logger does not write to stdout or stderr."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=test_config)
        captured_out = io.StringIO()
        captured_err = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured_out
        sys.stderr = captured_err
        try:
            adapter.info("should not appear")
            adapter.error("error should not appear")
            adapter.debug("debug should not appear")
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        assert captured_out.getvalue() == ""
        assert captured_err.getvalue() == ""

    def test_test_profile_never_raises(self, test_config: InMemoryConfigAdapter) -> None:
        """Test profile adapter never raises on any log method."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=test_config)
        # Should not raise even with arbitrary kwargs
        adapter.debug("debug")
        adapter.info("info", extra="value")
        adapter.warn("warn")
        adapter.error("error", exc=ValueError("test"))
        # None message should not raise
        adapter.info(None)  # type: ignore[arg-type]


class TestStructlogAdapterProdProfile:
    """Verify prod profile produces JSON output."""

    def test_prod_profile_produces_json(self, prod_config: InMemoryConfigAdapter) -> None:
        """Prod profile logger writes valid JSON to stdout."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=prod_config)
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            adapter.info("prod json message", action="login")
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue().strip()
        assert output, "Expected non-empty JSON output"
        record = json_module.loads(output)
        assert record["event"] == "prod json message"
        assert record.get("action") == "login"

    def test_prod_json_includes_contextvars(self, prod_config: InMemoryConfigAdapter) -> None:
        """Prod JSON output includes correlation_id, tenant_id, trace_id, span_id."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        set_correlation_id("prod-corr-456")
        set_tenant_id("prod-tenant")
        set_trace_id("trace-hex-123")
        set_span_id("span-hex-456")

        adapter = StructlogAdapter(config=prod_config)
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            adapter.info("context trace test")
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue().strip()
        record = json_module.loads(output)
        assert record.get("correlation_id") == "prod-corr-456"
        assert record.get("tenant_id") == "prod-tenant"
        assert record.get("trace_id") == "trace-hex-123"
        assert record.get("span_id") == "span-hex-456"

    def test_prod_error_with_exception_includes_exc_info(self, prod_config: InMemoryConfigAdapter) -> None:
        """Prod JSON error log includes exception type and message."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=prod_config)
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            try:
                raise RuntimeError("test explosion")
            except RuntimeError as exc:
                adapter.error("something broke", exc=exc)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue().strip()
        record = json_module.loads(output)
        assert record["event"] == "something broke"
        # structlog should include exception info
        assert "exception" in record or "exc_info" in record


class TestStructlogAdapterBind:
    """Verify bind() returns a bound logger with additional context."""

    def test_bind_adds_extra_context(self, prod_config: InMemoryConfigAdapter) -> None:
        """bind() creates a logger with extra keys prepended to every record."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=prod_config)
        bound = adapter.bind(component="auth-service", environment="staging")

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            bound.info("bound message")
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue().strip()
        record = json_module.loads(output)
        assert record.get("component") == "auth-service"
        assert record.get("environment") == "staging"


class TestStructlogAdapterMask:
    """Verify mask() truncates sensitive values."""

    def test_mask_default_four_chars(self, dev_config: InMemoryConfigAdapter) -> None:
        """mask() shows last 4 characters by default."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=dev_config)
        result = adapter.mask("secret-token-xyz123")
        assert result.endswith("123")
        assert result.startswith("*")
        assert "secret" not in result.lower()

    def test_mask_custom_visible_chars(self, dev_config: InMemoryConfigAdapter) -> None:
        """mask() respects custom visible_chars parameter."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=dev_config)
        result = adapter.mask("my-api-key", visible_chars=3)
        # "my-api-key" len=10, visible=3 → 7 * + "key" = "*******key" (10 chars)
        assert result == "*******key"

    def test_mask_short_value(self, dev_config: InMemoryConfigAdapter) -> None:
        """mask() handles values shorter than visible_chars."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=dev_config)
        result = adapter.mask("hi", visible_chars=5)
        assert result == "**"


class TestStructlogAdapterSchema:
    """Verify get_json_schema returns valid JSON Schema."""

    def test_get_json_schema_returns_valid_schema(self, dev_config: InMemoryConfigAdapter) -> None:
        """get_json_schema() returns a dict with properties key."""
        from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

        adapter = StructlogAdapter(config=dev_config)
        schema = adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert json_module.dumps(schema)
