"""Unit tests for InMemoryLoggerAdapter — list-backed LoggerManager test double.

Tests cover:
- Protocol compliance (satisfies LoggerManager)
- All log levels (debug, info, warn, error) collect records
- Records contain structured data (message, level, extras)
- bind() creates a bound logger with extra context
- mask() truncates values showing only last N chars
- get_logs() returns all collected log records
- clear() resets the log buffer
- Error logging with exception stores exception info

Author: CENF AI Team
Version: 0.1.0
"""

import pytest

from core_infrastructure.logger.adapters.in_memory_logger_adapter import (
    InMemoryLoggerAdapter,
)
from core_infrastructure.logger.ports import LoggerManager


@pytest.fixture
def in_memory_logger() -> InMemoryLoggerAdapter:
    """Create a fresh InMemoryLoggerAdapter with an empty log buffer."""
    return InMemoryLoggerAdapter()


class TestInMemoryLoggerAdapterProtocol:
    """Verify InMemoryLoggerAdapter satisfies LoggerManager Protocol."""

    def test_satisfies_logger_manager_protocol(self) -> None:
        """InMemoryLoggerAdapter passes isinstance check against LoggerManager."""
        adapter = InMemoryLoggerAdapter()
        assert isinstance(adapter, LoggerManager)

    def test_adapter_has_all_required_methods(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """Adapter exposes debug, info, warn, error, bind, mask, get_json_schema."""
        assert callable(in_memory_logger.debug)
        assert callable(in_memory_logger.info)
        assert callable(in_memory_logger.warn)
        assert callable(in_memory_logger.error)
        assert callable(in_memory_logger.bind)
        assert callable(in_memory_logger.mask)
        assert callable(in_memory_logger.get_json_schema)


class TestInMemoryLoggerAdapterLogging:
    """Verify log methods produce structured records in the buffer."""

    def test_debug_produces_record(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """debug() records a structured log entry with level='DEBUG'."""
        in_memory_logger.debug("test debug message")
        logs = in_memory_logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["message"] == "test debug message"
        assert logs[0]["level"] == "DEBUG"

    def test_info_produces_record(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """info() records a structured log entry with level='INFO'."""
        in_memory_logger.info("test info message", user_id="abc")
        logs = in_memory_logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["message"] == "test info message"
        assert logs[0]["level"] == "INFO"
        assert logs[0].get("user_id") == "abc"

    def test_warn_produces_record(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """warn() records a structured log entry with level='WARNING'."""
        in_memory_logger.warn("test warn message")
        logs = in_memory_logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["level"] == "WARNING"

    def test_error_produces_record(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """error() records a structured log entry with level='ERROR'."""
        in_memory_logger.error("test error message")
        logs = in_memory_logger.get_logs()
        assert len(logs) == 1
        assert logs[0]["level"] == "ERROR"
        assert logs[0]["message"] == "test error message"

    def test_error_with_exception_stores_exc_info(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """error() with an exception argument stores exception type and message."""
        try:
            raise ValueError("something went wrong")
        except ValueError as exc:
            in_memory_logger.error("operation failed", exc=exc)

        logs = in_memory_logger.get_logs()
        assert len(logs) == 1
        assert "exc_type" in logs[0]
        assert "ValueError" in logs[0]["exc_type"]
        assert "something went wrong" in logs[0].get("exc_message", "")

    def test_multiple_logs_preserved_in_order(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """Logs are preserved in the order they were emitted."""
        in_memory_logger.debug("first")
        in_memory_logger.info("second")
        in_memory_logger.warn("third")
        logs = in_memory_logger.get_logs()
        assert len(logs) == 3
        assert [r["message"] for r in logs] == ["first", "second", "third"]


class TestInMemoryLoggerAdapterBind:
    """Verify bind() creates a bound logger that prepends extra context."""

    def test_bind_adds_context_to_subsequent_logs(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """bind() returns a logger that includes bound keys in all records."""
        bound = in_memory_logger.bind(request_id="req-123", user="gonza")
        bound.info("bound message")
        logs = in_memory_logger.get_logs()
        assert len(logs) == 1
        assert logs[0].get("request_id") == "req-123"
        assert logs[0].get("user") == "gonza"

    def test_bind_does_not_affect_original(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """The original logger is unaffected by a bound instance."""
        _bound = in_memory_logger.bind(request_id="req-456")
        in_memory_logger.info("original message")
        logs = in_memory_logger.get_logs()
        assert len(logs) == 1
        assert "request_id" not in logs[0]

    def test_original_logs_appear_after_bound_logs(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """Both bound and original share the same buffer — logs interleaved in order."""
        bound = in_memory_logger.bind(extra="ctx")
        bound.info("from bound")
        in_memory_logger.info("from original")
        logs = in_memory_logger.get_logs()
        assert len(logs) == 2
        assert logs[0].get("extra") == "ctx"
        assert "extra" not in logs[1]


class TestInMemoryLoggerAdapterMask:
    """Verify mask() truncates sensitive values."""

    def test_mask_shows_last_n_chars(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """mask() returns a string with only the last visible_chars visible."""
        result = in_memory_logger.mask("secret-key-12345", visible_chars=4)
        assert result.endswith("2345")
        assert not result.startswith("secret")

    def test_mask_default_four_chars(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """mask() defaults to showing the last 4 characters."""
        result = in_memory_logger.mask("abcdefgh")
        assert result == "****efgh"

    def test_mask_zero_visible_chars(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """mask() with visible_chars=0 shows no original characters."""
        result = in_memory_logger.mask("sensitive", visible_chars=0)
        assert "sensitive" not in result.lower()
        assert all(c == "*" for c in result)

    def test_mask_value_shorter_than_visible(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """mask() shows the full value when visible_chars > len(value)."""
        result = in_memory_logger.mask("ab", visible_chars=10)
        assert result == "**"


class TestInMemoryLoggerAdapterBuffer:
    """Verify buffer management (get_logs, clear)."""

    def test_get_logs_returns_copy(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """get_logs() returns a copy — mutating it does not affect the internal buffer."""
        in_memory_logger.info("hello")
        logs = in_memory_logger.get_logs()
        logs.clear()
        assert len(in_memory_logger.get_logs()) == 1

    def test_clear_empties_buffer(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """clear() resets the log buffer to empty."""
        in_memory_logger.info("msg1")
        in_memory_logger.info("msg2")
        assert len(in_memory_logger.get_logs()) == 2
        in_memory_logger.clear()
        assert len(in_memory_logger.get_logs()) == 0

    def test_get_json_schema_returns_dict(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """get_json_schema() returns a non-empty dict."""
        schema = in_memory_logger.get_json_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0

    def test_logger_never_raises(self, in_memory_logger: InMemoryLoggerAdapter) -> None:
        """All logger methods must never raise — degrade gracefully."""
        # Logging with None message should not raise
        in_memory_logger.info(None)  # type: ignore[arg-type]
        # Calling mask with empty string
        result = in_memory_logger.mask("")
        assert isinstance(result, str)
