"""Unit tests for AuthManager Protocol and TokenClaims Pydantic model.

Tests cover:
- AuthManager Protocol contract (validate_token, get_claims, refresh_jwks, validate_scopes)
- Protocol is runtime-checkable
- TokenClaims Pydantic model validation and defaults
- AuthConfig Pydantic model validation

Author: CENF AI Team
Version: 0.1.0
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from core_infrastructure.auth.models import AuthConfig, TokenClaims
from core_infrastructure.auth.ports import AuthManager


class TestAuthManagerProtocol:
    """Verify AuthManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """AuthManager Protocol is decorated with @runtime_checkable."""
        assert hasattr(AuthManager, "_is_runtime_protocol") or hasattr(
            AuthManager, "__protocol_attrs__"
        )

    def test_has_validate_token_method(self) -> None:
        """Protocol requires validate_token(token) -> TokenClaims."""
        assert hasattr(AuthManager, "validate_token")

    def test_has_get_claims_method(self) -> None:
        """Protocol requires get_claims(token) -> TokenClaims."""
        assert hasattr(AuthManager, "get_claims")

    def test_has_refresh_jwks_method(self) -> None:
        """Protocol requires refresh_jwks() -> None."""
        assert hasattr(AuthManager, "refresh_jwks")

    def test_has_validate_scopes_method(self) -> None:
        """Protocol requires validate_scopes(claims, required) -> bool."""
        assert hasattr(AuthManager, "validate_scopes")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all AuthManager methods satisfies the protocol."""

        class ValidAuth:
            async def validate_token(self, token: str): ...
            async def get_claims(self, token: str): ...
            async def refresh_jwks(self) -> None: ...
            def validate_scopes(self, claims, required) -> bool: ...

        assert isinstance(ValidAuth(), AuthManager)

    def test_class_missing_validate_token_fails_protocol(self) -> None:
        """A class without validate_token() does NOT satisfy AuthManager."""

        class Incomplete:
            async def get_claims(self, token: str): ...

        assert not isinstance(Incomplete(), AuthManager)


class TestTokenClaimsModel:
    """Verify TokenClaims Pydantic model validation."""

    def test_valid_claims_construction(self) -> None:
        """TokenClaims can be constructed with required fields."""
        claims = TokenClaims(
            sub="user-123",
            iss="https://auth.example.com",
            aud="cenf-api",
            exp=9999999999,
            iat=1111111111,
            scopes=["read:users"],
            tenant_id="tenant-abc",
            principal_id="principal-xyz",
        )
        assert claims.sub == "user-123"
        assert claims.iss == "https://auth.example.com"
        assert claims.aud == "cenf-api"
        assert claims.scopes == ["read:users"]
        assert claims.tenant_id == "tenant-abc"
        assert claims.principal_id == "principal-xyz"

    def test_default_values(self) -> None:
        """TokenClaims has sensible defaults for optional fields."""
        claims = TokenClaims(
            sub="user-1",
            iss="issuer-1",
            aud="audience-1",
            exp=9999999999,
            iat=1111111111,
        )
        assert claims.nbf is None
        assert claims.scopes == []
        assert claims.tenant_id == ""
        assert claims.principal_id == ""

    def test_empty_sub_fails(self) -> None:
        """sub must not be empty."""
        with pytest.raises(PydanticValidationError):
            TokenClaims(
                sub="",
                iss="i",
                aud="a",
                exp=9999999999,
                iat=1111111111,
            )

    def test_empty_iss_fails(self) -> None:
        """iss must not be empty."""
        with pytest.raises(PydanticValidationError):
            TokenClaims(
                sub="s",
                iss="",
                aud="a",
                exp=9999999999,
                iat=1111111111,
            )

    def test_empty_aud_fails(self) -> None:
        """aud must not be empty."""
        with pytest.raises(PydanticValidationError):
            TokenClaims(
                sub="s",
                iss="i",
                aud="",
                exp=9999999999,
                iat=1111111111,
            )

    def test_negative_exp_fails(self) -> None:
        """exp must be a positive timestamp."""
        with pytest.raises(PydanticValidationError):
            TokenClaims(
                sub="s",
                iss="i",
                aud="a",
                exp=-1,
                iat=1111111111,
            )

    def test_tenant_id_max_length(self) -> None:
        """tenant_id respects max_length=64."""
        claims = TokenClaims(
            sub="s",
            iss="i",
            aud="a",
            exp=9999999999,
            iat=1111111111,
            tenant_id="x" * 64,
        )
        assert len(claims.tenant_id) == 64

    def test_tenant_id_too_long_fails(self) -> None:
        """tenant_id > 64 chars fails validation."""
        with pytest.raises(PydanticValidationError):
            TokenClaims(
                sub="s",
                iss="i",
                aud="a",
                exp=9999999999,
                iat=1111111111,
                tenant_id="x" * 65,
            )


class TestAuthConfigModel:
    """Verify AuthConfig Pydantic model validation."""

    def test_default_config(self) -> None:
        """AuthConfig creates with sensible defaults."""
        config = AuthConfig()
        assert config.issuer == ""
        assert config.audience == ""
        assert config.jwks_url == ""
        assert config.algorithms == ["HS256"]
        assert config.token_leeway == 60

    def test_custom_algorithms(self) -> None:
        """AuthConfig accepts custom algorithm list."""
        config = AuthConfig(algorithms=["RS256", "HS256"])
        assert config.algorithms == ["RS256", "HS256"]

    def test_token_leeway_negative_fails(self) -> None:
        """token_leeway must be >= 0."""
        with pytest.raises(PydanticValidationError):
            AuthConfig(token_leeway=-1)

    def test_empty_algorithms_fails(self) -> None:
        """algorithms must have at least one entry."""
        with pytest.raises(PydanticValidationError):
            AuthConfig(algorithms=[])
