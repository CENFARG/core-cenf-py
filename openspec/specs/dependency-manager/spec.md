---
Spec_ID: SPEC_M13
Title: DependencyManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [dependency, importlib, lazy-resolution, allowlist, docker]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M13: DependencyManager

## Purpose

Provide lazy, validated dependency resolution via importlib. Allows programs to register catalogs of dependencies (plugins, providers, adapters) and resolve them at runtime without loading the full import tree at startup. Compatible with Docker deployment via `get_required_packages()`.

**Does NOT**: Accept module_path from direct user input without allowlist, include framework-specific knowledge, eagerly import dependencies at startup, expose cached instances without hot-reload guarantees.

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class DependencyManager(Protocol):
    """@ai-directive: module_path must come from a registry allowlisted; never from direct user input."""

    def resolve_class(self, module_path: str, class_name: str) -> type:
        """Import module_path (lazy) and return class_name. Cached."""
        ...

    def register(self, namespace: str, key: str, target: tuple[str, str] | Any) -> None:
        """Register a catalog entry injected by the consuming program."""
        ...

    def is_known(self, namespace: str, key: str) -> bool:
        """Check if a dependency is registered."""
        ...

    def list_keys(self, namespace: str) -> list[str]:
        """List all keys in a namespace."""
        ...

    async def invalidate_cache(self) -> None:
        """Invalidate the cache (invoke on catalog hot-reload)."""
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery."""
        ...

    def get_required_packages(self) -> list[str]:
        """Return list of runtime package names for Dockerfile/pyproject.toml."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class DependencySettings(BaseModel):
    allowlist_paths: list[str] = Field(default_factory=list, description="Allowed module path prefixes")
    cache_max_size: int = Field(default=256, ge=16)
    entry_points_enabled: bool = Field(default=True)

class DependencyCatalog(BaseModel):
    namespace: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=128)
    module_path: str = Field(min_length=1)
    class_name: str = Field(min_length=1, max_length=128)
```

## Gherkin Scenarios

### Scenario: Lazy class resolution

- GIVEN namespace="models" with key="gpt4" registered as `("openai.models", "GPT4Model")`
- WHEN `resolve_class("openai.models", "GPT4Model")` is called
- THEN it imports `openai.models` lazily
- AND returns the `GPT4Model` class
- AND subsequent calls return the cached class

### Scenario: Allowlist validation prevents path traversal

- GIVEN allowlist contains `["openai.", "anthropic."]`
- WHEN `resolve_class("os", "system")` is called
- THEN it raises `ValidationError` (module not in allowlist)

### Scenario: Unknown dependency returns False

- WHEN `is_known("models", "unknown_model")` is called
- THEN it returns `False`

### Scenario: Get required packages for Docker

- WHEN `get_required_packages()` is called
- THEN it returns a list like `["openai>=1.0", "anthropic>=0.5"]`
- AND the list can be used in Dockerfile `pip install` commands

### Scenario: Cache invalidation on hot-reload

- GIVEN a class is resolved and cached
- WHEN `invalidate_cache()` is called
- THEN the next `resolve_class()` re-imports the module
- AND the new class version is returned

### Scenario: Entry points discovery

- GIVEN a third-party package registers an entry point `cenf.models`
- WHEN the DependencyManager starts
- THEN it discovers and registers the entry point
- AND `is_known()` returns True for the entry point key

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Module not in allowlist | VALIDATION | Re-raise immediately |
| Module not found | PERMANENT | Re-raise with details |
| Class not found in module | PERMANENT | Re-raise with details |
| Import error | PERMANENT | Re-raise with details |

## RED Metrics

- `cenf.dependency.resolve_total` (counter)
- `cenf.dependency.errors_total` (counter)
- `cenf.dependency.resolve_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryDependencyAdapter` — dict-based catalog, no imports.
- **Integration**: `ImportlibAdapter` with real module imports and allowlist validation.
- **E2E**: Docker package list generation, verify all lazy dependencies are declared.

## Do's and Don'ts

**Do**:
- Resolve classes lazily via `importlib.import_module` (only import when referenced)
- Validate all module_path against declarative allowlist before importing
- Cache resolved class instances (lru_cache or equivalent)
- Support extension via entry_points (importlib.metadata)
- Remain framework-agnostic — catalogs are injected by consuming programs
- Expose `get_required_packages()` for Docker deployment

**Don't**:
- Accept module_path derived from direct user input without allowlist
- Include knowledge of a specific framework inside the manager
- Eagerly import dependencies at module startup
- Expose cached instances without hot-reload invalidation guarantees
