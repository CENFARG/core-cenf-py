---
Spec_ID: SPEC_M14
Title: DynamicPromptingManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [prompting, cel, agno, conditional-assembly]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M14: DynamicPromptingManager

## Purpose

Provide conditional, deterministic assembly of system prompts and context blocks using CEL (Common Expression Language). Avoids monolithic mega-prompts by injecting only relevant blocks based on runtime state.

**Does NOT**: Use eval() or exec() (critical injection vector), perform I/O during evaluation, couple to business-specific prompts.

> **NOTE**: This manager is SPEC ONLY — do not implement yet. The Protocol and models are defined for future implementation.

## Python Protocol

```python
from __future__ import annotations
from typing import Any, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, Field

class PromptBlock(BaseModel):
    model_config = {"extra": "forbid", "frozen": True}

    id: str = Field(..., description="Unique identifier for the cognitive block.")
    condition: str | None = Field(None, description="CEL expression for evaluation. If None, always injected.")
    content: str = Field(..., description="Content to inject into the prompt if condition is true.")
    priority: int = Field(default=10, description="Injection order. Lower priority inserts first.")

@runtime_checkable
class DynamicPromptingManager(Protocol):
    """@ai-directive: Must use sandboxed CEL evaluation (pycel). Never use eval() or exec()."""

    async def assemble(self, base_prompt: str | None, blocks: Sequence[PromptBlock], context_state: dict[str, Any]) -> str:
        """Evaluate each block.condition against context_state. Sort by priority and concatenate."""
        ...

    def validate_expressions(self, blocks: Sequence[PromptBlock]) -> list[str]:
        """AOT-compile CEL expressions. Return list of syntax errors (empty if valid)."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class PromptAssemblySettings(BaseModel):
    max_blocks: int = Field(default=50, ge=1, le=200)
    cel_timeout_ms: int = Field(default=100, ge=10, le=1000)
    cache_enabled: bool = Field(default=True)
    cache_ttl_seconds: int = Field(default=300, ge=60, le=3600)
```

## Gherkin Scenarios

### Scenario: Assemble with unconditional blocks

- GIVEN base_prompt = "You are a helpful assistant."
- GIVEN blocks = [PromptBlock(id="greeting", condition=None, content="Always be polite.", priority=5)]
- WHEN `assemble(base_prompt, blocks, {})` is called
- THEN it returns "You are a helpful assistant.\nAlways be polite."

### Scenario: Assemble with conditional blocks

- GIVEN blocks with condition: `session_state.intent == "refund"`
- WHEN context_state = `{"session_state": {"intent": "refund"}}`
- THEN the block is injected
- AND when context_state = `{"session_state": {"intent": "purchase"}}`
- THEN the block is NOT injected

### Scenario: Priority ordering

- GIVEN blocks with priorities [20, 5, 10]
- WHEN `assemble()` is called
- THEN blocks are concatenated in order: priority 5, then 10, then 20

### Scenario: AOT validation catches syntax errors

- GIVEN a block with condition: `session_state.intent == ` (incomplete CEL)
- WHEN `validate_expressions([block])` is called
- THEN it returns a list with at least one error string
- AND the error describes the syntax issue

### Scenario: No eval() or exec() used

- GIVEN any PromptBlock with a CEL condition
- WHEN `assemble()` is called
- THEN the implementation MUST NOT use Python's eval() or exec()
- AND it MUST use pycel or equivalent sandboxed evaluator

### Scenario: No I/O during evaluation

- GIVEN a block with condition referencing a database value
- WHEN `assemble()` is called
- THEN the evaluation uses ONLY the provided context_state
- AND no database, HTTP, or file I/O is performed

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Invalid CEL syntax | VALIDATION | Return from validate_expressions() |
| CEL evaluation timeout | TRANSIENT | Log, skip block, continue assembly |
| Max blocks exceeded | VALIDATION | Re-raise immediately |
| pycel not installed | PERMANENT | Fail bootstrap |

## RED Metrics

- `cenf.prompting.assemble_total` (counter)
- `cenf.prompting.errors_total` (counter)
- `cenf.prompting.assemble_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryPromptingAdapter` — evaluates conditions without pycel for testing.
- **Integration**: `CELPromptingAdapter` with pycel sandboxed evaluator.
- **E2E**: Verify no eval()/exec() usage via code analysis.

## Do's and Don'ts

**Do**:
- Use pycel (Apache 2.0) for sandboxed CEL evaluation
- Sort blocks by priority before concatenation
- Compile CEL expressions AOT during bootstrap (fail-fast)
- Emit observability traces showing which blocks were injected

**Don't**:
- Use eval() or exec() under any circumstances (critical injection vector)
- Perform I/O (database, HTTP) during evaluation
- Couple the structure to business-specific prompts
- Allow unbounded block counts (enforce max_blocks)
