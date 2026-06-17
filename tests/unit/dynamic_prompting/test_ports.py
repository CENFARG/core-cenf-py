"""Unit tests for DynamicPromptingManager Protocol and PromptBlock Pydantic model.

Tests cover:
- DynamicPromptingManager Protocol contract (assemble, validate_blocks, get_json_schema)
- Protocol is runtime-checkable
- PromptBlock Pydantic model validation (frozen, forbid extra, defaults)
- Protocol satisfaction checks

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.dynamic_prompting.ports import DynamicPromptingManager, PromptBlock


class TestDynamicPromptingManagerProtocol:
    """Verify DynamicPromptingManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """DynamicPromptingManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(DynamicPromptingManager, "_is_runtime_protocol") or hasattr(
            DynamicPromptingManager, "__protocol_attrs__"
        )

    def test_has_assemble_method(self) -> None:
        """Protocol requires assemble(base_prompt, blocks, context_state) -> str."""
        assert hasattr(DynamicPromptingManager, "assemble")

    def test_has_validate_blocks_method(self) -> None:
        """Protocol requires validate_blocks(blocks) -> list[str]."""
        assert hasattr(DynamicPromptingManager, "validate_blocks")

    def test_has_get_json_schema_method(self) -> None:
        """Protocol requires get_json_schema() -> dict."""
        assert hasattr(DynamicPromptingManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all methods satisfies the protocol."""

        class ValidPromptingManager:
            async def assemble(self, base_prompt, blocks, context_state): ...
            def validate_blocks(self, blocks): ...
            @staticmethod
            def get_json_schema(): ...

        assert isinstance(ValidPromptingManager(), DynamicPromptingManager)

    def test_class_missing_assemble_fails_protocol(self) -> None:
        """A class without assemble() does NOT satisfy the protocol."""

        class Incomplete:
            def validate_blocks(self, blocks): ...

        assert not isinstance(Incomplete(), DynamicPromptingManager)


class TestPromptBlockModel:
    """Verify PromptBlock Pydantic model validation."""

    def test_valid_block_construction(self) -> None:
        """PromptBlock can be constructed with required fields."""
        block = PromptBlock(id="greeting", content="Always be polite.")
        assert block.id == "greeting"
        assert block.content == "Always be polite."
        assert block.condition is None
        assert block.priority == 10

    def test_condition_can_be_set(self) -> None:
        """PromptBlock accepts a dict condition."""
        block = PromptBlock(
            id="refund",
            condition={"session_state.intent": "refund"},
            content="Handle refunds.",
        )
        assert block.condition == {"session_state.intent": "refund"}

    def test_custom_priority(self) -> None:
        """PromptBlock accepts a custom priority."""
        block = PromptBlock(id="low", content="low priority", priority=5)
        assert block.priority == 5

    def test_frozen_model_immutable(self) -> None:
        """PromptBlock is frozen — attributes cannot be changed after construction."""
        block = PromptBlock(id="test", content="content")
        with pytest.raises((TypeError, ValueError)):
            block.id = "new-id"  # type: ignore[misc]

    def test_extra_fields_forbidden(self) -> None:
        """PromptBlock rejects extra fields (model_config extra=forbid)."""
        with pytest.raises(PydanticValidationError):
            PromptBlock(id="test", content="ok", extra_field="nope")

    def test_empty_id_fails(self) -> None:
        """id must not be empty."""
        with pytest.raises(PydanticValidationError):
            PromptBlock(id="", content="content")

    def test_empty_content_fails(self) -> None:
        """content must not be empty."""
        with pytest.raises(PydanticValidationError):
            PromptBlock(id="test", content="")
