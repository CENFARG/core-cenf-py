"""Unit tests for common.errors — CENF error taxonomy.

Tests cover:
- ErrorType enum values and membership
- CenfError base class with error_type, retryable, details
- Five concrete subclasses with correct error_type and retryable defaults
- JSON-serializable details dict
- String representation and exception inheritance
- isinstance checks against base and concrete types

Author: CENF AI Team
Version: 0.1.0
"""

import json

import pytest

from core_infrastructure.common.errors import (
    AuthError,
    CenfError,
    ErrorType,
    PermanentError,
    RateLimitError,
    TransientError,
    ValidationError,
)


class TestErrorTypeEnum:
    """Verify ErrorType enum contains the five taxonomy categories."""

    def test_has_five_members(self) -> None:
        """ErrorType has exactly 5 members: TRANSIENT, PERMANENT, VALIDATION, AUTH, RATE_LIMIT."""
        members = list(ErrorType)
        assert len(members) == 5

    def test_transient_member_exists(self) -> None:
        """ErrorType.TRANSIENT is a valid enum member."""
        assert ErrorType.TRANSIENT is not None

    def test_permanent_member_exists(self) -> None:
        """ErrorType.PERMANENT is a valid enum member."""
        assert ErrorType.PERMANENT is not None

    def test_validation_member_exists(self) -> None:
        """ErrorType.VALIDATION is a valid enum member."""
        assert ErrorType.VALIDATION is not None

    def test_auth_member_exists(self) -> None:
        """ErrorType.AUTH is a valid enum member."""
        assert ErrorType.AUTH is not None

    def test_rate_limit_member_exists(self) -> None:
        """ErrorType.RATE_LIMIT is a valid enum member."""
        assert ErrorType.RATE_LIMIT is not None

    def test_all_members_are_distinct(self) -> None:
        """Each ErrorType member has a unique value."""
        values = [e.value for e in ErrorType]
        assert len(values) == len(set(values))

    def test_value_equality(self) -> None:
        """ErrorType enum members can be compared by identity."""
        assert ErrorType.TRANSIENT is ErrorType.TRANSIENT
        assert ErrorType.TRANSIENT is not ErrorType.PERMANENT


class TestCenfErrorBase:
    """Verify CenfError base class contract."""

    def test_is_exception_subclass(self) -> None:
        """CenfError inherits from built-in Exception."""
        assert issubclass(CenfError, Exception)

    def test_instantiate_with_message_only(self) -> None:
        """CenfError can be created with just a message string."""
        e = CenfError("Something went wrong")
        assert str(e) == "Something went wrong"

    def test_default_error_type_is_permanent(self) -> None:
        """CenfError defaults to ErrorType.PERMANENT."""
        e = CenfError("test")
        assert e.error_type == ErrorType.PERMANENT

    def test_default_retryable_is_false(self) -> None:
        """CenfError is NOT retryable by default."""
        e = CenfError("test")
        assert e.retryable is False

    def test_default_details_is_empty_dict(self) -> None:
        """details defaults to an empty dict when not provided."""
        e = CenfError("test")
        assert e.details == {}

    def test_details_are_stored(self) -> None:
        """Custom details dict is preserved."""
        e = CenfError("test", details={"key": "value", "code": "E001"})
        assert e.details == {"key": "value", "code": "E001"}

    def test_details_are_json_serializable(self) -> None:
        """details dict values are always strings, making it JSON-serializable."""
        e = CenfError("test", details={"field": "username", "reason": "too_short"})
        serialized = json.dumps(e.details)
        deserialized = json.loads(serialized)
        assert deserialized == {"field": "username", "reason": "too_short"}

    def test_repr_includes_message(self) -> None:
        """repr() contains the error message."""
        e = CenfError("disk full")
        r = repr(e)
        assert "disk full" in r

    def test_message_via_str_matches_constructor(self) -> None:
        """str(error) returns the message passed to the constructor."""
        e = CenfError("connection refused")
        assert str(e) == "connection refused"


