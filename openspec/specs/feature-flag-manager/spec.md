---
Spec_ID: SPEC_M12
Title: FeatureFlagManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [feature-flags, yaml, watchfiles, unleash]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M12: FeatureFlagManager

## Purpose

Provide runtime feature flag evaluation with 2-phase strategy. Phase 1 (MVP): FileFeatureFlagAdapter with YAML + watchfiles hot-reload. Phase 2: UnleashFeatureFlagAdapter with same Protocol, zero code changes in domain.

**Does NOT**: Send PII to external providers, use for business-critical logic requiring transactional consistency, crash on evaluation failure.

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

from core_infrastructure.feature_flags.models import FlagContext

@runtime_checkable
class FeatureFlagManager(Protocol):
    """@ai-directive: is_enabled() MUST return False for unknown flags — never throw."""

    def is_enabled(self, flag_key: str, context: FlagContext | None = None) -> bool:
        """Check if a feature flag is enabled. Returns False for unknown flags."""
        ...

    def get_flag_value(self, flag_key: str, context: FlagContext | None = None, default: Any = None) -> Any:
        """Get the value (payload) of a feature flag. Returns default on cache miss."""
        ...

    def get_all_flags(self, context: FlagContext | None = None) -> dict[str, bool]:
        """Get the enabled state of all feature flags."""
        ...

    async def refresh(self) -> None:
        """Refresh the local flag cache from the provider."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class FeatureFlagSettings(BaseModel):
    backend: Literal["file", "unleash"] = Field(default="file")
    yaml_path: str | None = Field(default=None)
    unleash_url: str | None = Field(default=None)
    unleash_api_token: str | None = Field(default=None, min_length=1)
    app_name: str = Field(min_length=1, max_length=128, default="cenf-core")
    environment: str = Field(min_length=1, max_length=64, default="development")
    refresh_interval_seconds: int = Field(default=10, ge=5, le=300)
    streaming_enabled: bool = Field(default=True)
    fallback_enabled: bool = Field(default=True)

class FlagContext(BaseModel):
    user_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    environment: str = Field(min_length=1, max_length=64)
    custom_properties: dict[str, str] = Field(default_factory=dict)
```

## Gherkin Scenarios

### Scenario: Flag enabled

- GIVEN YAML contains `{"dark_mode": {"enabled": true}}`
- WHEN `is_enabled("dark_mode")` is called
- THEN it returns `True`

### Scenario: Unknown flag returns False (fail-safe)

- WHEN `is_enabled("nonexistent_flag")` is called
- THEN it returns `False` (no exception)

### Scenario: Context-based evaluation

- GIVEN flag "beta_feature" has rule: `environment == "staging"`
- WHEN `is_enabled("beta_feature", context=FlagContext(environment="staging"))` is called
- THEN it returns `True`
- AND `is_enabled("beta_feature", context=FlagContext(environment="prod"))` returns `False`

### Scenario: Hot-reload via watchfiles

- GIVEN flags are loaded from YAML
- WHEN the YAML file is modified on disk
- THEN watchfiles detects the change
- AND flags are reloaded automatically
- AND `is_enabled()` reflects the new values

### Scenario: Get flag value with default

- GIVEN flag "theme" has value "dark"
- WHEN `get_flag_value("theme", default="light")` is called
- THEN it returns `"dark"`
- AND `get_flag_value("missing_flag", default="light")` returns `"light"`

### Scenario: PII safety

- GIVEN FlagContext with user_id="user-123"
- WHEN flags are evaluated with Unleash backend
- THEN user_id is hashed before sending to external provider
- AND no raw PII is transmitted

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Unleash API unreachable | TRANSIENT | Use cached flags, retry |
| URL misconfiguration | PERMANENT | Fail bootstrap |
| Invalid token | AUTH | Log, use cached flags |
| Unknown flag | — | Return False (not an error) |

## RED Metrics

- `cenf.feature_flags.evaluated_total` (counter)
- `cenf.feature_flags.errors_total` (counter)
- `cenf.feature_flags.eval_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryFeatureFlagAdapter` — dict of flags with context evaluation.
- **Integration**: `FileFeatureFlagAdapter` with temp YAML files and watchfiles.
- **E2E**: Verify no PII in outgoing requests (Unleash phase 2).

## Do's and Don'ts

**Do**:
- Implement FileFeatureFlagAdapter with YAML + watchfiles hot-reload
- Cache locally for fast evaluation (<1ms)
- Return False for unknown flags (fail-safe, never crash)
- Hash user_id for PII safety when sending to external providers

**Don't**:
- Send PII to external providers
- Use for business-critical logic requiring transactional consistency
- Crash on evaluation failure — always return a safe default
