"""Unit tests for ErrorHandlingManager Protocol and ErrorClassification enum.

Tests cover:
- ErrorHandlingManager Protocol contract (classify, report, handle)
- ErrorClassification enum values
- Protocol is runtime-checkable
- @handle_errors is a decorator factory present on the Protocol

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.errors.models import ErrorClassification
from core_infrastructure.errors.ports import ErrorHandlingManager


class TestErrorClassificationEnum:
    """Verify ErrorClassification enum has all required members."""

    def test_transient_member(self) -> None:
        """TRANSIENT member exists."""
        assert ErrorClassification.TRANSIENT is not None
        assert isinstance(ErrorClassification.TRANSIENT, ErrorClassification)

    def test_permanent_member(self) -> None:
        """PERMANENT member exists."""
        assert ErrorClassification.PERMANENT is not None

    def test_validation_member(self) -> None:
        """VALIDATION member exists."""
        assert ErrorClassification.VALIDATION is not None

    def test_auth_member(self) -> None:
        """AUTH member exists."""
        assert ErrorClassification.AUTH is not None

    def test_rate_limit_member(self) -> None:
        """RATE_LIMIT member exists."""
        assert ErrorClassification.RATE_LIMIT is not None

    def test_enum_has_five_members(self) -> None:
        """ErrorClassification has exactly 5 members."""
        assert len(ErrorClassification.__members__) == 5


class TestErrorHandlingManagerProtocol:
    """Verify ErrorHandlingManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """ErrorHandlingManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(ErrorHandlingManager, "_is_runtime_protocol") or hasattr(
            ErrorHandlingManager, "__protocol_attrs__"
        )

    def test_has_classify_method(self) -> None:
        """Protocol requires classify(error) -> ErrorClassification."""
        assert hasattr(ErrorHandlingManager, "classify")

    def test_has_report_method(self) -> None:
        """Protocol requires report(error, context)."""
        assert hasattr(ErrorHandlingManager, "report")

    def test_has_handle_method(self) -> None:
        """Protocol requires handle(error, context) -> ErrorReport."""
        assert hasattr(ErrorHandlingManager, "handle")

    def test_has_handle_errors_decorator(self) -> None:
        """Protocol has handle_errors decorator factory."""
        assert hasattr(ErrorHandlingManager, "handle_errors")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all ErrorHandlingManager methods satisfies the protocol."""

        class ValidHandler:
            def classify(self, error: Exception): ...
            def report(self, error: Exception, context: dict | None = None) -> None: ...
            def handle(self, error: Exception, context: dict | None = None): ...
            def handle_errors(self, **decorator_opts): ...

        assert isinstance(ValidHandler(), ErrorHandlingManager)

    def test_class_missing_classify_fails_protocol(self) -> None:
        """A class without classify() does NOT satisfy ErrorHandlingManager."""

        class Incomplete:
            def report(self, error: Exception, context: dict | None = None) -> None: ...
            def handle(self, error: Exception, context: dict | None = None): ...

        assert not isinstance(Incomplete(), ErrorHandlingManager)
