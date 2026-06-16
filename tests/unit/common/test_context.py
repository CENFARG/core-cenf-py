"""Unit tests for common.context — contextvars propagation module.

Tests cover:
- Default values for correlation_id, tenant_id, trace_id, span_id
- Getter/setter type safety
- UUID4 generation for new_correlation_id
- Context snapshot serialization and restoration roundtrip
- ContextValidation model with boundary checks
- Context propagation across async boundaries

Author: CENF AI Team
Version: 0.1.0
"""

import asyncio
import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.common.context import (
    ContextValidation,
    get_context_snapshot,
    get_correlation_id,
    get_span_id,
    get_tenant_id,
    get_trace_id,
    new_correlation_id,
    restore_context_snapshot,
    set_correlation_id,
    set_span_id,
    set_tenant_id,
    set_trace_id,
)


class TestContextDefaults:
    """Verify default contextvar values when nothing has been explicitly set."""

    def test_correlation_id_default_is_system_init(self) -> None:
        """get_correlation_id() returns 'system-init' when not set."""
        result = get_correlation_id()
        assert result == "system-init"

    def test_tenant_id_default_is_global(self) -> None:
        """get_tenant_id() returns 'global' when not set."""
        result = get_tenant_id()
        assert result == "global"

    def test_trace_id_default_is_empty_string(self) -> None:
        """get_trace_id() returns '' when not set."""
        result = get_trace_id()
        assert result == ""

    def test_span_id_default_is_empty_string(self) -> None:
        """get_span_id() returns '' when not set."""
        result = get_span_id()
        assert result == ""


class TestContextSettersAndGetters:
    """Verify that set_* functions update values and get_* functions return them."""

    def test_set_and_get_correlation_id(self) -> None:
        """Setting correlation_id via setter is retrievable via getter."""
        set_correlation_id("abc-123")
        assert get_correlation_id() == "abc-123"
        # Reset to avoid test pollution
        set_correlation_id("system-init")

    def test_set_and_get_tenant_id(self) -> None:
        """Setting tenant_id via setter is retrievable via getter."""
        set_tenant_id("tenant-xyz")
        assert get_tenant_id() == "tenant-xyz"
        set_tenant_id("global")

    def test_set_and_get_trace_id(self) -> None:
        """Setting trace_id via setter is retrievable via getter."""
        set_trace_id("trace-456")
        assert get_trace_id() == "trace-456"
        set_trace_id("")

    def test_set_and_get_span_id(self) -> None:
        """Setting span_id via setter is retrievable via getter."""
        set_span_id("span-789")
        assert get_span_id() == "span-789"
        set_span_id("")

    def test_all_four_contextvars_independent(self) -> None:
        """Each contextvar has its own value space — no crosstalk."""
        set_correlation_id("cid-1")
        set_tenant_id("tid-2")
        set_trace_id("trc-3")
        set_span_id("spn-4")

        assert get_correlation_id() == "cid-1"
        assert get_tenant_id() == "tid-2"
        assert get_trace_id() == "trc-3"
        assert get_span_id() == "spn-4"

        # Reset
        set_correlation_id("system-init")
        set_tenant_id("global")
        set_trace_id("")
        set_span_id("")


class TestNewCorrelationId:
    """Verify new_correlation_id generates valid UUID4 strings."""

    def test_returns_valid_uuid4_string(self) -> None:
        """new_correlation_id() returns a string that can be parsed as UUID."""
        cid = new_correlation_id()
        assert isinstance(cid, str)
        parsed = uuid.UUID(cid)
        assert parsed.version == 4  # UUID4

    def test_generates_unique_values(self) -> None:
        """Multiple calls produce different correlation IDs."""
        ids = {new_correlation_id() for _ in range(100)}
        assert len(ids) == 100  # All unique

    def test_updates_contextvar(self) -> None:
        """After calling new_correlation_id(), get_correlation_id() returns the new value."""
        previous = get_correlation_id()
        cid = new_correlation_id()
        assert get_correlation_id() == cid
        # Restore
        set_correlation_id(previous)


