"""Unit tests for StaticAuthAdapter — test double for AuthManager.

Tests cover:
- Returns always-valid configurable claims
- Contextvars propagation (tenant_id, principal_id)
- Protocol compliance (satisfies AuthManager)
- Scope validation

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import pytest

from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter
from core_infrastructure.auth.models import TokenClaims
from core_infrastructure.auth.ports import AuthManager
from core_infrastructure.common.context import get_principal_id, get_tenant_id


@pytest.fixture
def static_auth() -> StaticAuthAdapter:
    """Create a StaticAuthAdapter with default claims."""
    default_claims = TokenClaims(
        sub="static-user",
        iss="https://static.test.cenf.tech",
        aud="static-api",
        exp=9999999999,
        iat=1,
        scopes=["read:users", "write:users"],
        tenant_id="static-tenant",
        principal_id="static-principal",
    )
    return StaticAuthAdapter(default_claims=default_claims)


class TestStaticAuthAdapterProtocol:
    """Verify StaticAuthAdapter satisfies AuthManager Protocol."""

    def test_satisfies_protocol(self, static_auth: StaticAuthAdapter) -> None:
        """StaticAuthAdapter passes isinstance check."""
        assert isinstance(static_auth, AuthManager)

    def test_has_all_required_methods(self, static_auth: StaticAuthAdapter) -> None:
        """Adapter exposes validate_token, get_claims, refresh_jwks, validate_scopes."""
        assert callable(static_auth.validate_token)
        assert callable(static_auth.get_claims)
        assert callable(static_auth.refresh_jwks)
        assert callable(static_auth.validate_scopes)


class TestStaticAuthValidation:
    """Verify validate_token always returns configured claims."""

    @pytest.mark.asyncio
    async def test_validate_token_any_input(self, static_auth: StaticAuthAdapter) -> None:
        """validate_token() accepts any token string and returns configured claims."""
        claims = await static_auth.validate_token("any-token-value")
        assert claims.sub == "static-user"
        assert claims.iss == "https://static.test.cenf.tech"
        assert claims.tenant_id == "static-tenant"
        assert claims.principal_id == "static-principal"

    @pytest.mark.asyncio
    async def test_validate_token_empty_string(self, static_auth: StaticAuthAdapter) -> None:
        """validate_token() accepts empty string as token."""
        claims = await static_auth.validate_token("")
        assert isinstance(claims, TokenClaims)
        assert claims.sub == "static-user"

    @pytest.mark.asyncio
    async def test_get_claims_same_as_validate(self, static_auth: StaticAuthAdapter) -> None:
        """get_claims() returns same as validate_token()."""
        v_claims = await static_auth.validate_token("t1")
        g_claims = await static_auth.get_claims("t1")
        assert v_claims.sub == g_claims.sub
        assert v_claims.tenant_id == g_claims.tenant_id

    @pytest.mark.asyncio
    async def test_validate_token_sets_contextvars(self, static_auth: StaticAuthAdapter) -> None:
        """validate_token() sets tenant_id and principal_id contextvars."""
        await static_auth.validate_token("any-token")
        assert get_tenant_id() == "static-tenant"
        assert get_principal_id() == "static-principal"


class TestStaticAuthScopeValidation:
    """Verify scope validation on static adapter."""

    def test_scopes_present(self, static_auth: StaticAuthAdapter) -> None:
        """validate_scopes() returns True for scopes in default claims."""
        claims = TokenClaims(
            sub="s", iss="i", aud="a", exp=9, iat=1,
            scopes=["read:users"],
        )
        assert static_auth.validate_scopes(claims, ["read:users"]) is True

    def test_scopes_missing(self, static_auth: StaticAuthAdapter) -> None:
        """validate_scopes() returns False for missing scopes."""
        claims = TokenClaims(
            sub="s", iss="i", aud="a", exp=9, iat=1,
            scopes=["read:users"],
        )
        assert static_auth.validate_scopes(claims, ["admin"]) is False


class TestStaticAuthRefreshJwks:
    """Verify refresh_jwks is a no-op."""

    @pytest.mark.asyncio
    async def test_refresh_jwks_no_op(self, static_auth: StaticAuthAdapter) -> None:
        """refresh_jwks() completes without error."""
        await static_auth.refresh_jwks()
        # No assertion needed — if it raises, the test fails
