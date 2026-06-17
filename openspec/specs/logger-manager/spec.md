---
Spec_ID: SPEC_M02
Title: LoggerManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [logging, structlog, profiles, markers]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M02: LoggerManager

## Purpose

Provide structured logging with dev/test/prod profiles and configurable keyword markers for production search/filtering. Uses structlog for multi-profile output.

**Does NOT**: Replace ObservabilityManager (OTel), log secrets or unsanitized PII, use print/console.log.

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class LoggerManager(Protocol):
    """@ai-directive: LoggerManager methods are SYNC only — structlog is sync."""

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a DEBUG-level message with optional structured data."""
        ...

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an INFO-level message with optional structured data."""
        ...

    def warn(self, message: str, **kwargs: Any) -> None:
        """Log a WARNING-level message with optional structured data."""
        ...

    def error(self, message: str, exc: Exception | None = None, **kwargs: Any) -> None:
        """Log an ERROR-level message with optional exception and data."""
        ...

    def bind(self, **kwargs: Any) -> "LoggerManager":
        """Create a new LoggerManager with additional bound context."""
        ...

    def mask(self, value: str, visible_chars: int = 4) -> str:
        """Return a redacted version of a sensitive string value."""
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return JSON Schema describing LoggerSettings."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class LoggerSettings(BaseModel):
    profile: Literal["dev", "test", "prod"] = Field(default="dev")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
    output_path: str | None = Field(default=None)
    include_timestamp: bool = Field(default=True)
    max_stack_depth: int = Field(default=10, ge=1, le=50)
    markers: dict[str, str] = Field(default_factory=dict, description="Configurable keyword markers for log filtering")
```

## Gherkin Scenarios

### Scenario: Dev profile outputs colored console

- GIVEN LoggerSettings.profile = "dev"
- WHEN `logger.info("Hello")` is called
- THEN output is human-readable with colors and stack traces

### Scenario: Prod profile outputs JSON

- GIVEN LoggerSettings.profile = "prod"
- WHEN `logger.info("Hello", user_id="123")` is called
- THEN output is a single JSON line: `{"event": "Hello", "user_id": "123", ...}`

### Scenario: Test profile is silent

- GIVEN LoggerSettings.profile = "test"
- WHEN any log method is called
- THEN no output is produced (NullHandler)

### Scenario: Mask sensitive values

- WHEN `logger.mask("secret1234", visible_chars=4)` is called
- THEN it returns `"******1234"`

### Scenario: Contextvars auto-injection

- GIVEN correlation_id="abc" and tenant_id="tenant-1" are set in contextvars
- WHEN `logger.info("test")` is called
- THEN the log record includes `correlation_id="abc"` and `tenant_id="tenant-1"`

### Scenario: Logger never raises

- GIVEN a structlog processor that would normally raise
- WHEN any log method is called
- THEN the error is caught and logged at ERROR level
- AND the original log call degrades silently

## Error Classification

LoggerManager NEVER raises. All internal errors are caught and degraded silently.

## RED Metrics

- `cenf.logger.log_total{level="..."}` (counter)
- `cenf.logger.errors_total` (counter — internal processor failures only)
- `cenf.logger.log_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryLoggerAdapter` — collects logs in `list[dict]` for assertions.
- **Integration**: `StructlogAdapter` with JSON output capture (StringIO).
- **E2E**: Verify contextvars auto-injection across async boundaries.

## Do's and Don'ts

**Do**:
- Implement dev/test/prod profiles with appropriate processors
- Guarantee sync-only operations (no blocking of event-loop)
- Extract metadata (hostname, version) automatically
- Support configurable keyword markers from YAML

**Don't**:
- Replace ObservabilityManager (OTel)
- Log secrets or unsanitized PII
- Use print or console.log
