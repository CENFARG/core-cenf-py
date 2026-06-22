---
sidebar_position: 2
---

# LoggerManager (M02)

Structured logging with multi-profile output (dev/test/prod). Every log record auto-injects `correlation_id`, `tenant_id`, `trace_id`, and `span_id` from `common.context` contextvars.

## Protocol

`LoggerManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.logger.ports`.

### `debug(message: str, **kwargs: Any) → None`

Log a DEBUG-level message with optional structured data.

```python
def debug(self, message: str, **kwargs: Any) -> None: ...
```

All log methods MUST NEVER raise — degrade silently on failure.

---

### `info(message: str, **kwargs: Any) → None`

Log an INFO-level message with optional structured data.

```python
def info(self, message: str, **kwargs: Any) -> None: ...
```

---

### `warn(message: str, **kwargs: Any) → None`

Log a WARNING-level message with optional structured data.

```python
def warn(self, message: str, **kwargs: Any) -> None: ...
```

---

### `error(message: str, exc: Exception | None = None, **kwargs: Any) → None`

Log an ERROR-level message with optional exception and data.

```python
def error(self, message: str, exc: Exception | None = None, **kwargs: Any) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `message` | `str` | The log message text |
| `exc` | `Exception \| None` | Optional exception to include in the log record |
| `**kwargs` | `Any` | Arbitrary key-value pairs added to the log record |

---

### `bind(**kwargs: Any) → LoggerManager`

Create a new LoggerManager with additional bound context.

```python
def bind(self, **kwargs: Any) -> LoggerManager: ...
```

The returned logger prepends the given kwargs to every subsequent log record. Useful for attaching request-scoped data (`request_id`, `user_id`, `component`) without passing it on every call.

---

### `mask(value: str, visible_chars: int = 4) → str`

Return a redacted version of a sensitive string value.

```python
def mask(self, value: str, visible_chars: int = 4) -> str: ...
```

Replaces all but the last `visible_chars` characters with `*`.

**Examples:**
```python
logger.mask("secret1234")       # → "******1234"
logger.mask("abc", visible_chars=1)  # → "**c"
```

**Security:** Use before writing credentials, tokens, or PII to logs.

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing `LoggerSettings`. Used by LLM agents for tool discovery (AX — Agent Experience).

## Profiles

| Profile | Rendering Strategy | Use Case |
|---------|-------------------|----------|
| `dev` | Colored console output (structlog `ConsoleRenderer`) | Local development |
| `test` | Silent / `NullHandler` — no output | Test runs, CI |
| `prod` | JSON-structured output (structlog `JSONRenderer`) | Log aggregation (ELK, Datadog) |

## Models

### `LoggerSettings`

**File:** `core_infrastructure.logger.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `profile` | `Literal["dev","test","prod"]` | `"dev"` | Rendering strategy |
| `log_level` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `"INFO"` | Minimum log level emitted |
| `output_path` | `str \| None` | `None` | File path for log output (None = stdout) |
| `include_timestamp` | `bool` | `True` | Attach ISO-8601 timestamps to log records |
| `max_stack_depth` | `int` (1–50) | `10` | Maximum stack frames in ERROR exception records |

## Context Injection

Every log record automatically includes these contextvars (set by middleware / AuthManager):

| Key | Source | Description |
|-----|--------|-------------|
| `correlation_id` | `common.context` | Request trace identifier |
| `tenant_id` | `common.context` | Multi-tenant identifier |
| `trace_id` | `common.context` | OpenTelemetry trace ID |
| `span_id` | `common.context` | OpenTelemetry span ID |

**Rule:** NEVER pass context as function arguments. Always use contextvars — the logger injects them automatically.

## Keyword Markers

Configurable from YAML under the `logger` section. The `StructlogAdapter` supports keyword markers for filtering and alerting. For example, `error` messages with `severity: "critical"` can trigger alerting pipelines.

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `StructlogAdapter` | [structlog](https://www.structlog.org/) | Production — multi-profile (dev/test/prod) with colored console or JSON output |
| `InMemoryLoggerAdapter` | Python list | Testing — captures all log records in `.get_logs()` for assertions |

## Usage Example

```python
from core_infrastructure.logger.adapters.structlog_adapter import StructlogAdapter

# Bootstrap — depends on ConfigManager
logger = StructlogAdapter(config_manager=config)

# Standard log levels
logger.debug("Processing item", item_id=42)
logger.info("Service started", port=8080, env=config.get_env())
logger.warn("Rate limit approaching", current_rate=0.85)
logger.error("Database connection failed", exc=TimeoutError(), host="db1")

# Context binding for request-scoped data
request_logger = logger.bind(request_id="req-abc123", user_id="usr-99")
request_logger.info("Request received")  # includes request_id + user_id

# Masking sensitive values BEFORE logging
token = "sk-live-abc123xyz789"
logger.info("Using API key", key=logger.mask(token))  # logs "******z789"

# LLM agent discovery
schema = logger.get_json_schema()
```

## @ai-directive

- LoggerManager methods are SYNC only — structlog is sync, no async log methods are needed.
- **Use `logger.mask()` before logging any credential, token, or PII.**
- When adding a new log level, update both the Protocol and all adapter implementations.
- All log methods MUST NEVER raise — degrade silently on failure.

## Related

- [ConfigManager](config-manager.md) — reads `logger` section via `get_section("logger")`
- [SecretManager](secret-manager.md) — use `logger.mask()` before logging secrets
- [ObservabilityManager](observability-manager.md) — trace_id and span_id auto-injected from context
- [AuthManager](auth-manager.md) — sets tenant_id contextvar consumed by logger
