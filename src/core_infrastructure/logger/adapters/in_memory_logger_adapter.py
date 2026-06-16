"""InMemoryLoggerAdapter — list-backed LoggerManager test double.

Collects all log records in an in-memory list for test assertions.
Supports all LoggerManager Protocol methods: debug, info, warn, error,
bind, mask, and get_json_schema. The buffer can be inspected via
get_logs() and reset via clear().

Security: No real I/O — logs never leave process memory.
Observability: Deterministic — always returns the same result for the
    same input. Ideal for TDD assertion cycles.
@ai-directive: This adapter exists solely for testing. NEVER use it in
    production code paths.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from core_infrastructure.logger.models import LoggerSettings
from core_infrastructure.logger.ports import LoggerManager


class InMemoryLoggerAdapter:
    """List-backed LoggerManager for unit test assertions.

    All log method calls append a structured ``dict`` to an internal buffer.
    The buffer is shared across bound loggers created via ``bind()``.

    Args:
        initial_context: Optional dict of context keys added to every record.

    Usage::

        logger = InMemoryLoggerAdapter()
        logger.info("user logged in", user_id="123")
        logs = logger.get_logs()
        assert logs[0]["message"] == "user logged in"
        assert logs[0]["user_id"] == "123"
    """

    def __init__(
        self,
        initial_context: dict[str, Any] | None = None,
    ) -> None:
        self._logs: list[dict[str, Any]] = []
        self._context: dict[str, Any] = deepcopy(initial_context) if initial_context else {}

    # ------------------------------------------------------------------
    # Public API — LoggerManager Protocol
    # ------------------------------------------------------------------

    def debug(self, message: str, **kwargs: Any) -> None:
        """Record a DEBUG-level log entry.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs stored in the record.
        """
        self._record("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Record an INFO-level log entry.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs stored in the record.
        """
        self._record("INFO", message, **kwargs)

    def warn(self, message: str, **kwargs: Any) -> None:
        """Record a WARNING-level log entry.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs stored in the record.
        """
        self._record("WARNING", message, **kwargs)

    def error(self, message: str, exc: Exception | None = None, **kwargs: Any) -> None:
        """Record an ERROR-level log entry with optional exception info.

        Args:
            message: The log message text.
            exc: Optional exception to store in the record.
            **kwargs: Arbitrary key-value pairs stored in the record.
        """
        if exc is not None:
            kwargs["exc_type"] = type(exc).__name__
            kwargs["exc_message"] = str(exc)
        self._record("ERROR", message, **kwargs)

    def bind(self, **kwargs: Any) -> LoggerManager:
        """Create a bound logger that prepends extra context to every record.

        The returned logger shares the SAME underlying buffer as the
        original. Both bound and original records appear in the same
        list, interleaved in call order.

        Args:
            **kwargs: Context keys to prepend to all subsequent records.

        Returns:
            InMemoryLoggerAdapter: New instance sharing the same buffer
                but with additional bound context.
        """
        merged_context = {**self._context, **kwargs}
        bound = InMemoryLoggerAdapter()
        bound._logs = self._logs  # Share the buffer
        bound._context = merged_context
        return bound

    def mask(self, value: str, visible_chars: int = 4) -> str:
        """Redact a sensitive string, showing only the last N characters.

        Args:
            value: The sensitive string to mask.
            visible_chars: Number of trailing characters to leave visible.

        Returns:
            str: Redacted string with ``*`` replacing hidden characters.
        """
        if not value:
            return ""
        if visible_chars == 0:
            return "*" * len(value)
        if len(value) <= visible_chars:
            return "*" * len(value)
        hidden = len(value) - visible_chars
        return "*" * hidden + value[-visible_chars:]

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing LoggerSettings.

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        return LoggerSettings.model_json_schema()

    # ------------------------------------------------------------------
    # Test-specific helpers (not part of LoggerManager Protocol)
    # ------------------------------------------------------------------

    def get_logs(self) -> list[dict[str, Any]]:
        """Return a shallow copy of the accumulated log records.

        Returns:
            list[dict[str, Any]]: All recorded log entries in order.
        """
        return list(self._logs)

    def clear(self) -> None:
        """Reset the log buffer to empty.

        Security: Ensures no log data leaks between test cases.
        """
        self._logs.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record(self, level: str, message: str, **kwargs: Any) -> None:
        """Build a structured log record and append it to the buffer.

        Args:
            level: Log level string (DEBUG, INFO, WARNING, ERROR).
            message: The log message — coerced to str if not already.
            **kwargs: Extra key-value pairs stored on the record.
        """
        record: dict[str, Any] = {
            "level": level,
            "message": str(message),
        }
        # Apply bound context first, then per-call kwargs override
        record.update(self._context)
        record.update(kwargs)
        self._logs.append(record)
