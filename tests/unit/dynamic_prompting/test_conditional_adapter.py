"""Unit tests for ConditionalPromptAdapter — DynamicPromptingManager implementation.

Tests cover:
- assemble() with base_prompt only (no blocks)
- assemble() with unconditional blocks (condition=None)
- assemble() with conditional blocks that match
- assemble() with conditional blocks that don't match
- assemble() priority ordering (lower number = first)
- assemble() dot-notation context keys (e.g., "session.intent")
- validate_blocks() error detection

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import (
    ConditionalPromptAdapter,
)
from core_infrastructure.dynamic_prompting.ports import DynamicPromptingManager, PromptBlock


@pytest.fixture
def config_manager() -> MagicMock:
    """Mock ConfigManager that returns a section dict."""
    mock = MagicMock()
    mock.get_section.return_value = {}
    return mock


@pytest.fixture
def logger_manager() -> MagicMock:
    """Mock LoggerManager for capturing log calls."""
    return MagicMock()


@pytest.fixture
def error_manager() -> MagicMock:
    """Mock ErrorHandlingManager."""
    return MagicMock()


@pytest.fixture
def adapter(
    config_manager: MagicMock,
    logger_manager: MagicMock,
    error_manager: MagicMock,
) -> ConditionalPromptAdapter:
    """Create a ConditionalPromptAdapter with mocked dependencies."""
    return ConditionalPromptAdapter(
        config=config_manager,
        logger=logger_manager,
        error_handler=error_manager,
    )


class TestConditionalPromptAdapterProtocol:
    """Verify ConditionalPromptAdapter satisfies DynamicPromptingManager Protocol."""

    def test_satisfies_protocol(self, adapter: ConditionalPromptAdapter) -> None:
        """Adapter passes isinstance check."""
        assert isinstance(adapter, DynamicPromptingManager)

    def test_has_all_required_methods(self, adapter: ConditionalPromptAdapter) -> None:
        """Adapter exposes assemble, validate_blocks, get_json_schema."""
        assert callable(adapter.assemble)
        assert callable(adapter.validate_blocks)
        assert callable(adapter.get_json_schema)


class TestAssemble:
    """Verify assemble() method behavior."""

    @pytest.mark.asyncio
    async def test_base_prompt_only_no_blocks(self, adapter: ConditionalPromptAdapter) -> None:
        """When blocks list is empty, only base_prompt is returned."""
        result = await adapter.assemble("You are helpful.", [], {})
        assert result == "You are helpful."

    @pytest.mark.asyncio
    async def test_base_prompt_none_no_blocks(self, adapter: ConditionalPromptAdapter) -> None:
        """When base_prompt is None and no blocks, returns empty string."""
        result = await adapter.assemble(None, [], {})
        assert result == ""

    @pytest.mark.asyncio
    async def test_unconditional_block_included(self, adapter: ConditionalPromptAdapter) -> None:
        """A block with condition=None is always included."""
        blocks = [
            PromptBlock(id="greeting", condition=None, content="Always be polite.", priority=5),
        ]
        result = await adapter.assemble("You are helpful.", blocks, {})
        assert result == "You are helpful.\n\nAlways be polite."

    @pytest.mark.asyncio
    async def test_conditional_block_matches(self, adapter: ConditionalPromptAdapter) -> None:
        """When dict condition matches context_state, the block is included."""
        blocks = [
            PromptBlock(
                id="refund",
                condition={"session_state.intent": "refund"},
                content="Handle refunds carefully.",
                priority=10,
            ),
        ]
        ctx = {"session_state": {"intent": "refund"}}
        result = await adapter.assemble("Base.", blocks, ctx)
        assert result == "Base.\n\nHandle refunds carefully."

    @pytest.mark.asyncio
    async def test_conditional_block_no_match(self, adapter: ConditionalPromptAdapter) -> None:
        """When dict condition does NOT match context_state, the block is skipped."""
        blocks = [
            PromptBlock(
                id="refund",
                condition={"session_state.intent": "refund"},
                content="Handle refunds.",
                priority=10,
            ),
        ]
        ctx = {"session_state": {"intent": "purchase"}}
        result = await adapter.assemble("Base.", blocks, ctx)
        assert result == "Base."

    @pytest.mark.asyncio
    async def test_multiple_condition_keys_all_must_match(self, adapter: ConditionalPromptAdapter) -> None:
        """ALL key:value pairs in the condition must match for the block to be included."""
        blocks = [
            PromptBlock(
                id="debug_refund",
                condition={"session_state.intent": "refund", "session_state.debug": True},
                content="Debug refund.",
                priority=10,
            ),
        ]
        # Match both
        ctx1 = {"session_state": {"intent": "refund", "debug": True}}
        result1 = await adapter.assemble("Base.", blocks, ctx1)
        assert "Debug refund." in result1

        # Match only one
        ctx2 = {"session_state": {"intent": "refund", "debug": False}}
        result2 = await adapter.assemble("Base.", blocks, ctx2)
        assert "Debug refund." not in result2

    @pytest.mark.asyncio
    async def test_priority_ordering(self, adapter: ConditionalPromptAdapter) -> None:
        """Blocks are assembled in ascending priority order (lower = first)."""
        blocks = [
            PromptBlock(id="third", condition=None, content="Third", priority=30),
            PromptBlock(id="first", condition=None, content="First", priority=10),
            PromptBlock(id="second", condition=None, content="Second", priority=20),
        ]
        result = await adapter.assemble("Base.", blocks, {})
        assert result == "Base.\n\nFirst\n\nSecond\n\nThird"

    @pytest.mark.asyncio
    async def test_dot_notation_context_keys(self, adapter: ConditionalPromptAdapter) -> None:
        """Condition keys with dot notation (e.g., "session.intent") are resolved via dict traversal."""
        blocks = [
            PromptBlock(
                id="dot_test",
                condition={"session.intent": "debug"},
                content="Debug mode active.",
                priority=5,
            ),
        ]
        ctx = {"session": {"intent": "debug"}}
        result = await adapter.assemble("Base.", blocks, ctx)
        assert "Debug mode active." in result

    @pytest.mark.asyncio
    async def test_dot_notation_missing_key(self, adapter: ConditionalPromptAdapter) -> None:
        """When dot notation key path does not exist, condition does not match."""
        blocks = [
            PromptBlock(
                id="dot_missing",
                condition={"session.intent": "debug"},
                content="Debug mode.",
                priority=5,
            ),
        ]
        ctx = {"other": {"intent": "debug"}}
        result = await adapter.assemble("Base.", blocks, ctx)
        assert "Debug mode." not in result

    @pytest.mark.asyncio
    async def test_empty_condition_dict(self, adapter: ConditionalPromptAdapter) -> None:
        """An empty dict condition is treated as match (vacuously true)."""
        blocks = [
            PromptBlock(id="empty_cond", condition={}, content="Always included.", priority=5),
        ]
        result = await adapter.assemble("Base.", blocks, {})
        assert "Always included." in result


class TestValidateBlocks:
    """Verify validate_blocks() error detection."""

    def test_valid_blocks_no_errors(self, adapter: ConditionalPromptAdapter) -> None:
        """Valid blocks return an empty error list."""
        blocks = [
            PromptBlock(id="b1", content="Content 1"),
            PromptBlock(id="b2", content="Content 2"),
        ]
        errors = adapter.validate_blocks(blocks)
        assert errors == []

    def test_duplicate_ids_detected(self, adapter: ConditionalPromptAdapter) -> None:
        """Duplicate block IDs produce an error."""
        blocks = [
            PromptBlock(id="dup", content="First"),
            PromptBlock(id="dup", content="Second"),
        ]
        errors = adapter.validate_blocks(blocks)
        assert len(errors) == 1
        assert "Duplicate" in errors[0] or "duplicate" in errors[0]
        assert "dup" in errors[0]

    def test_invalid_priority_negative(self, adapter: ConditionalPromptAdapter) -> None:
        """Negative priority values produce an error."""
        blocks = [PromptBlock(id="neg", content="Content", priority=-1)]
        errors = adapter.validate_blocks(blocks)
        assert len(errors) == 1
        assert "priority" in errors[0].lower()

    def test_invalid_priority_too_high(self, adapter: ConditionalPromptAdapter) -> None:
        """Priority values > 100 produce an error."""
        blocks = [PromptBlock(id="high", content="Content", priority=101)]
        errors = adapter.validate_blocks(blocks)
        assert len(errors) == 1
        assert "priority" in errors[0].lower()

    def test_priority_zero_is_valid(self, adapter: ConditionalPromptAdapter) -> None:
        """Priority 0 is a valid value."""
        blocks = [PromptBlock(id="zero", content="Content", priority=0)]
        errors = adapter.validate_blocks(blocks)
        assert errors == []

    def test_multiple_errors_reported(self, adapter: ConditionalPromptAdapter) -> None:
        """All validation errors are collected, not just the first."""
        blocks = [
            PromptBlock(id="dup", content="First", priority=-5),
            PromptBlock(id="dup", content="Second", priority=200),
        ]
        errors = adapter.validate_blocks(blocks)
        # At least 3 errors: duplicate ID + 2 invalid priorities
        assert len(errors) >= 3
