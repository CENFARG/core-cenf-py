"""CENF LicenceManager models — LicenseClaims, LicenceConfig.

Defines the Pydantic models for LicenceManager data transfer and configuration.
LicenseClaims represents the validated JWT-like licence payload; LicenceConfig
controls public key JWK, grace period duration, and offline mode.

Security: LicenseClaims NEVER carries the raw token string — only validated
    claims. public_key_jwk is stored in LicenceConfig but actual key material
    is retrieved from SecretManager at runtime.
Observability: Grace period transitions emit
    ``cenf.licence.grace_period_active_total``.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LicenseClaims(BaseModel):
    """Validated licence claims extracted from a signed licence document.

    Represents the decoded payload of a JWT-like licence token. All standard
    licence claims are supported: tenant binding, tier, feature flags,
    expiration, and seat limits.

    Attributes:
        license_id: Unique licence identifier.
        tenant_id: Tenant this licence is bound to.
        tier: Licence tier (free, pro, enterprise).
        features: Feature name to enabled/disabled mapping.
        expiry: Expiration timestamp (UNIX epoch seconds), or None if perpetual.
        not_before: Activation timestamp, or None if immediately valid.
        max_seats: Maximum concurrent seats, or None if unlimited.
        issued_at: Issuance timestamp (UNIX epoch seconds).
        installation_id: Optional installation fingerprint for node-locking.

    Security: This model is frozen — immutable after construction.
        Extra fields are forbidden to prevent injection.
    """

    model_config = {"extra": "forbid", "frozen": True}

    license_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Unique licence identifier.",
    )
    tenant_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Tenant this licence is bound to.",
    )
    tier: Literal["free", "pro", "enterprise"] = Field(
        ...,
        description="Licence tier.",
    )
    features: dict[str, bool] = Field(
        default_factory=dict,
        description="Feature name to enabled/disabled mapping.",
    )
    expiry: float | None = Field(
        default=None,
        gt=0,
        description="Expiration timestamp (UNIX epoch seconds), or None.",
    )
    not_before: float | None = Field(
        default=None,
        gt=0,
        description="Activation timestamp, or None if immediately valid.",
    )
    max_seats: int | None = Field(
        default=None,
        gt=0,
        description="Maximum concurrent seats, or None if unlimited.",
    )
    issued_at: float = Field(
        ...,
        gt=0,
        description="Issuance timestamp (UNIX epoch seconds).",
    )
    installation_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional installation fingerprint for node-locking.",
    )


class LicenceConfig(BaseModel):
    """Configuration for LicenceManager adapters.

    Controls the public key JWK for RS256 verification, grace period
    duration, and offline mode flag.

    Attributes:
        public_key_jwk: JWK JSON string for RS256 public key verification.
            Retrieved from SecretManager at adapter initialization.
        grace_period_days: Number of days after expiry that features remain
            accessible in degraded mode (0-30).
        offline_mode_allowed: Whether offline licence activation is permitted.
    """

    public_key_jwk: str = Field(
        default="",
        max_length=4096,
        description="JWK JSON string for RS256 public key verification.",
    )
    grace_period_days: int = Field(
        default=7,
        ge=0,
        le=30,
        description="Grace period in days after expiry (max 30).",
    )
    offline_mode_allowed: bool = Field(
        default=False,
        description="Whether offline licence activation is permitted.",
    )
