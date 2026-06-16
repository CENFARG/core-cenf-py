"""Unit tests for SecretManager Protocol and SecretRef/SecretValue/SecretConfig models.

Tests cover:
- SecretManager Protocol contract (all required methods present)
- SecretManager Protocol is runtime-checkable
- SecretValue.__repr__ is masked (never exposes raw secret)
- SecretRef model validation (key length, structure)
- SecretConfig TTL and cache settings

Author: CENF AI Team
Version: 0.1.0
"""

import json

import pytest
from pydantic import ValidationError as PydanticValidationError


class TestSecretManagerProtocol:
    """Verify SecretManager Protocol defines all required methods."""

    def test_protocol_is_runtime_checkable(self) -> None:
        """SecretManager Protocol is decorated with @runtime_checkable."""
        from core_infrastructure.secrets.ports import SecretManager

        assert hasattr(SecretManager, "_is_runtime_protocol") or hasattr(
            SecretManager, "__protocol_attrs__"
        )

    def test_has_get_secret_method(self) -> None:
        """Protocol requires async get_secret(key) -> str."""
        from core_infrastructure.secrets.ports import SecretManager

        assert hasattr(SecretManager, "get_secret")

    def test_has_invalidate_cache_method(self) -> None:
        """Protocol requires invalidate_cache(key=None)."""
        from core_infrastructure.secrets.ports import SecretManager

        assert hasattr(SecretManager, "invalidate_cache")

    def test_has_rotate_secret_method(self) -> None:
        """Protocol requires async rotate_secret(key, new_value)."""
        from core_infrastructure.secrets.ports import SecretManager

        assert hasattr(SecretManager, "rotate_secret")

    def test_has_get_json_schema_method(self) -> None:
        """Protocol requires get_json_schema() -> dict."""
        from core_infrastructure.secrets.ports import SecretManager

        assert hasattr(SecretManager, "get_json_schema")

    def test_class_with_all_methods_satisfies_protocol(self) -> None:
        """A class implementing all SecretManager methods satisfies the protocol."""
        from core_infrastructure.secrets.ports import SecretManager

        class ValidSecretManager:
            async def get_secret(self, key: str) -> str: ...
            def invalidate_cache(self, key: str | None = None) -> None: ...
            async def rotate_secret(self, key: str, new_value: str) -> None: ...
            def get_json_schema(self) -> dict: ...

        assert isinstance(ValidSecretManager(), SecretManager)

    def test_class_missing_get_secret_fails_protocol(self) -> None:
        """A class without get_secret() does NOT satisfy SecretManager."""
        from core_infrastructure.secrets.ports import SecretManager

        class IncompleteManager:
            def invalidate_cache(self) -> None: ...

        assert not isinstance(IncompleteManager(), SecretManager)


class TestSecretRefModel:
    """Verify SecretRef Pydantic model validation."""

    def test_secret_ref_minimal(self) -> None:
        """SecretRef creates with just a key."""
        from core_infrastructure.secrets.models import SecretRef

        ref = SecretRef(key="db_password")
        assert ref.key == "db_password"
        assert ref.namespace == "default"

    def test_secret_ref_with_namespace(self) -> None:
        """SecretRef accepts a custom namespace."""
        from core_infrastructure.secrets.models import SecretRef

        ref = SecretRef(key="api_key", namespace="external_api")
        assert ref.key == "api_key"
        assert ref.namespace == "external_api"

    def test_secret_ref_key_required(self) -> None:
        """SecretRef requires a non-empty key."""
        from core_infrastructure.secrets.models import SecretRef

        with pytest.raises(PydanticValidationError):
            SecretRef(key="")

    def test_secret_ref_key_max_length(self) -> None:
        """SecretRef key has max length validation."""
        from core_infrastructure.secrets.models import SecretRef

        with pytest.raises(PydanticValidationError):
            SecretRef(key="x" * 257)


class TestSecretValueModel:
    """Verify SecretValue masks raw secret in __repr__."""

    def test_repr_is_masked(self) -> None:
        """SecretValue.__repr__ MUST NOT expose raw secret value."""
        from core_infrastructure.secrets.models import SecretValue

        sv = SecretValue(value="super-secret-password-123")
        rep = repr(sv)
        assert "super-secret-password-123" not in rep

    def test_repr_shows_type_info(self) -> None:
        """SecretValue.__repr__ shows the class name and length hint."""
        from core_infrastructure.secrets.models import SecretValue

        sv = SecretValue(value="abcdefgh")
        rep = repr(sv)
        assert "SecretValue" in rep

    def test_value_still_accessible_via_attribute(self) -> None:
        """The raw value is still accessible via .value for programmatic use."""
        from core_infrastructure.secrets.models import SecretValue

        sv = SecretValue(value="real-secret")
        assert sv.value == "real-secret"

    def test_empty_value_repr_safe(self) -> None:
        """SecretValue with empty value has safe repr."""
        from core_infrastructure.secrets.models import SecretValue

        sv = SecretValue(value="")
        rep = repr(sv)
        assert "SecretValue" in rep


class TestSecretConfigModel:
    """Verify SecretConfig Pydantic model with TTL settings."""

    def test_default_ttl(self) -> None:
        """SecretConfig has a sensible default TTL."""
        from core_infrastructure.secrets.models import SecretConfig

        config = SecretConfig()
        assert config.cache_ttl_seconds > 0

    def test_custom_ttl(self) -> None:
        """SecretConfig accepts custom TTL values."""
        from core_infrastructure.secrets.models import SecretConfig

        config = SecretConfig(cache_ttl_seconds=600)
        assert config.cache_ttl_seconds == 600

    def test_ttl_must_be_positive(self) -> None:
        """TTL must be at least 1 second."""
        from core_infrastructure.secrets.models import SecretConfig

        with pytest.raises(PydanticValidationError):
            SecretConfig(cache_ttl_seconds=0)

    def test_fernet_key_field(self) -> None:
        """SecretConfig has a fernet_key field for local encryption."""
        from core_infrastructure.secrets.models import SecretConfig

        config = SecretConfig(fernet_key="test-key-material-here")
        assert config.fernet_key == "test-key-material-here"

    def test_model_json_schema_is_valid(self) -> None:
        """SecretConfig.model_json_schema() returns valid JSON Schema."""
        from core_infrastructure.secrets.models import SecretConfig

        schema = SecretConfig.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        json_str = json.dumps(schema)
        assert len(json_str) > 0
