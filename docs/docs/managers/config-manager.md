---
sidebar_position: 1
---

# ConfigManager (M01)

Read-only configuration from YAML + env vars following the [12-factor app](https://12factor.net/config) pattern. All infrastructure managers read configuration exclusively through this interface.

## Protocol

`ConfigManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.config.ports`.

### `get_env() → Env`

Return the current deployment environment.

```python
def get_env(self) -> Env: ...
```

**Returns:** One of `"local"`, `"dev"`, `"staging"`, `"prod"`.

---

### `get_string(key: str, default_value: str | None = None) → str`

Retrieve a string configuration value.

```python
def get_string(self, key: str, default_value: str | None = None) -> str: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `key` | `str` | Dot-notation config key (e.g., `"app.name"`) |
| `default_value` | `str \| None` | Fallback if key is not found |

**Raises:** `ValidationError` if key is missing and no default is provided.

---

### `get_number(key: str, default_value: float | None = None) → float`

Retrieve a numeric configuration value.

```python
def get_number(self, key: str, default_value: float | None = None) -> float: ...
```

**Raises:** `ValidationError` if key is missing and no default, or value is not numeric.

---

### `get_boolean(key: str, default_value: bool | None = None) → bool`

Retrieve a boolean configuration value.

```python
def get_boolean(self, key: str, default_value: bool | None = None) -> bool: ...
```

**Raises:** `ValidationError` if key is missing and no default, or value is not boolean.

---

### `get_json(key: str, default_value: Any = None) → Any`

Retrieve a JSON-deserialized configuration value.

```python
def get_json(self, key: str, default_value: Any = None) -> Any: ...
```

A dot-notation config key pointing to a JSON string value. Returns the deserialized Python object.

**Raises:** `ValidationError` if the value is not valid JSON.

---

### `get_section(namespace: str) → dict[str, Any]`

Retrieve an entire configuration section as a dict.

```python
def get_section(self, namespace: str) -> dict[str, Any]: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `namespace` | `str` | Dot-notation namespace prefix (e.g., `"logger"`) |

**Returns:** All keys under the given namespace as a flat dict.

---

### `async reload() → None`

Hot-reload configuration from the backing store.

```python
async def reload(self) -> None: ...
```

Must be protected by an `asyncio.Lock` in adapter implementations to prevent concurrent reload races. Reload events are logged at INFO level.

---

### `get_json_schema() → dict[str, Any]`

Return the JSON Schema describing the `CoreSettings` model.

```python
def get_json_schema(self) -> dict[str, Any]: ...
```

Used by LLM agents for tool discovery (AX — Agent Experience). Schema includes field descriptions, types, defaults, and constraints.

---

### Env Literal

```python
Env = Literal["local", "dev", "staging", "prod"]
```

The `get_env()` return type controls log verbosity, telemetry sampling, and adapter behavior across all managers.

## Models

### `CoreSettings`

**File:** `core_infrastructure.config.models`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `env` | `Literal["local","dev","staging","prod"]` | `"dev"` | Deployment environment |
| `app_name` | `str` (1–128 chars) | `"cenf-core"` | Application instance name |
| `version` | `str` (semver regex) | `"0.1.0"` | Semver string for health checks |
| `log_level` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `"INFO"` | Minimum log level |

Validated at bootstrap — if validation fails, the application exits immediately (fail-fast).

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `PydanticConfigAdapter` | YAML files + env vars (pydantic-settings) | Production — loads `config.yaml` and overlays env vars |
| `InMemoryConfigAdapter` | Python `dict` | Testing — inject configuration directly without files |

## Usage Example

```python
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter

# Bootstrap — config is FIRST (zero dependencies)
config = InMemoryConfigAdapter({
    "app.name": "my-service",
    "app.env": "dev",
    "db.host": "localhost",
    "db.port": "5432",
    "logger.profile": "dev",
})

# Typed access
env = config.get_env()                  # "dev"
name = config.get_string("app.name")    # "my-service"
port = config.get_number("db.port")     # 5432.0
debug = config.get_boolean("app.debug", default_value=False)  # False

# Section extraction
log_section = config.get_section("logger")
# → {"profile": "dev", "log_level": "INFO", ...}

# Hot-reload (async)
await config.reload()

# LLM agent schema discovery
schema = config.get_json_schema()
```

## @ai-directive

> **No accedas a `os.environ` directamente.** Always use `config.get_string()` or the appropriate typed getter. All configuration flows through ConfigManager for validation, schema discovery, and auditability.

- When adding a new config key, update `CoreSettings` AND ensure both adapters handle the new key correctly.
- The generic type parameters on `get_json[T]` and `get_section[T]` MUST be preserved by all adapter implementations for mypy strict mode.

## Related

- [LoggerManager](logger-manager.md) — reads `logger` section via `get_section("logger")`
- [SecretManager](secret-manager.md) — reads encryption keys from config
- [AuthManager](auth-manager.md) — reads `issuer`, `audience`, `jwks_url`
- [DatabaseManager](database-manager.md) — reads `dsn` connection string
