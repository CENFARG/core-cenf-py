---
sidebar_position: 14
---

# DynamicPromptingManager (M14)

Conditional system prompt assembly using dict-based condition matching. `PromptBlock` models represent content blocks with optional conditions and priority ordering. Blocks are sorted by priority (ascending) and concatenated into the final prompt. MVP uses dict equality; CEL integration is planned for a future release.

## Protocol

`DynamicPromptingManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.dynamic_prompting.ports`.

### `async assemble(base_prompt, blocks, context_state) → str`

Evaluate each block's condition against `context_state` and concatenate matching blocks. Sorts blocks by priority (ascending) before evaluation. The `base_prompt` is always prepended at the start.

```python
async def assemble(
    self,
    base_prompt: str | None,
    blocks: list[PromptBlock],
    context_state: dict[str, Any],
) -> str: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `base_prompt` | `str \| None` | Foundational system prompt, prepended first (or empty if `None`) |
| `blocks` | `list[PromptBlock]` | Conditional blocks to evaluate |
| `context_state` | `dict[str, Any]` | Runtime state dict used for condition matching |

**Returns:** The assembled prompt string.

**Condition matching rules:**
- `condition=None` → block always injected
- Empty dict `{}` → matches vacuously (always injected)
- Non-empty dict → ALL `key:value` pairs must match in `context_state`
- Dot-notation keys (e.g., `"user.role"`) resolved via nested dict traversal
- Never uses `eval()` or `exec()` — pure dict value comparison

---

### `validate_blocks(blocks) → list[str]`

Validate a list of `PromptBlock` entries. Checks for duplicate IDs, invalid priority values, and structural issues. Returns an empty list if all blocks are valid.

```python
def validate_blocks(self, blocks: list[PromptBlock]) -> list[str]: ...
```

---

### `get_json_schema() → dict[str, Any]` *(static)*

Return JSON Schema for agent discovery (AX).

```python
@staticmethod
def get_json_schema() -> dict[str, Any]: ...
```

---

## Models

**File:** `core_infrastructure.dynamic_prompting.ports` (PromptBlock), `core_infrastructure.dynamic_prompting.models` (PromptConfig)

### `PromptBlock`

Frozen Pydantic model (`extra="forbid"`).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` (≥1) | required | Unique identifier for the cognitive block |
| `condition` | `dict[str, Any] \| None` | `None` | Dict of key:value pairs. `None` = always injected. Non-empty = ALL must match |
| `content` | `str` (≥1) | required | Prompt text to inject if condition matches |
| `priority` | `int` (0–100) | `10` | Injection order (lower = first) |

### `PromptConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `source` | `"yaml" \| "dict"` | `"dict"` | Source of prompt block definitions |
| `file_path` | `str \| None` | `None` | Path to YAML file when `source="yaml"` |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `ConditionalPromptAdapter` | In-memory dict matching | Production — pure dict condition evaluation, no CEL required |

**MVP limitation:** Only one concrete adapter exists. CEL integration (`pycel`) is planned for a future release with richer condition expressions. The `ConditionalPromptAdapter` reads `PromptConfig` from ConfigManager and uses pure Python dict traversal for dot-notation keys.

---

## Usage Example

```python
from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import (
    ConditionalPromptAdapter,
)
from core_infrastructure.dynamic_prompting.ports import PromptBlock

prompt_assembler = ConditionalPromptAdapter(config, logger, error_handler)

# Define conditional blocks
blocks = [
    PromptBlock(id="persona", condition=None,
                content="You are a document processing assistant.", priority=1),
    PromptBlock(id="pdf-mode",
                condition={"document.format": "pdf"},
                content="Use the PDF extraction pipeline for text analysis.", priority=10),
    PromptBlock(id="image-mode",
                condition={"document.format": "image"},
                content="Use the OCR pipeline for image-to-text conversion.", priority=10),
    PromptBlock(id="admin-instructions",
                condition={"user.role": "admin"},
                content="You have full access to all documents and metadata.", priority=20),
    PromptBlock(id="rate-limit-warning",
                condition={"system.under_load": True},
                content="WARNING: System under high load. Prioritize critical documents.",
                priority=5),
]

# Validate blocks
errors = prompt_assembler.validate_blocks(blocks)
assert len(errors) == 0  # All valid

# Assemble for a PDF document, admin user
context = {
    "document": {"format": "pdf", "page_count": 42},
    "user": {"role": "admin", "name": "Alice"},
    "system": {"under_load": False},
}
prompt = await prompt_assembler.assemble(
    base_prompt="You are a helpful assistant.",
    blocks=blocks,
    context_state=context,
)
# Result includes: persona (always), pdf-mode (condition matched),
# admin-instructions (dot-notation: user.role == "admin")
# Excludes: image-mode (document.format != "image"),
# rate-limit-warning (system.under_load != True)

# Assemble for an image document, non-admin user
context_img = {
    "document": {"format": "image"},
    "user": {"role": "viewer"},
    "system": {"under_load": False},
}
prompt_img = await prompt_assembler.assemble(
    base_prompt="You are a helpful assistant.",
    blocks=blocks,
    context_state=context_img,
)
# Includes: persona, image-mode
# Excludes: pdf-mode, admin-instructions, rate-limit-warning
assert "full access" not in prompt_img
```

---

## @ai-directive

> **Conditions are dict-based equality — no CEL parser needed for MVP.** Condition matching is dict-based for MVP — CEL is future. Never use `eval()` or `exec()` for condition evaluation. Empty condition dict `{}` matches vacuously. Dot-notation keys are resolved via nested dict traversal. `validate_blocks()` is synchronous — no I/O required.

## Related

- [ConfigManager](config-manager.md) — supplies `dynamic_prompting` config section
- [LoggerManager](logger-manager.md) — block injection decisions logged at DEBUG
- [ErrorHandlingManager](error-handling-manager.md) — assembly errors classified