class TestContextSnapshot:
    """Verify snapshot serialization and restoration roundtrip."""

    def test_snapshot_captures_all_four_variables(self) -> None:
        """Snapshot dict contains keys for all four contextvars."""
        set_correlation_id("snap-cid")
        set_tenant_id("snap-tid")
        set_trace_id("snap-trc")
        set_span_id("snap-spn")

        snapshot = get_context_snapshot()

        assert snapshot["correlation_id"] == "snap-cid"
        assert snapshot["tenant_id"] == "snap-tid"
        assert snapshot["trace_id"] == "snap-trc"
        assert snapshot["span_id"] == "snap-spn"

        # Reset
        set_correlation_id("system-init")
        set_tenant_id("global")
        set_trace_id("")
        set_span_id("")

    def test_restore_roundtrip_preserves_all_values(self) -> None:
        """Restoring a snapshot sets all contextvars to their captured values."""
        # Setup known state
        set_correlation_id("original-cid")
        set_tenant_id("original-tid")
        set_trace_id("original-trc")
        set_span_id("original-spn")

        snapshot = get_context_snapshot()

        # Change everything
        set_correlation_id("changed-cid")
        set_tenant_id("changed-tid")
        set_trace_id("changed-trc")
        set_span_id("changed-spn")

        # Restore
        restore_context_snapshot(snapshot)

        assert get_correlation_id() == "original-cid"
        assert get_tenant_id() == "original-tid"
        assert get_trace_id() == "original-trc"
        assert get_span_id() == "original-spn"

        # Reset
        set_correlation_id("system-init")
        set_tenant_id("global")
        set_trace_id("")
        set_span_id("")


class TestContextValidation:
    """Verify ContextValidation Pydantic model boundary checks."""

    def test_valid_context_passes_validation(self) -> None:
        """Model with all valid fields is accepted."""
        model = ContextValidation(
            correlation_id="valid-cid-123",
            tenant_id="valid-tid-456",
            trace_id="trace-abc",
            span_id="span-xyz",
        )
        assert model.correlation_id == "valid-cid-123"
        assert model.tenant_id == "valid-tid-456"

    def test_empty_correlation_id_fails_validation(self) -> None:
        """correlation_id with min_length=1 rejects empty string."""
        with pytest.raises(PydanticValidationError):
            ContextValidation(correlation_id="", tenant_id="tid")

    def test_empty_tenant_id_fails_validation(self) -> None:
        """tenant_id with min_length=1 rejects empty string."""
        with pytest.raises(PydanticValidationError):
            ContextValidation(correlation_id="cid", tenant_id="")

    def test_correlation_id_exceeding_64_chars_fails(self) -> None:
        """correlation_id with max_length=64 rejects strings > 64 chars."""
        with pytest.raises(PydanticValidationError):
            ContextValidation(
                correlation_id="x" * 65,
                tenant_id="tid",
            )

    def test_tenant_id_exceeding_64_chars_fails(self) -> None:
        """tenant_id with max_length=64 rejects strings > 64 chars."""
        with pytest.raises(PydanticValidationError):
            ContextValidation(
                correlation_id="cid",
                tenant_id="x" * 65,
            )

    def test_trace_id_exceeding_64_chars_fails(self) -> None:
        """trace_id with max_length=64 rejects strings > 64 chars."""
        with pytest.raises(PydanticValidationError):
            ContextValidation(
                correlation_id="cid",
                tenant_id="tid",
                trace_id="x" * 65,
            )

    def test_span_id_exceeding_64_chars_fails(self) -> None:
        """span_id with max_length=64 rejects strings > 64 chars."""
        with pytest.raises(PydanticValidationError):
            ContextValidation(
                correlation_id="cid",
                tenant_id="tid",
                span_id="x" * 65,
            )

    def test_default_trace_id_is_empty(self) -> None:
        """trace_id defaults to empty string."""
        model = ContextValidation(correlation_id="cid", tenant_id="tid")
        assert model.trace_id == ""

    def test_default_span_id_is_empty(self) -> None:
        """span_id defaults to empty string."""
        model = ContextValidation(correlation_id="cid", tenant_id="tid")
        assert model.span_id == ""


class TestContextAsyncPropagation:
    """Verify contextvars propagate correctly across async boundaries."""

    @pytest.mark.asyncio
    async def test_contextvars_propagate_across_await(self) -> None:
        """Contextvars set before an await are visible after it."""

        async def fake_io() -> str:
            await asyncio.sleep(0)
            # Context should still be visible
            return get_correlation_id()

        set_correlation_id("async-test-cid")
        result = await fake_io()
        assert result == "async-test-cid"

        # Reset
        set_correlation_id("system-init")

    @pytest.mark.asyncio
    async def test_contextvars_propagate_to_nested_coroutines(self) -> None:
        """Deeply nested coroutines see parent-set contextvars."""

        async def level_3() -> str:
            await asyncio.sleep(0)
            return get_correlation_id()

        async def level_2() -> str:
            return await level_3()

        async def level_1() -> str:
            return await level_2()

        set_correlation_id("nested-async-cid")
        assert await level_1() == "nested-async-cid"

        set_correlation_id("system-init")

    @pytest.mark.asyncio
    async def test_different_tasks_have_independent_context(self) -> None:
        """Each asyncio task has its own contextvar space."""

        async def task_with_id(cid: str) -> str:
            set_correlation_id(cid)
            await asyncio.sleep(0.01)
            return get_correlation_id()

        results = await asyncio.gather(
            task_with_id("task-a"),
            task_with_id("task-b"),
            task_with_id("task-c"),
        )
        assert results == ["task-a", "task-b", "task-c"]
