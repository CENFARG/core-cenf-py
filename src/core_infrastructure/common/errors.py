"""CENF error taxonomy — structured exception hierarchy for classification and retry.

Provides a five-category ErrorType enum and a base CenfError class that all
12 infrastructure managers use for error classification, retry decisions,
and structured error serialization (details dict).

Security: details dict values are always strings — JSON-serializable, no
    sensitive data leakage through structured error attributes.
Observability: ErrorHandlingManager emits RED metrics per error_type on each
    classification event.
@ai-directive: Pure Python exceptions — no Pydantic models needed here.
    ErrorHandlingManager (not this module) maps built-in types to ErrorType.

Author: CENF AI Team
Version: 0.1.0
"""

from enum import Enum, auto


class ErrorType(Enum):
    """Error classification taxonomy for retry and routing decisions.

    Each concrete CenfError subclass maps to exactly one ErrorType member.
    ErrorHandlingManager uses this enum to decide between retry (TRANSIENT,
    RATE_LIMIT) and immediate failure (PERMANENT, VALIDATION, AUTH).
    """

    TRANSIENT = auto()
    PERMANENT = auto()
    VALIDATION = auto()
    AUTH = auto()
    RATE_LIMIT = auto()


class CenfError(Exception):
    """Base class for all CENF infrastructure errors.

    Every error raised by a CENF infrastructure manager must inherit from
    this class or one of its five concrete subclasses. The ``error_type``
    attribute enables generic retry/classification logic without isinstance
    chains.

    Args:
        message: Human-readable error description.
        details: Optional dict of structured context (str keys and values
            only — JSON-serializable).

    Attributes:
        error_type: The ErrorType category for this error.
        retryable: Whether the caller should retry the operation.
        details: Structured error context dict.
    """

    error_type: ErrorType = ErrorType.PERMANENT
    retryable: bool = False

    def __init__(self, message: str, *, details: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, str] = details if details is not None else {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)!r}, error_type={self.error_type.name})"


class TransientError(CenfError):
    """Temporary failure — the operation should be retried.

    Examples: network timeout, connection refused, database deadlock,
    external service temporarily unavailable.

    Observability: RED counter ``cenf.error.classified_total{error_type="TRANSIENT"}``
    is incremented by ErrorHandlingManager.
    """

    error_type: ErrorType = ErrorType.TRANSIENT
    retryable: bool = True


class PermanentError(CenfError):
    """Non-recoverable failure — retrying will NOT help.

    Examples: missing configuration file, invalid schema, not implemented,
    corrupted state that requires manual intervention.
    """

    error_type: ErrorType = ErrorType.PERMANENT
    retryable: bool = False


class ValidationError(CenfError):
    """Input validation failure — caller must fix the input before retrying.

    Examples: invalid email format, missing required field, value out of range,
    type coercion failure.

    Observability: ErrorHandlingManager does NOT retry this error type.
    """

    error_type: ErrorType = ErrorType.VALIDATION
    retryable: bool = False


class AuthError(CenfError):
    """Authentication or authorization failure.

    Examples: invalid token, expired credentials, insufficient permissions,
    forbidden access.

    Security: NEVER include raw tokens or secrets in the message or details.
    """

    error_type: ErrorType = ErrorType.AUTH
    retryable: bool = False


class RateLimitError(CenfError):
    """Rate limit exceeded — retry after backoff.

    Examples: HTTP 429, API quota exhausted, Redis rate limiter triggered.

    Observability: ErrorHandlingManager retries with exponential backoff + jitter.
    """

    error_type: ErrorType = ErrorType.RATE_LIMIT
    retryable: bool = True
