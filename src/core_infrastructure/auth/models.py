"""CENF AuthManager models — TokenClaims, JWKSKey, AuthConfig.

Defines the Pydantic models for AuthManager data transfer and configuration.
TokenClaims represents the validated JWT payload; AuthConfig controls
issuer, audience, JWKS endpoint, and algorithm selection.

Security: TokenClaims NEVER carries the raw token string — only validated
    claims. scopes field is validated but not encrypted.
Observability: AuthConfig.jwks_url is logged at DEBUG level on refresh.
@ai-directive: NEVER add a raw_token field to TokenClaims. The token
    itself is consumed by validate_token() and discarded.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenClaims(BaseModel):
    """Validated JWT claims extracted from a token by AuthManager.

    All standard OIDC claims are supported. Custom CENF claims (tenant_id,
    principal_id) enable multi-tenant data isolation and principal-based
    authorization.

    Attributes:
        sub: Subject identifier (the principal the token is about).
        iss: Issuer URL (e.g., ``https://auth.cenf.tech``).
        aud: Intended audience (must match the service identifier).
        exp: Expiration timestamp (UNIX epoch seconds).
        iat: Issued-at timestamp (UNIX epoch seconds).
        nbf: Not-before timestamp, or None if not present.
        scopes: List of scope strings (e.g., ``["read:users"]``).
        tenant_id: CENF multi-tenant identifier for data isolation.
        principal_id: CENF principal identifier for audit trails.

    Security: scopes are NOT encrypted. Callers must not log sensitive scopes
        in production.
    """

    sub: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Subject identifier.",
    )
    iss: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Issuer URL.",
    )
    aud: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Intended audience.",
    )
    exp: int = Field(
        ...,
        gt=0,
        description="Expiration timestamp (UNIX epoch seconds).",
    )
    iat: int = Field(
        ...,
        ge=0,
        description="Issued-at timestamp (UNIX epoch seconds).",
    )
    nbf: int | None = Field(
        default=None,
        description="Not-before timestamp, or None.",
    )
    scopes: list[str] = Field(
        default_factory=list,
        description="Scope strings from the token.",
    )
    tenant_id: str = Field(
        default="",
        max_length=64,
        description="CENF multi-tenant identifier.",
    )
    principal_id: str = Field(
        default="",
        max_length=64,
        description="CENF principal identifier.",
    )


class JWKSKey(BaseModel):
    """A single JWK (JSON Web Key) from a JWKS endpoint.

    Represents a public key used for RS256/RS384/RS512 token verification.

    Attributes:
        kid: Key ID for matching the token header.
        kty: Key type (e.g., ``"RSA"``).
        alg: Algorithm (e.g., ``"RS256"``).
        n: RSA modulus (base64url-encoded).
        e: RSA exponent (base64url-encoded).
    """

    kid: str = Field(
        ...,
        min_length=1,
        description="Key ID.",
    )
    kty: str = Field(
        default="RSA",
        min_length=1,
        description="Key type.",
    )
    alg: str = Field(
        default="RS256",
        min_length=1,
        description="Algorithm.",
    )
    n: str = Field(
        default="",
        description="RSA modulus (base64url).",
    )
    e: str = Field(
        default="AQAB",
        description="RSA exponent (base64url).",
    )


class AuthConfig(BaseModel):
    """Configuration for AuthManager adapters.

    Controls token validation parameters: expected issuer/audience,
    supported algorithms, JWKS endpoint for RS256 public keys, and
    clock skew tolerance (leeway).

    Attributes:
        issuer: Expected ``iss`` claim value.
        audience: Expected ``aud`` claim value.
        jwks_url: URL to fetch JWKS for RS256 verification.
        algorithms: Allowed signing algorithms (default ``["HS256"]``).
        token_leeway: Clock skew tolerance in seconds (default 60).
    """

    issuer: str = Field(
        default="",
        max_length=512,
        description="Expected issuer claim.",
    )
    audience: str = Field(
        default="",
        max_length=256,
        description="Expected audience claim.",
    )
    jwks_url: str = Field(
        default="",
        max_length=2048,
        description="JWKS endpoint URL.",
    )
    algorithms: list[str] = Field(
        default_factory=lambda: ["HS256"],
        min_length=1,
        description="Allowed signing algorithms.",
    )
    token_leeway: int = Field(
        default=60,
        ge=0,
        le=300,
        description="Clock skew tolerance in seconds.",
    )
