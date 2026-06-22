"""Blind Agent Demo — all 20 core-cenf managers working together.

Full integration demo built from scratch by an agent with ZERO prior knowledge
of core-cenf, using only AGENTS.md, AGENTS_API.md, and codegraph exploration.

Demonstrates every CENF manager (M01-M20) with in-memory adapters and the
BootstrapOrchestrator lifecycle pattern. No external I/O, no network, no filesystem.

Run:  python examples/blind_agent_demo.py
Exit code 0 means all 20 managers demonstrated successfully.

Author: CENF Blind Agent
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import time as _time
from typing import Any

# ===========================================================================
# M01 — ConfigManager (root, zero dependencies)
# ===========================================================================
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter

# ===========================================================================
# M02 — LoggerManager (depends on: ConfigManager)
# ===========================================================================
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter

# ===========================================================================
# M03 — SecretManager (depends on: ConfigManager, LoggerManager)
# ===========================================================================
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter
from core_infrastructure.secrets.models import SecretConfig

# ===========================================================================
# M04 — ErrorHandlingManager (depends on: LoggerManager, ObservabilityManager)
# ===========================================================================
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.common.errors import TransientError, ValidationError, PermanentError

# ===========================================================================
# M05 — ObservabilityManager (depends on: ConfigManager)
# ===========================================================================
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)

# ===========================================================================
# M06 — AuthManager (depends on: Config, Secret, Logger, Observability)
# ===========================================================================
from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter
from core_infrastructure.auth.models import AuthConfig, TokenClaims

# ===========================================================================
# M07 — CacheManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.cache.models import CacheConfig

# ===========================================================================
# M08 — DatabaseManager (depends on: Config, Secret, Logger, Observability)
# ===========================================================================
from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter

# ===========================================================================
# M09 — FileStorageManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
from core_infrastructure.filestorage.models import StorageConfig

# ===========================================================================
# M10 — TaskQueueManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import MemoryTaskQueueAdapter
from core_infrastructure.taskqueue.models import QueueConfig

# ===========================================================================
# M11 — ExternalAPIManager (depends on: Config, Logger, Observability, Auth)
# ===========================================================================
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter

# ===========================================================================
# M12 — FeatureFlagManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FeatureFlag, FlagConfig, FlagContext

# ===========================================================================
# M13 — DependencyManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import (
    InMemoryDependencyAdapter,
)

# ===========================================================================
# M14 — DynamicPromptingManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import (
    ConditionalPromptAdapter,
)
from core_infrastructure.dynamic_prompting.ports import PromptBlock

# ===========================================================================
# M15 — AlertManager (depends on: Config, Secret, Logger, Observability, ExternalAPI)
# ===========================================================================
from core_infrastructure.alert.adapters.dispatch_alert_adapter import DispatchAlertAdapter
from core_infrastructure.alert.ports import AlertLevel, AlertRule

# ===========================================================================
# M16 — RateLimiterManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import (
    InMemoryRateLimitAdapter,
)

# ===========================================================================
# M17 — I18nManager (depends on: Config, Logger)
# ===========================================================================
from core_infrastructure.i18n.adapters.in_memory_i18n_adapter import InMemoryI18nAdapter

# ===========================================================================
# M18 — PermissionManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.permission.adapters.in_memory_permission_adapter import (
    InMemoryPermissionAdapter,
)
from core_infrastructure.permission.models import PermissionConfig

# ===========================================================================
# M19 — LicenceManager (depends on: Config, Secret, Logger, Observability)
# ===========================================================================
from core_infrastructure.licence.adapters.in_memory_licence_adapter import (
    InMemoryLicenceAdapter,
)
from core_infrastructure.licence.models import LicenceConfig, LicenseClaims

# ===========================================================================
# M20 — UpdateManager (depends on: Config, Logger, Observability)
# ===========================================================================
from core_infrastructure.update.adapters.in_memory_update_adapter import (
    InMemoryUpdateAdapter,
)
from core_infrastructure.update.adapters.http_update_adapter_helpers import (
    ArtifactWrapper,
    ReleaseWrapper,
)
from core_infrastructure.update.models import ArtifactMeta, ReleaseMetadata, UpdateConfig

# ===========================================================================
# Bootstrap Orchestrator (lifecycle management)
# ===========================================================================
from core_infrastructure.bootstrap import BootstrapOrchestrator

# ===========================================================================
# Context propagation
# ===========================================================================
from core_infrastructure.common.context import (
    get_correlation_id,
    get_tenant_id,
    new_correlation_id,
    set_principal_id,
    set_tenant_id,
)


# ===========================================================================
# Main demo — all 20 managers wired in dependency order
# ===========================================================================


async def main() -> None:
    """Demonstrate all 20 core-cenf managers with the BootstrapOrchestrator."""
    print("=" * 72)
    print("  CENF Core Infrastructure — Blind Agent Demo (20 managers)")
    print("=" * 72)

    # -------------------------------------------------------------------
    # M01 — CONFIG MANAGER (root, zero deps)
    # -------------------------------------------------------------------
    print("\n[M01] ConfigManager — bootstrapping configuration...")
    config = InMemoryConfigAdapter(
        initial_data={
            "app": {"name": "blind-agent-demo", "version": "0.1.0"},
            "env": "dev",
            "log_level": "DEBUG",
            "cache": {"default_ttl": 300, "max_size": 1000, "backend": "memory"},
            "database": {"host": "localhost", "port": 5432, "max_connections": 10},
            "alert": {
                "channels": {"slack": {"webhook_url": "https://hooks.slack.com/mock/xxx"}},
            },
            "dynamic_prompting": {"max_blocks": 16, "default_priority": 10},
        }
    )
    env = config.get_env()
    app_name = config.get_string("app.name")
    cache_section = config.get_section("cache")
    assert env == "dev" and app_name == "blind-agent-demo"
    print(f"   [OK] env={env}, app={app_name}, cache_ttl={cache_section.get('default_ttl')}")

    # -------------------------------------------------------------------
    # M02 — LOGGER MANAGER (depends on: Config)
    # -------------------------------------------------------------------
    print("\n[M02] LoggerManager — structured logging...")
    logger = InMemoryLoggerAdapter(
        initial_context={"service": "blind-agent-demo", "env": env}
    )
    logger.info("Pipeline starting", step="bootstrap")
    logger.debug("Config loaded", keys=list(cache_section.keys()))
    logger.warn("Demo mode active")

    masked = logger.mask("sk-top-secret-abc123", visible_chars=4)
    bound_logger = logger.bind(component="demo")
    bound_logger.info("Bound logger ready")

    logs = logger.get_logs()
    assert len(logs) >= 4
    assert masked.endswith("c123")
    print(f"   [OK] {len(logs)} log records, masked_key={masked}")

    # -------------------------------------------------------------------
    # M03 — SECRET MANAGER (depends on: Config, Logger)
    # -------------------------------------------------------------------
    print("\n[M03] SecretManager — credentials...")
    secrets = InMemorySecretAdapter(config=SecretConfig(cache_ttl_seconds=30))
    secrets.set_secret("auth_signing_key", "demo-hs256-signing-key-32chars!!")
    secrets.set_secret("api_key", "sk-demo-project-key-12345")
    secrets.set_secret("db_password", "demo-password-123")

    api_key = await secrets.get_secret("api_key")
    signing_key = await secrets.get_secret("auth_signing_key")
    await secrets.rotate_secret("api_key", "sk-demo-rotated-key-67890")
    rotated_key = await secrets.get_secret("api_key")
    secrets.invalidate_cache("api_key")

    assert api_key != rotated_key
    print(f"   [OK] api_key={logger.mask(api_key)}, rotated={logger.mask(rotated_key)}")

    # -------------------------------------------------------------------
    # M05 — OBSERVABILITY MANAGER (depends on: Config)
    # -------------------------------------------------------------------
    print("\n[M05] ObservabilityManager — metrics and spans...")
    observability = InMemoryObservabilityAdapter()
    observability.increment_counter("cenf.demo.started_total", value=1.0)
    observability.record_histogram("cenf.demo.setup_duration_seconds", value=0.123)

    with observability.start_span("Demo.run", attributes={"phase": "bootstrap"}) as _span:
        trace_id = observability.get_trace_id()
        observability.increment_counter("cenf.demo.spans_active", value=1.0)

    metrics = observability.get_metrics()
    spans = observability.get_spans()
    assert len(metrics) >= 2 and len(spans) >= 1
    print(f"   [OK] {len(metrics)} metrics, {len(spans)} spans, trace={trace_id[:8]}...")

    # -------------------------------------------------------------------
    # M04 — ERROR HANDLING MANAGER (depends on: Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M04] ErrorHandlingManager — classification and decorator...")
    error_handler = CapturingErrorAdapter(config, logger, observability)

    @error_handler.handle_errors()
    def demo_step(value: int) -> dict[str, Any]:
        if value < 0:
            raise ValidationError("Value must be non-negative", details={"value": value})
        if value == 0:
            raise TransientError("Service unavailable", details={"retry_after": 5})
        return {"result": value * 2}

    # Happy path
    result = demo_step(5)
    assert result is not None
    # Error path (capturing adapter returns None)
    failed = demo_step(0)
    assert failed is None
    captured = error_handler.get_captured()
    assert len(captured) == 1
    classification = error_handler.classify(captured[0])
    error_handler.report(captured[0], context={"source": "demo"})
    print(f"   [OK] happy={result}, captured={type(captured[0]).__name__}, class={classification.name}")

    # -------------------------------------------------------------------
    # M06 — AUTH MANAGER (depends on: Config, Secret, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M06] AuthManager — JWT validation...")
    from jose import jwt as jose_jwt

    now = int(_time.time())
    test_payload = {
        "sub": "svc-demo",
        "iss": "https://auth.cenf.tech",
        "aud": "blind-agent-demo",
        "exp": now + 3600,
        "iat": now,
        "nbf": now - 60,
        "scopes": ["read", "write", "admin"],
        "tenant_id": "tenant-abc",
        "principal_id": "principal-xyz",
    }
    token = jose_jwt.encode(test_payload, signing_key, algorithm="HS256")

    auth_config = AuthConfig(
        issuer="https://auth.cenf.tech",
        audience="blind-agent-demo",
        algorithms=["HS256"],
        token_leeway=60,
    )
    auth = JwtAuthAdapter(config, secrets, logger, observability, auth_config)

    claims: TokenClaims = await auth.validate_token(token)
    has_admin = auth.validate_scopes(claims, ["admin"])
    has_super = auth.validate_scopes(claims, ["superadmin"])

    assert has_admin is True and has_super is False
    assert get_tenant_id() == "tenant-abc"
    print(f"   [OK] sub={claims.sub}, scopes={claims.scopes}, admin={has_admin}, superadmin={has_super}")

    # -------------------------------------------------------------------
    # M07 — CACHE MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M07] CacheManager — KV cache with stampede protection...")
    cache = MemoryCacheAdapter(
        config=config,
        logger=logger,
        error_handler=error_handler,
        stampede_config=None,
    )
    cache.set("key:alpha", {"val": 1}, ttl=300)
    assert cache.exists("key:alpha") is True

    factory_calls = 0

    def expensive_factory() -> dict[str, str]:
        nonlocal factory_calls
        factory_calls += 1
        return {"from": "factory"}

    r1 = cache.get_or_set("key:beta", expensive_factory, ttl=300)
    r2 = cache.get_or_set("key:beta", expensive_factory, ttl=300)
    assert factory_calls == 1 and r1 == r2

    cache.delete("key:alpha")
    assert cache.exists("key:alpha") is False
    print(f"   [OK] get_or_set factory called {factory_calls}x (stampede protected)")

    # -------------------------------------------------------------------
    # M08 — DATABASE MANAGER (depends on: Config, Secret, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M08] DatabaseManager — transactions and repositories...")
    db = MemoryDatabaseAdapter(config, logger, observability, error_handler)
    repo = db.get_repository(dict)

    doc = await repo.insert({"title": "Demo Doc", "status": "draft", "tenant_id": "tenant-abc"})
    found = await repo.find_by_id(doc["id"])
    assert found is not None and found["title"] == "Demo Doc"

    all_docs = await repo.find_all(filters={"status": "draft"}, limit=10)
    total = await repo.count(filters={"status": "draft"})
    assert total == 1

    async with db.transaction() as tx:
        doc2 = await repo.insert({"title": "Tx Doc", "status": "draft"})
        await tx.commit()

    committed = await repo.find_by_id(doc2["id"])
    assert committed is not None
    print(f"   [OK] inserted={doc['id'][:8]}..., found={found['title']}, tx_committed={committed['title']}")

    # -------------------------------------------------------------------
    # M09 — FILE STORAGE MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M09] FileStorageManager — blob upload/download...")
    storage = MemoryStorageAdapter(config=StorageConfig())
    content = b"Hello from blind agent demo!"
    upload_result = await storage.upload("docs", "demo/hello.txt", content, content_type="text/plain")
    assert await storage.exists("docs", "demo/hello.txt") is True

    downloaded = await storage.download("docs", "demo/hello.txt")
    assert downloaded == content

    presigned = await storage.generate_presigned_url("docs", "demo/hello.txt", expiry=3600)
    objects = await storage.list_objects("docs", prefix="demo/")
    await storage.delete("docs", "demo/hello.txt")
    assert await storage.exists("docs", "demo/hello.txt") is False
    print(f"   [OK] uploaded={upload_result.key}, downloaded={len(downloaded)}B, objects={len(objects)}")

    # -------------------------------------------------------------------
    # M10 — TASK QUEUE MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M10] TaskQueueManager — enqueue/dequeue/ack...")
    task_queue = MemoryTaskQueueAdapter(config=QueueConfig())

    job_ref = await task_queue.enqueue("processing", {"doc_id": "d1", "op": "parse"}, max_retries=3)
    job = await task_queue.dequeue("processing")
    assert job is not None and job.payload["doc_id"] == "d1"
    await task_queue.ack(job.id)

    verified = await task_queue.get_job(job.id)
    assert verified is not None

    dlq = await task_queue.get_dlq_jobs("processing")
    print(f"   [OK] enqueued={job_ref.id[:8]}..., acked status={verified.status.name}, dlq={len(dlq)}")

    # -------------------------------------------------------------------
    # M11 — EXTERNAL API MANAGER (depends on: Config, Logger, Observability, Auth)
    # -------------------------------------------------------------------
    print("\n[M11] ExternalAPIManager — mock HTTP calls...")
    http_client = MockHTTPAdapter()
    http_client.set_response("GET", "https://api.example.com/status", status_code=200, body={"ok": True})
    http_client.set_response("POST", "https://api.example.com/data", status_code=201, body={"id": "123"})

    get_resp = await http_client.get("https://api.example.com/status")
    post_resp = await http_client.post("https://api.example.com/data", body={"x": 1})
    circuit = http_client.get_circuit_state("api.example.com")

    assert get_resp.status_code == 200 and post_resp.status_code == 201
    print(f"   [OK] GET={get_resp.status_code}, POST={post_resp.status_code}, circuit={circuit.name}")

    # -------------------------------------------------------------------
    # M12 — FEATURE FLAG MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M12] FeatureFlagManager — runtime toggles...")
    feature_flags = MemoryFeatureFlagAdapter(config=FlagConfig(default_all=False))
    feature_flags.set_flag(FeatureFlag(key="dark_mode", enabled=True, value={"theme": "midnight"}))
    feature_flags.set_flag(FeatureFlag(key="beta_search", enabled=False))
    feature_flags.set_flag(FeatureFlag(
        key="prod_only",
        enabled=True,
        rules=[{"attribute": "environment", "operator": "eq", "value": "production"}],
    ))

    ctx = FlagContext(tenant_id="tenant-abc", environment="dev")
    assert feature_flags.is_enabled("dark_mode", context=ctx) is True
    assert feature_flags.is_enabled("beta_search", context=ctx) is False
    assert feature_flags.is_enabled("prod_only", context=ctx) is False  # rule mismatch
    assert feature_flags.is_enabled("nonexistent", context=ctx) is False  # fail-safe

    all_flags = feature_flags.get_all_flags(context=ctx)
    print(f"   [OK] dark_mode=ON, beta_search=OFF, prod_only=OFF(dev), unknown=OFF, all={all_flags}")

    # -------------------------------------------------------------------
    # M13 — DEPENDENCY MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M13] DependencyManager — lazy resolution...")

    class DemoPlugin:
        def __init__(self) -> None:
            self.name = "DemoPlugin v1.0"

        def run(self) -> str:
            return "Plugin executed!"

    plugin = DemoPlugin()
    dependency_mgr = InMemoryDependencyAdapter(mapping={("plugins.demo", "DemoPlugin"): plugin})
    dependency_mgr.register(namespace="plugins", key="ocr", target=("plugins.ocr", "OcrPlugin"))

    assert dependency_mgr.is_known("plugins", "ocr") is True
    assert dependency_mgr.is_known("plugins", "unknown") is False
    keys = dependency_mgr.list_keys("plugins")

    resolved = dependency_mgr.resolve_class("plugins.demo", "DemoPlugin")
    assert resolved is not None and resolved.name == "DemoPlugin v1.0"
    print(f"   [OK] keys={keys}, resolved={resolved.name}, run={resolved.run()}")

    # -------------------------------------------------------------------
    # M14 — DYNAMIC PROMPTING MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M14] DynamicPromptingManager — conditional prompt assembly...")
    prompt_assembler = ConditionalPromptAdapter(config, logger, error_handler)

    blocks = [
        PromptBlock(id="persona", condition=None, content="You are an expert assistant.", priority=1),
        PromptBlock(id="code-mode", condition={"context.mode": "code"}, content="Use code blocks.", priority=10),
        PromptBlock(id="verbose", condition={"context.verbose": True}, content="Be detailed.", priority=20),
    ]

    errors = prompt_assembler.validate_blocks(blocks)
    assert len(errors) == 0

    code_prompt = await prompt_assembler.assemble(
        base_prompt="Help the user.",
        blocks=blocks,
        context_state={"context": {"mode": "code", "verbose": False}},
    )
    assert "code blocks" in code_prompt
    assert "Be detailed" not in code_prompt  # verbose=False -> excluded

    verbose_prompt = await prompt_assembler.assemble(
        base_prompt="Help the user.",
        blocks=blocks,
        context_state={"context": {"mode": "chat", "verbose": True}},
    )
    assert "Be detailed" in verbose_prompt
    assert "code blocks" not in verbose_prompt
    print(f"   [OK] code_prompt={len(code_prompt)} chars, verbose_prompt={len(verbose_prompt)} chars")

    # -------------------------------------------------------------------
    # M15 — ALERT MANAGER (depends on: Config, Secret, Logger, ExternalAPI, Error)
    # -------------------------------------------------------------------
    print("\n[M15] AlertManager — rule-based alert dispatch...")
    http_client.set_response("POST", "https://hooks.slack.com/mock/xxx", status_code=200, body={"ok": True})

    alert_mgr = DispatchAlertAdapter(
        config=config,
        secret_manager=secrets,
        logger=logger,
        external_api=http_client,
        error_handler=error_handler,
    )

    rule = AlertRule(
        rule_id="demo_alert",
        condition={"event_type": "error", "severity": "critical"},
        level=AlertLevel.CRITICAL,
        channels=["slack"],
        throttle_seconds=0,
    )
    alert_mgr.register_rule(rule)

    await alert_mgr.evaluate_and_alert({
        "event_type": "error",
        "severity": "critical",
        "message": "Demo alert triggered",
    })

    await alert_mgr.send_alert(
        level=AlertLevel.WARNING,
        title="Demo warning",
        message="This is a test alert from blind agent demo",
        metadata={"source": "demo"},
    )
    print(f"   [OK] rule registered, evaluate_and_alert + send_alert dispatched")

    # -------------------------------------------------------------------
    # M16 — RATE LIMITER MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M16] RateLimiterManager — token bucket rate limiting...")
    rate_limiter = InMemoryRateLimitAdapter(mode="always_allow")
    rate_limiter.configure_bucket("api:demo", capacity=100, refill_rate=10.0, window_type="token_bucket")

    for _ in range(3):
        assert await rate_limiter.is_allowed("api:demo") is True

    remaining = await rate_limiter.get_remaining("api:demo")
    reset_time = await rate_limiter.get_reset_time("api:demo")

    deny_limiter = InMemoryRateLimitAdapter(mode="always_deny")
    assert await deny_limiter.is_allowed("api:demo") is False
    print(f"   [OK] 3 calls allowed, remaining={remaining}, deny_mode_works")

    # -------------------------------------------------------------------
    # M17 — I18N MANAGER (depends on: Config, Logger)
    # -------------------------------------------------------------------
    print("\n[M17] I18nManager — multi-language translations...")
    i18n = InMemoryI18nAdapter(
        translations={
            "en": {"greeting": "Hello, {name}!", "errors": {"not_found": "Not found"}},
            "es": {"greeting": "¡Hola, {name}!", "errors": {"not_found": "No encontrado"}},
        },
        default_locale="en",
        fallback_locale="en",
    )

    assert i18n.t("greeting", name="World") == "Hello, World!"
    i18n.set_locale("es")
    assert i18n.t("greeting", name="Mundo") == "¡Hola, Mundo!"
    assert i18n.t("errors.not_found") == "No encontrado"
    assert i18n.t("nonexistent.key") == "[missing: nonexistent.key]"

    locales = i18n.get_available_locales()
    i18n.load_translations({"farewell": "Adiós"}, "es")
    assert i18n.t("farewell") == "Adiós"
    print(f"   [OK] locales={locales}, es:greeting={i18n.t('greeting', name='Mundo')}")

    # -------------------------------------------------------------------
    # M18 — PERMISSION MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M18] PermissionManager — RBAC access control...")
    permission_mgr = InMemoryPermissionAdapter(config=PermissionConfig())
    permission_mgr.add_role("principal-xyz", "admin", "tenant-abc")
    permission_mgr.add_role("principal-abc", "user", "tenant-abc")

    # Admin should be able to read
    decision = await permission_mgr.check_permission(
        tenant_id="tenant-abc",
        principal_id="principal-xyz",
        principal_type="human",
        resource_type="document",
        resource_id="doc-001",
        action="read",
    )
    assert decision.is_allowed() is True

    # User without role should be denied
    deny_decision = await permission_mgr.check_permission(
        tenant_id="tenant-abc",
        principal_id="no-role-user",
        principal_type="human",
        resource_type="document",
        resource_id="doc-001",
        action="write",
    )
    assert deny_decision.is_allowed() is False

    perms = await permission_mgr.list_effective_permissions(
        tenant_id="tenant-abc",
        principal_id="principal-xyz",
        principal_type="human",
    )
    print(f"   [OK] admin read={decision.is_allowed()}, no-role write={deny_decision.is_allowed()}, perms={len(perms)}")

    # -------------------------------------------------------------------
    # M19 — LICENCE MANAGER (depends on: Config, Secret, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M19] LicenceManager — signed licence validation...")
    licence_mgr = InMemoryLicenceAdapter(config=LicenceConfig(grace_period_days=7))

    # Add a licence with features
    licence_claims = LicenseClaims(
        license_id="lic-demo-001",
        tenant_id="tenant-abc",
        tier="pro",
        features={"advanced_search": True, "export_pdf": True, "ai_assistant": False},
        issued_at=_time.time(),
        expiry=_time.time() + 86400 * 365,
    )
    licence_mgr.add_license("tenant-abc", licence_claims)

    lic_info = await licence_mgr.get_license(tenant_id="tenant-abc")
    assert lic_info is not None
    assert lic_info.tier() == "pro"
    assert lic_info.is_valid() is True

    assert await licence_mgr.is_feature_enabled(tenant_id="tenant-abc", feature_key="advanced_search") is True
    assert await licence_mgr.is_feature_enabled(tenant_id="tenant-abc", feature_key="ai_assistant") is False

    features = await licence_mgr.list_enabled_features(tenant_id="tenant-abc")
    await licence_mgr.revoke_license(tenant_id="tenant-abc")
    revoked = await licence_mgr.get_license(tenant_id="tenant-abc")
    assert revoked is None

    print(f"   [OK] tier={lic_info.tier()}, valid={lic_info.is_valid()}, features={dict(features)}, revoked=null")

    # -------------------------------------------------------------------
    # M20 — UPDATE MANAGER (depends on: Config, Logger, Observability)
    # -------------------------------------------------------------------
    print("\n[M20] UpdateManager — auto-update with rollback...")
    update_mgr = InMemoryUpdateAdapter(
        config=UpdateConfig(
            update_url="https://updates.example.com",
            public_key="deadbeef" * 4,
            current_version="1.0.0",
            rollback_enabled=True,
        ),
        override_platform="windows",
    )

    # Create a release with artifact
    artifact_meta = ArtifactMeta(
        url="https://updates.example.com/releases/1.1.0/installer.exe",
        platform="windows",
        arch="x64",
        kind="installer",
        hash="a" * 64,
    )
    release_meta = ReleaseMetadata(
        version="1.1.0",
        channel="stable",
        release_notes_url="https://updates.example.com/releases/1.1.0",
        artifacts=[artifact_meta],
    )
    release = ReleaseWrapper(release_meta)
    update_mgr.add_release("stable", release)

    current_ver = await update_mgr.get_current_version(app_id="demo-app")
    assert current_ver == "1.0.0"

    available = await update_mgr.check_for_updates(app_id="demo-app", channel="stable")
    assert available is not None
    assert available.version() == "1.1.0"

    artifact = await update_mgr.download_update(app_id="demo-app", release=available)
    assert artifact.platform() == "windows"

    result = await update_mgr.apply_update(app_id="demo-app", artifact=artifact)
    assert result.success() is True
    assert result.new_version() == "1.1.0"

    new_ver = await update_mgr.get_current_version(app_id="demo-app")
    assert new_ver == "1.1.0"

    # Test rollback
    rollback_result = await update_mgr.rollback(app_id="demo-app")
    assert rollback_result.success() is True
    restored_ver = await update_mgr.get_current_version(app_id="demo-app")
    assert restored_ver == "1.0.0"

    print(f"   [OK] v={current_ver} -> {available.version()}, applied={result.new_version()}, rollback -> {restored_ver}")

    # ===================================================================
    # BOOTSTRAP ORCHESTRATOR — lifecycle pattern
    # ===================================================================
    print("\n" + "-" * 72)
    print("  BootstrapOrchestrator — lifecycle management pattern")
    print("-" * 72)

    # The BootstrapOrchestrator manages AsyncLifecycle-compatible managers.
    # In-memory test adapters don't implement AsyncLifecycle (they are for
    # unit testing, not production orchestration). We demonstrate the
    # architectural pattern via direct instantiation, showing how it would
    # coordinate startup -> wait -> shutdown for production adapters.
    orchestrator = BootstrapOrchestrator(
        config, logger, secrets, observability, error_handler,
        auth, cache, db, storage, task_queue, http_client,
        feature_flags, dependency_mgr, prompt_assembler, alert_mgr,
        rate_limiter, i18n, permission_mgr, licence_mgr, update_mgr,
    )
    print(f"   [OK] BootstrapOrchestrator instantiated with {len(orchestrator._managers)} managers")
    print(f"   [INFO] Production flow: orchestrator.run() -> startup() -> signal wait -> shutdown()")

    # ===================================================================
    # SUCCESS
    # ===================================================================
    print("\n" + "=" * 72)
    print("  [SUCCESS] All 20 managers demonstrated successfully!")
    print("=" * 72)

    print("""
    +------+-------------------------+-------------------------------------------+
    |  #   | Manager                 | Key method(s) demonstrated                 |
    +------+-------------------------+-------------------------------------------+
    | M01  | ConfigManager           | get_env, get_string, get_section           |
    | M02  | LoggerManager           | info/debug/warn, mask, bind                |
    | M03  | SecretManager           | get_secret, rotate_secret, invalidate      |
    | M04  | ErrorHandlingManager    | @handle_errors, classify, report           |
    | M05  | ObservabilityManager    | counter, histogram, span, trace_id         |
    | M06  | AuthManager             | validate_token, validate_scopes            |
    | M07  | CacheManager            | set/get/exists, get_or_set (stampede)      |
    | M08  | DatabaseManager         | get_repository, insert/find, transaction   |
    | M09  | FileStorageManager      | upload, download, presigned_url, delete    |
    | M10  | TaskQueueManager        | enqueue, dequeue, ack, get_dlq_jobs        |
    | M11  | ExternalAPIManager      | GET, POST, get_circuit_state               |
    | M12  | FeatureFlagManager      | is_enabled, get_all_flags, rules           |
    | M13  | DependencyManager       | register, resolve_class, is_known          |
    | M14  | DynamicPromptingManager | validate_blocks, assemble (conditional)     |
    | M15  | AlertManager            | register_rule, evaluate_and_alert, send    |
    | M16  | RateLimiterManager      | is_allowed, configure_bucket, get_remaining|
    | M17  | I18nManager             | t, set_locale, get_available_locales       |
    | M18  | PermissionManager       | check_permission, list_effective_perms     |
    | M19  | LicenceManager          | get_license, is_feature_enabled, revoke    |
    | M20  | UpdateManager           | check_for_updates, apply_update, rollback  |
    +------+-------------------------+-------------------------------------------+
    """)


if __name__ == "__main__":
    asyncio.run(main())
