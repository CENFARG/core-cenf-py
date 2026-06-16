"""CENF ErrorHandlingManager adapters — concrete implementations.

Exports:
- ClassificationAdapter: Production error handler with full classification,
  logging, metric emission, and guaranteed re-raise behavior.
- CapturingErrorAdapter: Test double that captures errors instead of re-raising.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.errors.adapters.classification_adapter import ClassificationAdapter

__all__ = [
    "CapturingErrorAdapter",
    "ClassificationAdapter",
]
