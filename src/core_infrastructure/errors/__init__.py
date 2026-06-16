"""CENF ErrorHandlingManager — structured error classification and reporting.

Provides a Protocol-based interface for classifying, logging, and emitting
metrics on exceptions using the CenfError taxonomy. The @handle_errors
decorator offers type-safe function wrapping with automatic classification,
metric emission, and guaranteed re-raise behavior.

Security: ErrorReport never includes raw secrets. All classification is
    based on error type hierarchy, not error message content.
Observability: RED counter ``cenf.error.classified_total`` emitted per
    error type on every classification event.
@ai-directive: NEVER swallow errors in production adapters. The capturing
    adapter exists solely for testing.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.errors.adapters.classification_adapter import ClassificationAdapter
from core_infrastructure.errors.models import ErrorClassification, ErrorContext, ErrorReport
from core_infrastructure.errors.ports import ErrorHandlingManager

__all__ = [
    "CapturingErrorAdapter",
    "ClassificationAdapter",
    "ErrorClassification",
    "ErrorContext",
    "ErrorHandlingManager",
    "ErrorReport",
]
