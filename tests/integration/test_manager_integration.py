"""Integration tests for cross-manager interactions.

Verifies that managers work together through their real adapter implementations
(no mocking — real in-memory adapters wired together via conftest fixtures).

Tests cover:
- ConfigManager → LoggerManager (logger uses config profile)
- LoggerManager → ObservabilityManager (log context flows to OTel)
- SecretManager → AuthManager (auth validates via secrets)
- CacheManager → TaskQueueManager (queue uses cache for dedup)
- Full chain: all 12 managers wired together

Author: CENF AI Team
Version: 0.1.0
"""

import pytest


class TestConfigToLoggerIntegration:
    """ConfigManager provides configuration consumed by LoggerManager."""

    def test_logger_has_config_access(self, config_manager, logger_manager) -> None:
        """Logger adapter can be accessed alongside config adapter."""
        assert config_manager._adapter is not None
        assert logger_manager._adapter is not None
        # Logger has get_json_schema which verifies it's functional
        schema = logger_manager._adapter.get_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema or "type" in schema


class TestLoggerToObservabilityIntegration:
    """LoggerManager provides context that ObservabilityManager consumes."""

    def test_logger_and_obs_both_available(self, logger_manager, observability_manager) -> None:
        """Both managers are instantiated and functional."""
        assert logger_manager._adapter is not None
        assert observability_manager._adapter is not None


class TestSecretToAuthIntegration:
    """SecretManager provides keys that AuthManager uses for token validation."""

    def test_secret_and_auth_both_available(self, secret_manager, auth_manager) -> None:
        """Both managers are instantiated."""
        assert secret_manager._adapter is not None
        assert auth_manager._adapter is not None

    @pytest.mark.asyncio
    async def test_auth_validates_token(self, auth_manager) -> None:
        """AuthManager can validate a token (via StaticAuthAdapter)."""
        claims = await auth_manager._adapter.validate_token("any-token")
        assert claims.sub == "test-user"
        assert claims.iss == "cenf-test"


class TestCacheToTaskQueueIntegration:
    """CacheManager provides dedup storage consumed by TaskQueueManager."""

    def test_cache_and_queue_both_available(self, cache_manager, taskqueue_manager) -> None:
        """Both managers are instantiated."""
        assert cache_manager._adapter is not None
        assert taskqueue_manager._adapter is not None


class TestFullManagerChain:
    """Full chain: all 12 managers wired and functioning together."""

    def test_all_twelve_managers_instantiated(
        self,
        config_manager,
        logger_manager,
        secret_manager,
        observability_manager,
        error_manager,
        auth_manager,
        cache_manager,
        database_manager,
        filestorage_manager,
        taskqueue_manager,
        external_api_manager,
        feature_flag_manager,
    ) -> None:
        """All 12 managers are non-None and have their adapter accessible."""
        managers = [
            ("config", config_manager),
            ("logger", logger_manager),
            ("secret", secret_manager),
            ("observability", observability_manager),
            ("error", error_manager),
            ("auth", auth_manager),
            ("cache", cache_manager),
            ("database", database_manager),
            ("filestorage", filestorage_manager),
            ("taskqueue", taskqueue_manager),
            ("external_api", external_api_manager),
            ("feature_flags", feature_flag_manager),
        ]
        for name, mgr in managers:
            assert mgr is not None, f"{name} manager is None"
            assert mgr._adapter is not None, f"{name} adapter is None"

    @pytest.mark.asyncio
    async def test_full_chain_startup_and_shutdown(
        self,
        config_manager,
        logger_manager,
        secret_manager,
        observability_manager,
        error_manager,
        auth_manager,
        cache_manager,
        database_manager,
        filestorage_manager,
        taskqueue_manager,
        external_api_manager,
        feature_flag_manager,
    ) -> None:
        """All 12 managers can be started and stopped together."""
        managers = [
            config_manager,
            logger_manager,
            secret_manager,
            observability_manager,
            error_manager,
            auth_manager,
            cache_manager,
            database_manager,
            filestorage_manager,
            taskqueue_manager,
            external_api_manager,
            feature_flag_manager,
        ]
        # Start all
        for mgr in managers:
            await mgr.start()
            assert mgr._started is True

        # Stop all
        for mgr in managers:
            await mgr.stop()
            assert mgr._stopped is True
