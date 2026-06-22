---
sidebar_position: 13
---

# DependencyManager (M13)

Lazy dependency resolution with allowlist security. Uses `importlib` for dynamic class loading — validates `module_path` against a configured allowlist BEFORE importing. Provides `get_required_packages()` for Docker and `pyproject.toml` generation. Catalog entries are injected by consuming programs; the manager itself is framework-agnostic.

## Protocol

`DependencyManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.dependency.ports`.

### `resolve_class(module_path, class_name) → type`

Import module_path lazily and return class_name. Validates against allowlist BEFORE importing. Results are cached — subsequent calls return the cached type.

```python
def resolve_class(self, module_path: str, class_name: str) -> type: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `module_path` | `str` | Fully qualified Python module path (e.g., `"openai.models"`) |
| `class_name` | `str` | Target class name within the module |

**Raises:** `ValidationError` if `module_path` is not in the allowlist (strict mode). `ModuleNotFoundError` if the module cannot be imported. `AttributeError` if `class_name` is not found.

---

### `register(namespace, key, target) → None`

Register a catalog entry injected by the consuming program.

```python
def register(self, namespace: str, key: str, target: tuple[str, str] | Any) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `namespace` | `str` | Logical grouping (e.g., `"models"`, `"agents"`) |
| `key` | `str` | Unique key within the namespace |
| `target` | `tuple[str, str] \| Any` | Either `(module_path, class_name)` for lazy resolution, or a direct object |

---

### `is_known(namespace, key) → bool`

Check if a dependency is registered. Synchronous and cheap — does not trigger any import.

```python
def is_known(self, namespace: str, key: str) -> bool: ...
```

---

### `list_keys(namespace) → list[str]`

List all keys registered under a namespace.

```python
def list_keys(self, namespace: str) -> list[str]: ...
```

---

### `async invalidate_cache() → None`

Invalidate the resolution cache for hot-reload scenarios. Forces re-import on next `resolve_class()`.

```python
async def invalidate_cache(self) -> None: ...
```

---

### `get_required_packages() → list[str]`

Return list of runtime package names for `Dockerfile` / `pyproject.toml`. Aggregates all `packages` fields from registered `RegistryEntry` objects plus `default_packages` from `DependencyConfig`. No duplicates.

```python
def get_required_packages(self) -> list[str]: ...
```

**Returns:** Package specs like `["openai>=1.0", "anthropic>=0.5"]`.

---

### `get_json_schema() → dict[str, Any]` *(static)*

Return JSON Schema for agent discovery (AX).

```python
@staticmethod
def get_json_schema() -> dict[str, Any]: ...
```

---

## Models

**File:** `core_infrastructure.dependency.models`

### `RegistryEntry`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `module_path` | `str` (≥1) | required | Fully qualified Python module path |
| `class_name` | `str` (1–128) | required | Target class name within the module |
| `packages` | `list[str]` | `[]` | pip package specs required at runtime |
| `metadata` | `dict[str, Any]` | `{}` | Arbitrary key-value metadata |

### `DependencyConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `allowlist_mode` | `"strict" \| "permissive"` | `"strict"` | Strict: only registered paths allowed. Permissive: unregistered paths allowed with warning |
| `default_packages` | `list[str]` | `[]` | Packages always included in `get_required_packages()` |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `ImportlibDependencyAdapter` | `importlib` + allowlist | Production — lazy resolution with prefix-matched allowlist validation |
| `InMemoryDependencyAdapter` | In-memory dict mapping | Testing — preload `(module_path, class_name) → object` mappings |

**Security:** `ImportlibDependencyAdapter` validates `module_path` against configured `allowlist_paths` BEFORE calling `importlib.import_module()`. In strict mode, the path must start with an allowlisted prefix. `InMemoryDependencyAdapter` resolves via a pre-loaded mapping dict — no `importlib` calls.

---

## Usage Example

```python
from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import (
    InMemoryDependencyAdapter,
)

# Pre-load an explicit mapping
class PdfParser:
    def __init__(self):
        self.name = "PdfParser v1.0"

    def parse(self, content: bytes) -> str:
        return f"Parsed {len(content)} bytes"

parser_instance = PdfParser()
dep_mgr = InMemoryDependencyAdapter(
    mapping={("parsers.pdf", "PdfParser"): parser_instance}
)

# Register a catalog entry for lazy resolution
dep_mgr.register("parsers", "ocr_parser",
                 target=("parsers.ocr", "TesseractParser"))

# Check if registered
dep_mgr.is_known("parsers", "ocr_parser")  # → True
dep_mgr.is_known("parsers", "pdf_parser")  # → False

# List keys
dep_mgr.list_keys("parsers")  # → ["ocr_parser"]

# Resolve a class
resolved = dep_mgr.resolve_class("parsers.pdf", "PdfParser")
assert resolved is parser_instance
result = resolved.parse(b"demo content")
# → "Parsed 12 bytes"

# Production: ImportlibDependencyAdapter with allowlist
from core_infrastructure.dependency.adapters.importlib_dependency_adapter import (
    ImportlibDependencyAdapter,
)
prod_dep = ImportlibDependencyAdapter(config, logger, error_handler)
prod_dep.register("models", "gpt4", ("openai.models", "GPT4Model"))
cls = prod_dep.resolve_class("openai.models", "GPT4Model")

# Generate Docker requirements
packages = prod_dep.get_required_packages()
# → ["openai>=1.0"]
```

---

## @ai-directive

> **Never pass `module_path` from user input. Always validate against allowlist.** `module_path` must come from an allowlisted registry — never from direct user input. Allowlist paths are prefix-matched — registering `"openai."` allows any submodule under `"openai"`. `resolve_class()` validates BEFORE importing. In strict mode, unregistered paths raise `ValidationError`.

## Related

- [ConfigManager](config-manager.md) — supplies `dependency.allowlist_paths` and `dependency.allowlist_mode`
- [LoggerManager](logger-manager.md) — resolution events logged at INFO
- [ErrorHandlingManager](error-handling-manager.md) — classifies import errors
