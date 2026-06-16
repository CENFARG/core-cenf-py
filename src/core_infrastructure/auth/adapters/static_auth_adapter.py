"""StaticAuthAdapter — AuthManager test double returning always-valid claims.

Returns configurable TokenClaims for ANY token input. Used in unit tests
where real JWT validation would be an unnecessary dependency. Sets
tenant_id and principal_id contextvars from the configured claims.

Security: This adapter performs NO real validation. NEVER use it in
    production code paths.
Observability: No RED metrics emitted — this is a test-only adapter.
@ai-directive: This adapter exists solely for testing. It accepts ANY
    token input and returns the configured claims without verification.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from core_infrastructure.auth.models import TokenClaims
from core_infrastructure.common.context import set_principal_id, set_tenant_id


class StaticAuthAdapter:
    """AuthManager test double with always-valid configurable claims.

    Accepts any token string and returns the configured TokenClaims
    without performing real JWT validation. Ideal for unit testing
    downstream components that depend on AuthManager.

    Args:
        default_claims: The TokenClaims to return for all tokens.

    Usage::

        claims = TokenClaims(sub="test", iss="mock", aud="test", exp=99, iat=1)
        auth = StaticAuthAdapter(default_claims=claims)
        result = await auth.validate_token("any-string")
        assert result.sub == "test"
    """

    def __init__(self, default_claims: TokenClaims) -> None:
        self._default_claims = default_claims

    # ------------------------------------------------------------------
    # Public API — AuthManager Protocol
    # ------------------------------------------------------------------

    async def validate_token(self, token: str) -> TokenClaims:
        """Return configured claims for any token (NO real validation).

        Sets tenant_id and principal_id contextvars from the claims.

        Args:
            token: Any string — ignored by this adapter.

        Returns:
            TokenClaims: The configured default claims.
        """
        claims = self._default_claims
        if claims.tenant_id:
            set_tenant_id(claims.tenant_id)
        if claims.principal_id:
            set_principal_id(claims.principal_id)
        return claims

    async def get_claims(self, token: str) -> TokenClaims:
        """Return configured claims (same as validate_token).

        Args:
            token: Any string — ignored.

        Returns:
            TokenClaims: The configured default claims.
        """
        return self._default_claims

    async def refresh_jwks(self) -> None:
        """No-op — static adapter has no JWKS.

        Exists to satisfy the AuthManager Protocol.
        """

    def validate_scopes(self, claims: TokenClaims, required: list[str]) -> bool:
        """Check if token claims contain all required scopes.

        Args:
            claims: The token claims to check.
            required: List of scope strings that must all be present.

        Returns:
            bool: True if all required scopes are present.
        """
        claim_scopes = set(claims.scopes)
        return all(scope in claim_scopes for scope in required)
