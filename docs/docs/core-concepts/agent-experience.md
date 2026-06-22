# Agent Experience (AX)

core-cenf is designed to be used by **both humans and AI coding agents**. The Agent
Experience (AX) layer gives AI agents everything they need to discover, understand, and
correctly use the infrastructure without scanning thousands of lines of source code.

## Three Discovery Mechanisms

### 1. `AGENTS.md` — The Entry Point

The `AGENTS.md` file at the repository root is the first file any AI agent reads. It is a
~200-line document that provides:

- **What core-cenf is** — one sentence, no fluff.
- **The Golden Rule** — code example of correct vs. incorrect usage.
- **All 16 managers** — a table with manager name, what it does, key method, and test
  adapter.
- **Bootstrap pattern** — copy-paste template for wiring managers.
- **`@ai-directive` reference** — every critical rule per manager in a single table.
- **Context propagation** — the implicit rule: never pass context explicitly.
- **Error taxonomy** — the five error types with import paths.
- **Testing patterns** — how to use in-memory adapters in tests.
- **Commit gate** — the three commands that must pass before every commit.

```markdown
# AGENTS.md excerpt
@ai-directive: Never access `os.environ` directly. Always use `config.get_string()`.
```

An agent can read `AGENTS.md` in ~90 seconds and be productive.

### 2. `@ai-directive` Docstring Annotations

Every manager Protocol has `@ai-directive` annotations in its docstring. These are
machine-readable rules embedded directly in the source code:

```python
@runtime_checkable
class ConfigManager(Protocol):
    """Configuration contract for the 12-factor app pattern.

    All infrastructure managers read configuration exclusively through this
    interface. Concrete adapters load from YAML + env vars (pydantic-settings)
    or a dict (in-memory test double).

    Rules:
        - get_env() returns the current deployment environment.
        - All get_* methods accept an optional default_value.
        - get_json() and get_section() use generics for type-safe extraction.
        - reload() is async — allows hot-reload without blocking.
        - get_json_schema() returns JSON Schema for LLM agent discovery.

    @ai-directive: When adding a new config key, update CoreSettings AND
        ensure both adapters handle the new key correctly.
    """
```

Agents can grep for `@ai-directive` across the codebase and compile a complete rulebook
without reading implementation code. Every annotation is a behavioral invariant that MUST
be followed.

Key directives from across managers:

| Manager | `@ai-directive` |
|---|---|
| ConfigManager | Never access `os.environ` directly. Always use `config.get_string()`. |
| LoggerManager | Methods are SYNC only. Use `logger.mask()` before logging any credential. |
| SecretManager | `SecretValue.__repr__` is auto-masked. Never log raw `.value`. |
| ErrorHandlingManager | `@handle_errors` NEVER swallows — always re-raises. |
| ObservabilityManager | If OTel export fails, degrade gracefully — never throw. |
| AuthManager | Set `tenant_id` and `principal_id` contextvars after validation. |
| CacheManager | `get_or_set()` uses XFetch stampede mitigation. Cache miss is NOT an error. |
| DatabaseManager | Always use `async with db.transaction() as tx:`. |
| FileStorageManager | Never infer MIME type from file extension. |
| TaskQueueManager | Payloads MUST be JSON-serializable. |
| ExternalAPIManager | Circuit breaker protects by host. Timeouts are mandatory. |
| FeatureFlagManager | NEVER throw on evaluation failure — return default. |
| DependencyManager | Never pass `module_path` from user input. Validate against allowlist. |
| DynamicPromptingManager | Conditions are dict-based equality. No CEL parser needed. |
| AlertManager | Fire-and-forget. Never block main flow if alert dispatch fails. |
| RateLimiterManager | Use `is_allowed()` before any rate-limited operation. |

### 3. `get_json_schema()` — Tool Discovery

Every `ConfigManager` adapter exposes a `get_json_schema()` method that returns the JSON
Schema of the `CoreSettings` Pydantic model:

```python
config = InMemoryConfigAdapter({"app.name": "my-app"})
schema = config.get_json_schema()
```

```json
{
  "title": "CoreSettings",
  "type": "object",
  "properties": {
    "env": {
      "type": "string",
      "enum": ["local", "dev", "staging", "prod"],
      "default": "dev",
      "description": "Deployment environment"
    },
    "app_name": {
      "type": "string",
      "minLength": 1,
      "maxLength": 128,
      "default": "cenf-core",
      "description": "Unique name for this application instance"
    },
    "version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+",
      "default": "0.1.0",
      "description": "Semver string used in health checks and telemetry"
    },
    "log_level": {
      "type": "string",
      "enum": ["DEBUG", "INFO", "WARNING", "ERROR"],
      "default": "INFO",
      "description": "Minimum log level emitted by LoggerManager"
    }
  },
  "required": []
}
```

This enables AI agents to **discover available configuration keys** without scanning
source code. The agent can introspect field types, enums, defaults, descriptions, and
constraints — exactly the information needed to write correct configuration.

## Agent Workflow

When an AI coding agent encounters a CENF codebase, the expected flow is:

```mermaid
flowchart TD
    A[Agent starts] --> B[Read AGENTS.md]
    B --> C{Need to use a manager?}
    C -->|Yes| D[Read the manager's ports.py]
    D --> E[Find @ai-directive rules]
    E --> F[Import Protocol, not adapter]
    F --> G[Check existing tests for pattern]
    C -->|Need config keys| H[Call config.get_json_schema()]
    H --> F
    C -->|No| I[Write domain logic]
    I --> J[Commit: ruff + mypy + pytest]
```

1. **Read `AGENTS.md`** — understand the architecture and rules in 90 seconds.
2. **Read `ports.py`** for the specific manager — discover the method signatures and
   `@ai-directive` annotations.
3. **Import the Protocol** — never the adapter.
4. **Check existing tests** — `tests/conftest.py` shows the wiring pattern with in-memory
   adapters.
5. **Commit** — run the mandatory gate: `ruff check`, `mypy --strict`, `pytest`.

## CodeGraph Integration

The `.codegraph/` directory contains a knowledge graph of the entire codebase. Agents
with CodeGraph support can query structural relationships:

- "What depends on ConfigManager?"
- "What adapters implement the CacheManager Protocol?"
- "Show me all callers of `set_correlation_id()`."

Regenerate with:

```bash
codegraph index
```

## Why This Matters

Traditional libraries require AI agents to read hundreds of files, infer patterns from
examples, and hope they get the conventions right. core-cenf's AX layer makes the
contract **explicit**:

- `AGENTS.md` states the rules in one place.
- `@ai-directive` embeds rules at the point of use.
- `get_json_schema()` provides machine-readable configuration discovery.
- `@runtime_checkable` Protocols enable structural type checks without importing
  adapters.

An AI agent using core-cenf should never import an adapter directly, never access
`os.environ`, never log a raw secret, and never pass context explicitly — because the AX
layer tells it not to, at every level.
