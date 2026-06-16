"""AuthManager Protocol — the contract every auth adapter must satisfy.

Defines the token validation interface consumed by all infrastructure
managers that need M2M authentication. Adapters implement HS256 symmetric
validation (JwtAuthAdapter) or static claims (StaticAuthAdapter for testing).

Security: Validate_token() validates exp, iat, nbf, iss, aud. NEVER trust
    a token without full validation.
Observability: Token validation events emit RED counters via ObservabilityManager.
@ai-directive: All validate_token() methods MUST be async — token validation
    may involve network I/O (JWKS refresh). NEVER cache validation results
    indefinitely.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core_infrastructure.auth.models import TokenClaims


@runtime_checkable
class AuthManager(Protocol):
    """Token validation and claims extraction contract.

    All infrastructure managers that need M2M auth consume this interface.
    Concrete adapters provide HS256 symmetric validation, RS256 via JWKS,
    or static claims for testing.

    Rules:
        - validate_token() is async — may fetch JWKS on cache miss.
        - get_claims() returns TokenClaims without re-validating expiry.
        - refresh_jwks() is called periodically to rotate RS256 keys.
        - validate_scopes() is sync — pure logic, no I/O.
        - All implementations MUST set tenant_id and principal_id contextvars
          from validated claims.

    Security: NEVER accept tokens without full validation. Expired tokens
        MUST raise AuthError. Wrong signature MUST raise AuthError.

    @ai-directive: When adding a new validation check, update all adapter
        implementations AND TokenClaims model.
    """

    async def validate_token(self, token: str) -> TokenClaims:
        """Validate a JWT token and return its claims.

        Performs full validation: signature, expiry, issuer, audience,
        and not-before. Sets tenant_id and principal_id contextvars on success.

        Args:
            token: The raw JWT token string.

        Returns:
            TokenClaims: The validated claims extracted from the token.

        Raises:
            AuthError: If the token is expired, has invalid signature,
                wrong issuer, wrong audience, or is not yet valid.

        Security: The raw token string is NEVER stored in TokenClaims.
        """
        ...

    async def get_claims(self, token: str) -> TokenClaims:
        """Extract claims from a token without full re-validation.

        Useful for reading claims from an already-validated token.

        Args:
            token: The raw JWT token string.

        Returns:
            TokenClaims: The claims from the token.

        Raises:
            AuthError: If the token cannot be decoded.
        """
        ...

    async def refresh_jwks(self) -> None:
        """Refresh the JWKS cache from the configured JWKS endpoint.

        Called periodically (e.g., every 60 minutes) to pick up key rotations.
        Must be idempotent and safe to call concurrently.

        Raises:
            AuthError: If the JWKS endpoint is unreachable.
        """
        ...

    def validate_scopes(self, claims: TokenClaims, required: list[str]) -> bool:
        """Check if token claims contain all required scopes.

        Args:
            claims: The validated token claims.
            required: List of scope strings that must all be present.

        Returns:
            bool: True if all required scopes are present in claims.
        """
        ...
