"""StructlogAdapter — production LoggerManager using structlog.

Implements the LoggerManager Protocol with three rendering profiles:
  - ``"dev"``: Colored console output for local development.
  - ``"test"``: NullHandler — produces no output.
  - ``"prod"``: JSON-structured output for log aggregation systems.

Contextvar injection: Every log record automatically includes
``correlation_id``, ``tenant_id``, ``trace_id``, and ``span_id`` from
``core_infrastructure.common.context`` via a custom structlog processor.

Security: mask() ensures sensitive values are never written to logs.
Observability: All log records carry trace context for correlation across
    services in distributed tracing systems.
@ai-directive: This adapter is sync-only — structlog does not require
    async log methods. Inject ConfigManager via constructor.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, ClassVar

import structlog

from core_infrastructure.common import context as ctx
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.logger.models import LoggerSettings
from core_infrastructure.logger.ports import LoggerManager

# ---------------------------------------------------------------------------
# Structlog processors
# ---------------------------------------------------------------------------


def _inject_contextvars(
    _logger: Any,
    _method_name: str,
    event_dict: Any,
) -> Any:
    """Structlog processor: inject trace context into every log record.

    Reads correlation_id, tenant_id, trace_id, and span_id from
    contextvars and adds them to the structured log event.

    Args:
        _logger: The stdlib logger instance (unused by this processor).
        _method_name: The log method name (unused by this processor).
        event_dict: The current event dictionary being built.

    Returns:
        The event dict with contextvars injected.

    Observability: This is the single point where context propagation
        meets structured logging — every log line gets trace context
        without any per-call boilerplate.
    """
    event_dict["correlation_id"] = ctx.get_correlation_id()
    event_dict["tenant_id"] = ctx.get_tenant_id()
    trace_id = ctx.get_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
    span_id = ctx.get_span_id()
    if span_id:
        event_dict["span_id"] = span_id
    return event_dict


# ---------------------------------------------------------------------------
# Profile-specific structlog configuration
# ---------------------------------------------------------------------------


def _configure_dev() -> None:
    """Configure structlog for colored console output (dev profile).

    Uses ConsoleRenderer with colors, timestamps, and human-readable format.
    Writes to stdout at DEBUG level.
    """
    # Reset root logger level in case a previous test profile suppressed it
    logging.getLogger().setLevel(logging.DEBUG)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            _inject_contextvars,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _configure_test() -> None:
    """Configure structlog for silent output (test profile).

    Routes all log events to a NullHandler — no output is produced.
    Used during test runs to avoid noisy console output.
    """
    null_handler = logging.NullHandler()
    structlog.configure(
        processors=[
            _inject_contextvars,
            structlog.processors.format_exc_info,
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    # Suppress all stdlib logging as well
    root_logger = logging.getLogger()
    root_logger.handlers = [null_handler]
    root_logger.setLevel(logging.CRITICAL + 1)


def _configure_prod() -> None:
    """Configure structlog for JSON output (prod profile).

    Uses JSONRenderer for machine-readable output. Suitable for ingestion
    by log aggregation tools (ELK, Datadog, Splunk).
    """
    # Reset root logger level in case a previous test profile suppressed it
    logging.getLogger().setLevel(logging.DEBUG)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            _inject_contextvars,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


# ---------------------------------------------------------------------------
# StructlogAdapter
# ---------------------------------------------------------------------------


class StructlogAdapter:
    """Production LoggerManager using structlog for structured logging.

    Reads ``LoggerSettings`` from ``ConfigManager.get_section("logger")``
    on construction and configures structlog with the appropriate rendering
    profile.

    Args:
        config: ConfigManager instance providing logger settings.

    Usage::

        config = PydanticConfigAdapter(config_path="config.yaml")
        logger = StructlogAdapter(config=config)
        logger.info("user action", user_id="123", action="login")
    """

    _PROFILE_CONFIGURATORS: ClassVar[dict[str, Any]] = {
        "dev": _configure_dev,
        "test": _configure_test,
        "prod": _configure_prod,
    }

    def __init__(self, config: ConfigManager) -> None:
        self._config = config
        self._settings = self._load_settings()
        self._configure_structlog()
        self._logger = structlog.get_logger()

    # ------------------------------------------------------------------
    # Public API — LoggerManager Protocol
    # ------------------------------------------------------------------

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a DEBUG-level message.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs added to the log record.
        """
        with contextlib.suppress(Exception):
            self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an INFO-level message.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs added to the log record.
        """
        with contextlib.suppress(Exception):
            self._logger.info(message, **kwargs)

    def warn(self, message: str, **kwargs: Any) -> None:
        """Log a WARNING-level message.

        Args:
            message: The log message text.
            **kwargs: Arbitrary key-value pairs added to the log record.
        """
        with contextlib.suppress(Exception):
            self._logger.warning(message, **kwargs)

    def error(
        self,
        message: str,
        exc: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Log an ERROR-level message with optional exception.

        Args:
            message: The log message text.
            exc: Optional exception whose traceback will be included.
            **kwargs: Arbitrary key-value pairs added to the log record.
        """
        try:
            if exc is not None:
                self._logger.error(message, exc_info=exc, **kwargs)
            else:
                self._logger.error(message, **kwargs)
        except Exception:
            pass

    def bind(self, **kwargs: Any) -> LoggerManager:
        """Create a new structlog logger with additional bound context.

        Args:
            **kwargs: Context keys to bind to all subsequent records.

        Returns:
            StructlogAdapter: A new adapter wrapping a bound structlog logger.
        """
        bound_adapter = StructlogAdapter.__new__(StructlogAdapter)
        bound_adapter._config = self._config
        bound_adapter._settings = self._settings
        bound_adapter._logger = self._logger.bind(**kwargs)
        return bound_adapter

    def mask(self, value: str, visible_chars: int = 4) -> str:
        """Redact a sensitive string, showing only the last N characters.

        Args:
            value: The sensitive string to mask.
            visible_chars: Number of trailing characters to leave visible.

        Returns:
            str: Redacted string (e.g., ``"mysecret"`` → ``"****cret"``).

        Security: Call before logging credentials, tokens, or PII.
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_settings(self) -> LoggerSettings:
        """Load and validate LoggerSettings from ConfigManager.

        Returns:
            LoggerSettings: Validated logger configuration.
        """
        section = self._config.get_section("logger")
        return LoggerSettings.model_validate(section)

    def _configure_structlog(self) -> None:
        """Apply the structlog configuration for the current profile.

        Delegates to the appropriate configurator based on LoggerSettings.profile.
        """
        configurator = self._PROFILE_CONFIGURATORS.get(self._settings.profile)
        if configurator:
            configurator()
