"""CENF PermissionManager models — PermissionConfig, DelegationRecord, PermissionResult.

Defines the Pydantic models for PermissionManager data transfer and configuration.
PermissionConfig controls model/policy file paths; DelegationRecord represents
a time-limited delegation capability; PermissionResult captures authorization
decisions for audit.

Security: PermissionResult.context must not contain secrets or PII.
    DelegationRecord.purpose is logged for audit — keep it non-sensitive.
Observability: DelegationRecord.expires_at is used to prune expired delegations;
    expired delegations emit ``cenf.permission.delegation_expired_total``.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class PermissionConfig(BaseModel):
    """Configuration for PermissionManager adapters.

    Controls the paths to the Casbin model.conf and policy.csv files.
    Empty defaults are valid for the InMemoryPermissionAdapter test double.

    Attributes:
        model_path: Path to the Casbin model.conf file (e.g., RBAC with domains).
        policy_path: Path to the Casbin policy.csv file.
    """

    model_path: str = Field(
        default="",
        max_length=1024,
        description="Path to the Casbin model configuration file.",
    )
    policy_path: str = Field(
        default="",
        max_length=1024,
        description="Path to the Casbin policy CSV file.",
    )


class DelegationRecord(BaseModel):
    """A time-limited delegation from one principal to another.

    Represents an explicit capability delegation where a delegator grants
    a delegate permission to perform specific actions on a specific resource
    for a limited time, with a declared purpose.

    The expires_at field is computed from created_at + ttl_seconds at
    construction time. If created_at is not provided, the current UTC time
    is used.

    Security: ttl_seconds is capped at 86400 (24 hours). Delegations are
        NOT persistent across restarts in the MVP; persistent store is
        reserved for future ReBAC adapter.
    """

    model_config = {"extra": "forbid", "frozen": True}

    delegator_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="The principal granting the delegation.",
    )
    delegate_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="The principal receiving the delegation.",
    )
    delegate_type: Literal["human", "agent", "team"] = Field(
        ...,
        description="Type of the delegate principal.",
    )
    resource_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Type of the resource the delegation applies to.",
    )
    resource_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Identifier of the resource the delegation applies to.",
    )
    allowed_actions: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Actions the delegate is permitted to perform.",
    )
    purpose: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Declared purpose for this delegation.",
    )
    ttl_seconds: int = Field(
        ...,
        ge=1,
        le=86400,
        description="Time-to-live in seconds (max 24 hours).",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the delegation was created.",
    )

    @model_validator(mode="after")
    def _compute_expires_at(self) -> DelegationRecord:
        """Compute expires_at from created_at + ttl_seconds.

        Uses object.__setattr__ because the model is frozen=True.

        Returns:
            DelegationRecord: Self with expires_at set.
        """
        expires_at = datetime.fromtimestamp(
            self.created_at.timestamp() + self.ttl_seconds, tz=UTC
        )
        object.__setattr__(self, "expires_at", expires_at)
        return self

    # expires_at is computed in the validator above.
    # Declared as a regular attribute for type checking and Pydantic schema.
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Expiration timestamp (computed from created_at + ttl_seconds).",
        init=False,
    )


class PermissionResult(BaseModel):
    """A concrete PermissionDecision returned by adapters.

    Implements the PermissionDecision Protocol for use by adapter implementations.
    Carries the decision, reason, and contextual attributes for auditing.

    Attributes:
        allowed: Whether the action is permitted.
        reason: Machine-readable reason code (e.g., ``"rbac_allow"``).
        policy_id: Identifier of the policy that produced the decision, or empty.
        context: Additional attributes for audit (purpose, on_behalf_of, etc.).
    """

    model_config = {"extra": "forbid", "frozen": True}

    allowed: bool = Field(
        ...,
        description="Whether the action is permitted.",
    )
    reason: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Machine-readable reason code.",
    )
    policy_id: str = Field(
        default="",
        max_length=128,
        description="Identifier of the policy that produced this decision.",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional audit context.",
    )

    def is_allowed(self) -> bool:
        """Return whether the action is permitted.

        Returns:
            bool: The allowed flag value.
        """
        return self.allowed

    def attributes(self) -> dict[str, Any]:
        """Return the context dict for audit.

        Returns:
            dict[str, Any]: The context attributes.
        """
        return self.context
