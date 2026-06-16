"""LoggerSettings — Pydantic model for LoggerManager configuration.

Validates the logging profile, verbosity level, and output format options
that drive the StructlogAdapter rendering strategy.

Security: output_path must be validated against path traversal attacks
    by the adapter implementation, not the model.
Observability: LoggerSettings schema is auto-discoverable via
    LoggerManager.get_json_schema().
@ai-directive: This model is the single validation gate for all logger
    configuration injected via ConfigManager.get_section("logger").

Author: CENF AI Team
Version: 0.1.0
"""

from typing import Literal

from pydantic import BaseModel, Field


class LoggerSettings(BaseModel):
    """Configuration model for LoggerManager adapter selection.

    The ``profile`` field determines which rendering strategy the
    StructlogAdapter uses:
        - ``"dev"``: Colored console output for local development.
        - ``"test"``: NullHandler — no output, for test runs.
        - ``"prod"``: JSON-structured output for log aggregation.

    Attributes:
        profile: Rendering strategy (dev/test/prod).
        log_level: Minimum log level emitted.
        output_path: Optional file path for log output (None = stdout).
        include_timestamp: Whether to attach ISO-8601 timestamps.
        max_stack_depth: Maximum stack frames included in ERROR records.
    """

    profile: Literal["dev", "test", "prod"] = Field(
        default="dev",
        description="Rendering strategy: colored console (dev), silent (test), JSON (prod).",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Minimum log level emitted by the logger adapter.",
    )
    output_path: str | None = Field(
        default=None,
        description="Optional file path for log output. None writes to stdout.",
    )
    include_timestamp: bool = Field(
        default=True,
        description="Whether to attach ISO-8601 timestamps to log records.",
    )
    max_stack_depth: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum stack frames included in ERROR exception records.",
    )
