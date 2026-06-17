---
Spec_ID: SPEC_06
Title: AX Schemas
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [agent-experience, json-schema, tool-discovery, llm]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_06: AX Schemas

## Purpose

Define JSON schemas for agent function calling for all 16 managers, tool discovery contracts, `@ai-directive` annotations, and LLM agent integration guide.

## Tool Discovery Contract

Every manager SHALL expose a `get_json_schema()` method returning a JSON Schema compatible with OpenAPI function calling:

```python
@staticmethod
def get_json_schema() -> dict[str, Any]: ...
```

### Schema Structure

Each schema SHALL include:
- `name`: Manager name (e.g., `"cache_manager"`)
- `description`: One-line purpose statement
- `parameters`: JSON Schema with `properties` for each method
- `required`: List of required parameters
- `ai_directive`: The `@ai-directive` annotation text for agent guidance

#### Scenario: Schema validity

- GIVEN any manager's `get_json_schema()` output
- WHEN validated against JSON Schema Draft 2020-12
- THEN it passes validation
- AND includes all public methods as callable tools

## Manager AX Schemas

### M01: ConfigManager

```json
{
  "name": "config_manager",
  "description": "Read configuration values from environment and YAML files.",
  "tools": [
    {"name": "get_string", "description": "Get a string config value", "parameters": {"key": "string", "default_value": "string"}},
    {"name": "get_number", "description": "Get a numeric config value", "parameters": {"key": "string", "default_value": "number"}},
    {"name": "get_boolean", "description": "Get a boolean config value", "parameters": {"key": "string", "default_value": "boolean"}},
    {"name": "get_section", "description": "Get an entire config section", "parameters": {"namespace": "string"}}
  ],
  "ai_directive": "Never access os.environ directly; always use ConfigManager."
}
```

### M07: CacheManager

```json
{
  "name": "cache_manager",
  "description": "Key-value cache with TTL and stampede mitigation.",
  "tools": [
    {"name": "get", "description": "Retrieve cached value", "parameters": {"key": "string"}},
    {"name": "set", "description": "Store value with TTL", "parameters": {"key": "string", "value": "any", "ttl": "integer"}},
    {"name": "delete", "description": "Remove cached entry", "parameters": {"key": "string"}},
    {"name": "exists", "description": "Check if key exists", "parameters": {"key": "string"}}
  ],
  "ai_directive": "Use get_or_set for hot keys to prevent stampede. Never cache credentials."
}
```

### M08: DatabaseManager

```json
{
  "name": "database_manager",
  "description": "Transactional database access with generic repositories.",
  "tools": [
    {"name": "transaction", "description": "Begin atomic transaction scope", "parameters": {}},
    {"name": "get_repository", "description": "Get typed repository for entity", "parameters": {"entity_type": "string"}}
  ],
  "ai_directive": "Always use transaction() for write operations. Never expose raw sessions."
}
```

### M11: ExternalAPIManager

```json
{
  "name": "external_api_manager",
  "description": "Resilient HTTP client with circuit breaker and retry.",
  "tools": [
    {"name": "get", "description": "HTTP GET request", "parameters": {"url": "string", "headers": "object", "timeout": "number"}},
    {"name": "post", "description": "HTTP POST request", "parameters": {"url": "string", "body": "object", "headers": "object", "timeout": "number"}},
    {"name": "get_circuit_state", "description": "Check circuit breaker state", "parameters": {"host": "string"}}
  ],
  "ai_directive": "Circuit breaker is per-host. Check state before retrying failed requests."
}
```

## @ai-directive Annotation Standard

Every Protocol method SHALL include `@ai-directive` in its docstring:

```python
def get_secret(self, key: str) -> str:
    """...
    @ai-directive: NEVER log the return value. Use SecretValue.get_masked() for display.
    """
```

### Directive Categories

| Category | Purpose | Example |
|----------|---------|---------|
| **Security** | Prevent credential leakage | "Never log secrets" |
| **Performance** | Avoid anti-patterns | "Use get_or_set for hot keys" |
| **Correctness** | Ensure proper usage | "Always use transaction() for writes" |
| **Discovery** | Guide agent exploration | "Call get_json_schema() first" |

## LLM Agent Integration Guide

### Step 1: Discover Available Tools

```python
from core_infrastructure import (
    ConfigManager, CacheManager, DatabaseManager,
    ExternalAPIManager, FeatureFlagManager
)

tools = [
    ConfigManager.get_json_schema(),
    CacheManager.get_json_schema(),
    DatabaseManager.get_json_schema(),
    ExternalAPIManager.get_json_schema(),
    FeatureFlagManager.get_json_schema(),
]
```

### Step 2: Register Tools with Agno

Pass the schemas to Agno's function calling registry. The agent can then invoke manager methods through structured JSON calls.

### Step 3: Handle Responses

All manager responses are JSON-serializable. Error responses include `error_type` and `details` for agent decision-making.

#### Scenario: Agent discovers and uses cache

- GIVEN an LLM agent needs to cache a computation result
- WHEN the agent calls `cache_manager.get_json_schema()`
- THEN it discovers `set(key, value, ttl)` and `get(key)` tools
- AND the agent calls `set("computation:abc", result, ttl=300)`
- AND subsequent calls to `get("computation:abc")` return the cached result
