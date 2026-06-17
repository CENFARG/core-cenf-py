"""DynamicPromptingManager Protocol — conditional system prompt assembly.

Defines the contract for assembling system prompts condititionally based
on runtime state. PromptBlock models represent content blocks with optional
dict-based conditions and priority ordering.

Security: Never use eval() or exec() for condition evaluation. Always use
    dict-based matching (MVP) or sandboxed CEL evaluation.
Observability: All assemble() calls emit RED metrics under cenf.prompting.*.
@ai-directive: Condition matching is dict-based for MVP — CEL is future.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class PromptBlock(BaseModel):
    """A cognitive content block for conditional prompt assembly.

    Represents a block of prompt content that may be conditionally
    injected into the final system prompt based on runtime context_state.

    Attributes:
        id: Unique identifier for the block.
        condition: Optional dict of key:value pairs. If None, always included.
            If dict, ALL key:value pairs must match in context_state.
            Keys support dot-notation (e.g., ``"session.intent"``).
        content: The prompt text to inject if the condition matches.
        priority: Injection order (lower = first). Range 0-100, default 10.
    """

    model_config = {"extra": "forbid", "frozen": True}

    id: str = Field(..., min_length=1, description="Unique identifier for the cognitive block.")
    condition: dict[str, Any] | None = Field(
        None, description="Dict of key:value pairs for condition matching. If None, always injected."
    )
    content: str = Field(..., min_length=1, description="Content to inject into the prompt if condition is true.")
    priority: int = Field(default=10, description="Injection order. Lower priority inserts first.")


@runtime_checkable
class DynamicPromptingManager(Protocol):
    """Conditional prompt assembly contract with dict-based condition matching.

    Provides deterministic, conditional assembly of system prompts by
    evaluating PromptBlock conditions against runtime context_state.
    Blocks are sorted by priority (ascending) and concatenated.

    Rules:
        - Condition matching is dict-based: all key:value pairs must match.
        - Dot-notation keys are resolved via nested dict traversal.
        - Empty condition dict (``{}``) matches vacuously.
        - Never use eval() or exec() for condition evaluation.
        - validate_blocks() is synchronous — no I/O required.
    """

    async def assemble(
        self,
        base_prompt: str | None,
        blocks: list[PromptBlock],
        context_state: dict[str, Any],
    ) -> str:
        """Evaluate each block.condition against context_state and concatenate.

        Sorts blocks by priority (ascending) before evaluation. Each block
        whose condition matches (or is None) has its content appended to
        the result. The base_prompt is always prepended at the start.

        Args:
            base_prompt: The foundational system prompt (or None for empty).
            blocks: List of PromptBlock entries to evaluate.
            context_state: Runtime state dict used for condition matching.

        Returns:
            str: The assembled prompt string.
        """
        ...

    def validate_blocks(self, blocks: list[PromptBlock]) -> list[str]:
        """Validate a list of PromptBlock entries and return error messages.

        Checks for duplicate IDs, invalid priority values, and other
        structural issues. Returns an empty list if all blocks are valid.

        Args:
            blocks: List of PromptBlock entries to validate.

        Returns:
            list[str]: Error messages encountered (empty if valid).
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: A valid JSON Schema object describing the
                PromptBlock model.
        """
        ...