class TestConcreteErrorClasses:
    """Verify each concrete error subclass has correct defaults."""

    def test_transient_error_is_retryable(self) -> None:
        """TransientError is retryable and has TRANSIENT error_type."""
        e = TransientError("timeout")
        assert e.error_type == ErrorType.TRANSIENT
        assert e.retryable is True

    def test_permanent_error_is_not_retryable(self) -> None:
        """PermanentError is NOT retryable and has PERMANENT error_type."""
        e = PermanentError("config missing")
        assert e.error_type == ErrorType.PERMANENT
        assert e.retryable is False

    def test_validation_error_is_not_retryable(self) -> None:
        """ValidationError is NOT retryable (user must fix input)."""
        e = ValidationError("invalid email")
        assert e.error_type == ErrorType.VALIDATION
        assert e.retryable is False

    def test_auth_error_is_not_retryable(self) -> None:
        """AuthError is NOT retryable (requires re-authentication)."""
        e = AuthError("token expired")
        assert e.error_type == ErrorType.AUTH
        assert e.retryable is False

    def test_rate_limit_error_is_retryable(self) -> None:
        """RateLimitError IS retryable (can retry after backoff)."""
        e = RateLimitError("too many requests")
        assert e.error_type == ErrorType.RATE_LIMIT
        assert e.retryable is True

    def test_all_concrete_errors_inherit_from_cenf_error(self) -> None:
        """All five concrete errors are subclasses of CenfError."""
        for cls in [TransientError, PermanentError, ValidationError, AuthError, RateLimitError]:
            assert issubclass(cls, CenfError), f"{cls.__name__} does not inherit from CenfError"

    def test_all_concrete_errors_inherit_from_exception(self) -> None:
        """All five concrete errors are subclasses of Exception."""
        for cls in [TransientError, PermanentError, ValidationError, AuthError, RateLimitError]:
            assert issubclass(cls, Exception), f"{cls.__name__} does not inherit from Exception"

    def test_can_catch_with_cenf_error_base(self) -> None:
        """All concrete errors can be caught with 'except CenfError'."""
        caught = False
        try:
            raise TransientError("boom")
        except CenfError:
            caught = True
        assert caught is True

    def test_can_catch_with_concrete_type(self) -> None:
        """Concrete errors can be caught specifically."""
        caught = False
        try:
            raise ValidationError("bad input")
        except ValidationError:
            caught = True
        except CenfError:
            pytest.fail("ValidationError should be caught by its own handler")
        assert caught is True

    def test_isinstance_check(self) -> None:
        """isinstance works correctly for the hierarchy."""
        e = AuthError("unauthorized")
        assert isinstance(e, AuthError)
        assert isinstance(e, CenfError)
        assert isinstance(e, Exception)

    def test_details_passed_to_concrete_error(self) -> None:
        """Concrete errors forward details to CenfError base."""
        e = PermanentError("disk error", details={"disk": "sda1", "mount": "/data"})
        assert e.details == {"disk": "sda1", "mount": "/data"}


class TestErrorCatchingPatterns:
    """Verify error taxonomy integrates correctly with try/except patterns."""

    def test_raise_and_catch_transient(self) -> None:
        """TransientError can be raised and caught by its own type."""
        with pytest.raises(TransientError) as exc_info:
            raise TransientError("network timeout")
        assert exc_info.value.error_type == ErrorType.TRANSIENT
        assert exc_info.value.retryable is True

    def test_raise_and_catch_permanent(self) -> None:
        """PermanentError can be raised and caught by its own type."""
        with pytest.raises(PermanentError) as exc_info:
            raise PermanentError("misconfiguration")
        assert exc_info.value.error_type == ErrorType.PERMANENT
        assert exc_info.value.retryable is False

    def test_raise_and_catch_rate_limit(self) -> None:
        """RateLimitError can be raised and caught."""
        with pytest.raises(RateLimitError) as exc_info:
            raise RateLimitError("rate exceeded", details={"retry_after": "30"})
        assert exc_info.value.error_type == ErrorType.RATE_LIMIT
        assert exc_info.value.details["retry_after"] == "30"

    def test_retry_decision_based_on_error_type(self) -> None:
        """Application code can branch on error_type for retry logic."""
        errors = [
            (TransientError("t"), True),
            (PermanentError("p"), False),
            (ValidationError("v"), False),
            (AuthError("a"), False),
            (RateLimitError("r"), True),
        ]
        for error, should_retry in errors:
            assert error.retryable == should_retry, (
                f"{error.__class__.__name__} retryable={error.retryable}, expected={should_retry}"
            )
