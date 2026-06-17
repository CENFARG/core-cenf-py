"""ConditionalPromptAdapter — dict-based conditional prompt assembly.

Implements DynamicPromptingManager with simple dict-based condition
matching. No external CEL evaluator required for MVP. Conditions are
simple equality checks with dot-notation key traversal.

Security: Never uses eval() or exec() — all condition matching is
    pure dict value comparison. No I/O during assemble().
Observability: All assemble() calls log block injection decisions at DEBUG.
@ai-directive: MVP uses dict conditions only. CEL integration (pycel)
    is planned for a future release.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.dynamic_prompting.models import PromptConfig
from core_infrastructure.dynamic_prompting.ports import PromptBlock
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.logger.ports import LoggerManager


class ConditionalPromptAdapter:
    """Conditional prompt assembler using dict-based condition matching.

    Evaluates PromptBlock conditions against runtime context_state using
    simple dict value equality. Supports dot-notation keys for nested
    dict traversal. Blocks are sorted by priority before concatenation.

    Args:
        config: ConfigManager for PromptConfig reading.
        logger: LoggerManager for structured log emission.
        error_handler: ErrorHandlingManager for exception classification.

    Usage::

        adapter = ConditionalPromptAdapter(config, logger, error_handler)
        blocks = [PromptBlock(id="greet", condition=None, content="Be polite.")]
        result = await adapter.assemble("You are helpful.", blocks, {})
    """

    def __init__(
        self,
        config: ConfigManager,
        logger: LoggerManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._logger = logger
        self._error_handler = error_handler

        section = config.get_section("dynamic_prompting")
        self._prompt_config = PromptConfig(**section) if section else PromptConfig()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_dot_notation(d: dict[str, Any], key_path: str) -> Any:
        """Resolve a dot-notation key path in a nested dict.

        Splits ``key_path`` on ``"."`` and traverses the dict
        hierarchy. Returns ``None`` if any intermediate key is missing.

        Args:
            d: The root dict to traverse.
            key_path: Dot-separated key path (e.g., ``"session.intent"``).

        Returns:
            Any: The value at the resolved path, or ``None`` if missing.
        """
        parts = key_path.split(".")
        current: Any = d
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def _condition_matches(condition: dict[str, Any], context_state: dict[str, Any]) -> bool:
        """Check if ALL key:value pairs in condition match context_state.

        Each key in ``condition`` is resolved via dot-notation in
        ``context_state`` and compared by equality.

        Args:
            condition: Dict of expected key:value pairs.
            context_state: Runtime state dict to match against.

        Returns:
            bool: True if all key:value pairs match (vacuously true for empty condition).
        """
        for key, expected_value in condition.items():
            actual = ConditionalPromptAdapter._resolve_dot_notation(context_state, key)
            if actual != expected_value:
                return False
        return True

    # ------------------------------------------------------------------
    # Public API — DynamicPromptingManager Protocol
    # ------------------------------------------------------------------

    async def assemble(
        self,
        base_prompt: str | None,
        blocks: list[PromptBlock],
        context_state: dict[str, Any],
    ) -> str:
        """Assemble a system prompt from a base prompt and conditional blocks.

        Sorts blocks by priority (ascending), evaluates each block's
        condition against context_state, and concatenates matching blocks.
        The base_prompt is always prepended.

        Args:
            base_prompt: The foundational system prompt (or None for empty).
            blocks: List of PromptBlock entries to evaluate.
            context_state: Runtime state dict for condition matching.

        Returns:
            str: The assembled prompt string.
        """
        sorted_blocks = sorted(blocks, key=lambda b: b.priority)

        parts: list[str] = []
        if base_prompt is not None:
            parts.append(base_prompt)

        for block in sorted_blocks:
            if block.condition is None:
                self._logger.debug("Injecting unconditional block", block_id=block.id)
                parts.append(block.content)
                continue

            if self._condition_matches(block.condition, context_state):
                self._logger.debug("Condition matched", block_id=block.id, condition=block.condition)
                parts.append(block.content)
            else:
                self._logger.debug("Condition skipped", block_id=block.id, condition=block.condition)

        return "\n\n".join(parts)

    def validate_blocks(self, blocks: list[PromptBlock]) -> list[str]:
        """Validate a list of PromptBlock entries and return error messages.

        Checks for:
        - Duplicate block IDs
        - Priority values outside the 0-100 range

        Args:
            blocks: List of PromptBlock entries to validate.

        Returns:
            list[str]: Error messages (empty if valid).
        """
        errors: list[str] = []

        seen_ids: set[str] = set()
        for block in blocks:
            if block.id in seen_ids:
                errors.append(f"Duplicate block ID: {block.id}")
            seen_ids.add(block.id)

            if block.priority < 0 or block.priority > 100:
                errors.append(
                    f"Invalid priority {block.priority} for block '{block.id}': must be 0-100."
                )

        return errors

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: JSON Schema describing PromptConfig model.
        """
        return PromptConfig.model_json_schema()
