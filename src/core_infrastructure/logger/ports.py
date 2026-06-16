"""LoggerManager Protocol — the contract every logger adapter must satisfy.

Defines the structured logging interface consumed by all infrastructure
managers. Adapters (structlog, in-memory test double) implement this
Protocol to provide multi-profile logging: dev (colored console), test
(silent/NullHandler), and prod (JSON).

Security: mask() ensures sensitive values are never written to log output.
Observability: Every log record auto-injects correlation_id, tenant_id,
    trace_id, and span_id from common.context.
@ai-directive: LoggerManager methods are SYNC only — structlog is sync,
    no async log methods are needed.

Author: CENF AI Team
Version: 0.1.0
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LoggerManager(Protocol):
    """Structured logging contract for multi-profile output.

    All infrastructure managers log exclusively through this interface.
    Concrete adapters select rendering strategy (console/JSON/silent) based
    on the active profile from LoggerSettings.

    Rules:
        - All log methods MUST NEVER raise — degrade silently on failure.
        - debug/info/warn/error accept arbitrary **kwargs for structured data.
        - bind() returns a new LoggerManager with additional context.
        - mask() returns a redacted string showing only the last N chars.
        - get_json_schema() enables LLM agent discovery of logger config.

    @ai-directive: When adding a new log level, update both the Protocol
        and all adapter implementations.
    """

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a DEBUG-level message with optional structured data.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs added to the log record.
        """
        ...

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an INFO-level message with optional structured data.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs added to the log record.
        """
        ...

    def warn(self, message: str, **kwargs: Any) -> None:
        """Log a WARNING-level message with optional structured data.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs added to the log record.
        """
        ...

    def error(self, message: str, exc: Exception | None = None, **kwargs: Any) -> None:
        """Log an ERROR-level message with optional exception and data.

        Args:
            message: The log message text.
            exc: Optional exception to include in the log record.
            **kwargs: Arbitrary key-value pairs added to the log record.
        """
        ...

    def bind(self, **kwargs: Any) -> "LoggerManager":
        """Create a new LoggerManager with additional bound context.

        The returned logger prepends the given kwargs to every subsequent
        log record. Useful for attaching request-scoped data (request_id,
        user_id, component) without passing it on every call.

        Args:
            **kwargs: Context keys to bind to all subsequent log records.

        Returns:
            LoggerManager: A new logger instance with bound context.
        """
        ...

    def mask(self, value: str, visible_chars: int = 4) -> str:
        """Return a redacted version of a sensitive string value.

        Replaces all but the last ``visible_chars`` characters with ``*``.

        Args:
            value: The sensitive string to mask.
            visible_chars: Number of trailing characters to leave visible.

        Returns:
            str: Redacted string (e.g., ``"secret1234"`` → ``"******1234"``).

        Security: Use before writing credentials, tokens, or PII to logs.
        """
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return the JSON Schema describing LoggerSettings.

        Used by LLM agents for tool discovery (AX — Agent Experience).

        Returns:
            dict[str, Any]: A valid JSON Schema object.
        """
        ...
