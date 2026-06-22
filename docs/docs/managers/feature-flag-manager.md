---
sidebar_position: 12
---

# FeatureFlagManager (M12)

Runtime feature toggles with context-based evaluation for staged rollouts and multi-tenant isolation. Two-phase strategy: `FileFeatureFlagAdapter` (YAML + watchfiles) for MVP, with `Unleash` reserved for future production. **NEVER throw on evaluation failure — return default.**

## Protocol

`FeatureFlagManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.feature_flags.ports`.

### `is_enabled(flag_key, context) → bool`

Check if a feature flag is enabled. Evaluates rules against context. Returns `False` for unknown flags — never raises.

```python
def is_enabled(
    self,
    flag_key: str,
    context: FlagContext | None = None,
) -> bool: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `flag_key` | `str` | Feature flag identifier (max 128 chars) |
| `context` | `FlagContext \| None` | Optional evaluation context for rule-based decisions |

**Returns:** `True` if flag is enabled and all rules pass, `False` otherwise.

---

### `get_flag_value(flag_key, context, default) → Any`

Get the value (payload) of a feature flag. Returns `default` on cache miss.

```python
def get_flag_value(
    self,
    flag_key: str,
    context: FlagContext | None = None,
    default: Any = None,
) -> Any: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `default` | `Any` | Value returned if the flag is not found or disabled |

---

### `get_all_flags(context) → dict[str, bool]`

Get the enabled state of all feature flags, evaluating each against the provided context.

```python
def get_all_flags(
    self,
    context: FlagContext | None = None,
) -> dict[str, bool]: ...
```

---

### `async refresh() → None`

Refresh the local flag cache from the provider. No-op for memory adapters; polls Unleash API for Unleash adapters.

```python
async def refresh(self) -> None: ...
```

---

## Models

**File:** `core_infrastructure.feature_flags.models`

### `FeatureFlag`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `key` | `str` (1–128) | required | Unique flag identifier |
| `enabled` | `bool` | `False` | Whether the flag is enabled by default |
| `value` | `Any` | `None` | Optional payload returned by `get_flag_value()` |
| `rules` | `list[dict[str, str]]` | `[]` | Context-based evaluation rules |

Each rule: `{"attribute": str, "operator": "eq", "value": str}`. All rules must match for flag to be enabled. Only `"eq"` operator is supported in MVP.

### `FlagContext`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tenant_id` | `str` (1–64) | `"global"` | Tenant identifier — **local-only, never sent externally** |
| `environment` | `str` (1–64) | `"development"` | Deployment environment |
| `attributes` | `dict[str, str]` | `{}` | Arbitrary key-value pairs for rule matching |

### `FlagConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `"memory" \| "unleash"` | `"memory"` | Flag provider backend |
| `cache_ttl` | `int` (≥1) | `60` | Cache TTL in seconds |
| `default_all` | `bool` | `False` | Default for unknown flags (`False` = fail-safe) |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `FileFeatureFlagAdapter` | YAML file + `asyncio.Lock` | Production MVP — reads `flags.yaml`, supports hot-reload |
| `MemoryFeatureFlagAdapter` | In-memory dict | Testing — inject flags directly via `set_flag()` |

**Two-phase strategy:** `FileFeatureFlagAdapter` (YAML + `watchfiles`) is the current MVP. `Unleash` backend is reserved for future production with server-side evaluation and real-time updates.

---

## Usage Example

```python
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FlagConfig, FlagContext, FeatureFlag

feature_flags = MemoryFeatureFlagAdapter(config=FlagConfig(default_all=False))

# Register flags with rules
feature_flags.set_flag(FeatureFlag(
    key="new_parser",
    enabled=True,
    value={"parser_version": "v2", "engine": "rust-pdf"},
))
feature_flags.set_flag(FeatureFlag(
    key="experimental_ocr",
    enabled=False,
))
feature_flags.set_flag(FeatureFlag(
    key="staging_only_feature",
    enabled=True,
    rules=[{"attribute": "environment", "operator": "eq", "value": "staging"}],
))

# Evaluate with context
ctx = FlagContext(tenant_id="cntrs", environment="dev")

new_parser = feature_flags.is_enabled("new_parser", context=ctx)
# → True

experimental = feature_flags.is_enabled("experimental_ocr", context=ctx)
# → False

staging_feat = feature_flags.is_enabled("staging_only_feature", context=ctx)
# → False (rule: environment must be "staging", we're in "dev")

unknown = feature_flags.is_enabled("nonexistent", context=ctx)
# → False (fail-safe: unknown flags return False)

# Get flag payload
parser_value = feature_flags.get_flag_value("new_parser", context=ctx)
# → {"parser_version": "v2", "engine": "rust-pdf"}

# List all flags
all_flags = feature_flags.get_all_flags(context=ctx)
# → {"new_parser": True, "experimental_ocr": False, "staging_only_feature": False}

# YAML file format (for FileFeatureFlagAdapter)
# flags.yaml:
#   new_parser:
#     enabled: true
#     value:
#       parser_version: v2
#       engine: rust-pdf
#   staging_only_feature:
#     enabled: true
#     rules:
#       - condition: {environment: staging}
```

---

## @ai-directive

> **NEVER throw on evaluation failure — return default.** `is_enabled()` MUST return `False` for unknown flags — never raise. `get_flag_value()` returns the provided `default` on cache miss. `refresh()` is async for Unleash polling but may be sync for memory adapters. Context evaluation is dict-based equality — `tenant_id` is local-only, never sent to external providers. Unknown flags return `False` (fail-safe). Rules support environment matching for staged rollouts.

## Related

- [ConfigManager](config-manager.md) — supplies `feature_flags.file_path` and `feature_flags.default_all`
- [LoggerManager](logger-manager.md) — evaluations logged at DEBUG
- [ErrorHandlingManager](error-handling-manager.md) — exception classification during reload
