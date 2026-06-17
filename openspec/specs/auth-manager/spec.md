---
Spec_ID: SPEC_M06
Title: AuthManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [auth, jwt, hs256, scopes, jwks]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M06: AuthManager

## Purpose

Provide JWT token validation (HS256), scope checking, M2M token issuance, and JWKS refresh. Sets tenant_id and principal_id contextvars from validated claims.

**Does NOT**: Manage user database, handle OAuth flows, store raw tokens.

## Python Protocol

```python
from __future__ import annotations
from typing import Protocol, runtime_checkable

from core_infrastructure.auth.models import TokenClaims

@runtime_checkable
class AuthManager(Protocol):
    """@ai-directive: All validate_token() methods MUST be async. NEVER cache validation indefinitely."""

    async def validate_token(self, token: str) -> TokenClaims:
        """Validate a JWT token and return its claims. Sets contextvars on success."""
        ...

    async def get_claims(self, token: str) -> TokenClaims:
        """Extract claims from a token without full re-validation."""
        ...

    async def refresh_jwks(self) -> None:
        """Refresh the JWKS cache from the configured endpoint."""
        ...

    def validate_scopes(self, claims: TokenClaims, required: list[str]) -> bool:
        """Check if token claims contain all required scopes."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class AuthSettings(BaseModel):
    oidc_issuer: str = Field(min_length=1)
    jwks_uri: str | None = Field(default=None)
    jwks_cache_ttl_seconds: int = Field(default=3600, ge=60)
    m2m_enabled: bool = Field(default=False)
    m2m_secret_path: str | None = Field(default=None)
    audience: str = Field(min_length=1, default="cenf-core")
    clock_skew_seconds: int = Field(default=30, ge=0, le=120)

class TokenClaims(BaseModel):
    sub: str = Field(min_length=1)
    iss: str = Field(min_length=1)
    aud: str = Field(min_length=1)
    exp: int = Field(gt=0)
    iat: int = Field(gt=0)
    scopes: list[str] = Field(default_factory=list)
    tenant_id: str | None = Field(default=None, max_length=64)
    principal_id: str | None = Field(default=None, max_length=64)
```

## Gherkin Scenarios

### Scenario: Valid token validation

- GIVEN a valid HS256 JWT with correct signature, unexpired, correct issuer/audience
- WHEN `validate_token(token)` is called
- THEN it returns `TokenClaims` with extracted claims
- AND `tenant_id` and `principal_id` contextvars are set

### Scenario: Expired token raises AuthError

- GIVEN a JWT with `exp` in the past
- WHEN `validate_token(token)` is called
- THEN it raises `AuthError` with reason "token_expired"

### Scenario: Invalid signature raises AuthError

- GIVEN a JWT with tampered signature
- WHEN `validate_token(token)` is called
- THEN it raises `AuthError` with reason "invalid_signature"

### Scenario: Scope validation

- GIVEN TokenClaims with scopes=["read", "write"]
- WHEN `validate_scopes(claims, required=["read", "admin"])` is called
- THEN it returns `False` (missing "admin")

### Scenario: JWKS refresh on key mismatch

- GIVEN a JWT signed with a key not in the current JWKS cache
- WHEN `validate_token(token)` is called
- THEN it triggers `refresh_jwks()` to fetch updated keys
- AND retries validation with the new JWKS

### Scenario: Clock skew tolerance

- GIVEN a JWT that expired 15 seconds ago
- GIVEN clock_skew_seconds = 30
- WHEN `validate_token(token)` is called
- THEN it accepts the token (within skew tolerance)

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Invalid signature | AUTH | Re-raise immediately |
| Expired token | AUTH | Re-raise immediately |
| Missing scopes | AUTH | Re-raise immediately |
| JWKS unreachable | TRANSIENT | Retry with backoff |
| OIDC misconfiguration | PERMANENT | Fail bootstrap |

## RED Metrics

- `cenf.auth.validate_total` (counter)
- `cenf.auth.errors_total{reason="..."}` (counter)
- `cenf.auth.validate_duration_seconds` (histogram)

## Test Requirements

- **Unit**: `InMemoryAuthAdapter` — mock JWT with hardcoded keys.
- **Integration**: `JoseAdapter` with mock OIDC server.
- **E2E**: Full M2M flow: issue → validate → check scope.

## Do's and Don'ts

**Do**:
- Validate signature, exp, iss, aud on every token
- Set tenant_id and principal_id contextvars from claims
- Refresh JWKS periodically and on key ID mismatch
- Support clock skew tolerance (configurable)

**Don't**:
- Manage user database
- Handle OAuth authorization code flows
- Store raw tokens in any form
- Cache validation results indefinitely
