---
Spec_ID: SPEC_M01
Title: ConfigManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [config, pydantic-settings, pyyaml, 12-factor]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M01: ConfigManager

## Purpose

Provide the single source of truth for immutable environment configuration. Resolves 12-factor precedence (env vars > remote > files > defaults), validates schemas at bootstrap (fail-fast), and supports hot-reload.

**Does NOT**: Write configuration (read-only), read from domain databases, include secrets (use SecretManager), include business branching logic.

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Literal, Protocol, runtime_checkable

Env = Literal["local", "dev", "staging", "prod"]

@runtime_checkable
class ConfigManager(Protocol):
    """@ai-directive: Never access os.environ directly; always use ConfigManager."""

    def get_env(self) -> Env:
        """Return the current deployment environment."""
        ...

    def get_string(self, key: str, default_value: str | None = None) -> str:
        """Retrieve a string configuration value by dot-notation key."""
        ...

    def get_number(self, key: str, default_value: float | None = None) -> float:
        """Retrieve a numeric configuration value."""
        ...

    def get_boolean(self, key: str, default_value: bool | None = None) -> bool:
        """Retrieve a boolean configuration value."""
        ...

    def get_json(self, key: str, default_value: Any = None) -> Any:
        """Retrieve a JSON-deserialized configuration value."""
        ...

    def get_section(self, namespace: str) -> dict[str, Any]:
        """Retrieve an entire configuration section as a dict."""
        ...

    async def reload(self) -> None:
        """Hot-reload configuration from the backing store."""
        ...

    def get_json_schema(self) -> dict[str, Any]:
        """Return JSON Schema describing the CoreSettings model."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class CoreSettings(BaseModel):
    env: Literal["local", "dev", "staging", "prod"] = Field(default="dev")
    app_name: str = Field(min_length=1, max_length=128, default="cenf-core")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+", default="0.1.0")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")
```

## Gherkin Scenarios

### Scenario: Get string with default

- GIVEN ConfigManager loaded with YAML containing `app.name: "my-app"`
- WHEN `get_string("app.name")` is called
- THEN it returns `"my-app"`

### Scenario: Get string missing key with default

- GIVEN ConfigManager loaded with YAML
- WHEN `get_string("missing.key", default_value="fallback")` is called
- THEN it returns `"fallback"`

### Scenario: Get string missing key without default

- GIVEN ConfigManager loaded with YAML
- WHEN `get_string("missing.key")` is called (no default)
- THEN it raises `ValidationError`

### Scenario: Hot-reload with lock

- GIVEN ConfigManager is running with initial config
- WHEN two concurrent `reload()` calls are made
- THEN only one reload executes at a time (asyncio.Lock)
- AND the final state reflects the last successful reload

### Scenario: Invalid YAML causes PermanentError

- GIVEN a YAML file with syntax error (unclosed quote)
- WHEN ConfigManager attempts to load it
- THEN it raises `PermanentError` with parse details

### Scenario: Environment detection

- GIVEN env var `CENF_ENV=prod` is set
- WHEN `get_env()` is called
- THEN it returns `"prod"`

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Key missing, no default | VALIDATION | Re-raise immediately |
| Type coercion failure | VALIDATION | Re-raise immediately |
| Config file not found | PERMANENT | Fail bootstrap |
| Malformed YAML | PERMANENT | Fail bootstrap |

## RED Metrics

- `cenf.config.reload_total` (counter)
- `cenf.config.errors_total{error_type="..."}` (counter)
- `cenf.config.reload_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryConfigAdapter` — dict-based, no I/O. Tests all `get_*` methods and error paths.
- **Integration**: `PydanticSettingsAdapter` with temp YAML files and env var overrides.
- **E2E**: Bootstrap fails on invalid YAML.

## Do's and Don'ts

**Do**:
- Resolve 12-factor precedence: env vars > remote > files > defaults
- Validate schemas at bootstrap using Pydantic V2 (fail-fast)
- Cache reads and support async hot-reload
- Protect reload with `asyncio.Lock`

**Don't**:
- Write configuration (read-only)
- Read from domain databases
- Include secrets (use SecretManager)
- Include business branching logic
