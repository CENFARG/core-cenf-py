"""Full demo: all 16 core-cenf managers working together.

Document Processing Pipeline -- demonstrates the integration pattern for
every core-cenf horizontal transversal manager. Uses in-memory adapters
exclusively (no external I/O, no network, no filesystem).

Run:  python examples/full_demo.py
Exit code 0 means all managers demonstrated successfully.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import time as _time
from typing import Any

# ---------------------------------------------------------------------------
# 1. ConfigManager -- configuration from env vars (InMemoryConfigAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter

# ---------------------------------------------------------------------------
# 2. LoggerManager -- structured logging (InMemoryLoggerAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter

# ---------------------------------------------------------------------------
# 3. SecretManager -- credential retrieval (InMemorySecretAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter
from core_infrastructure.secrets.models import SecretConfig

# ---------------------------------------------------------------------------
# 4. ObservabilityManager -- metrics and tracing (InMemoryObservabilityAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)

# ---------------------------------------------------------------------------
# 5. ErrorHandlingManager -- classification and decorator (CapturingErrorAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.common.errors import TransientError, ValidationError

# ---------------------------------------------------------------------------
# 6. AuthManager -- JWT validation and claims extraction (JwtAuthAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter
from core_infrastructure.auth.models import AuthConfig, TokenClaims

# ---------------------------------------------------------------------------
# 7. CacheManager -- key-value cache with stampede protection (MemoryCacheAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
from core_infrastructure.cache.models import StampedeConfig

# ---------------------------------------------------------------------------
# 8. DatabaseManager -- transactional document records (MemoryDatabaseAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter

# ---------------------------------------------------------------------------
# 9. FileStorageManager -- upload/download documents (MemoryStorageAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
from core_infrastructure.filestorage.models import StorageConfig

# ---------------------------------------------------------------------------
# 10. TaskQueueManager -- enqueue/dequeue/ack jobs (MemoryTaskQueueAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import MemoryTaskQueueAdapter
from core_infrastructure.taskqueue.models import QueueConfig

# ---------------------------------------------------------------------------
# 11. ExternalAPIManager -- mock HTTP calls (MockHTTPAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter

# ---------------------------------------------------------------------------
# 12. FeatureFlagManager -- runtime feature toggles (MemoryFeatureFlagAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FeatureFlag, FlagConfig, FlagContext

# ---------------------------------------------------------------------------
# 13. DependencyManager -- dynamic dependency resolution (InMemoryDependencyAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import (
    InMemoryDependencyAdapter,
)

# ---------------------------------------------------------------------------
# 14. DynamicPromptingManager -- conditional prompt assembly (ConditionalPromptAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import (
    ConditionalPromptAdapter,
)
from core_infrastructure.dynamic_prompting.ports import PromptBlock

# ---------------------------------------------------------------------------
# 15. AlertManager -- multi-channel alert dispatch (DispatchAlertAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.alert.adapters.dispatch_alert_adapter import DispatchAlertAdapter
from core_infrastructure.alert.ports import AlertLevel, AlertRule

# ---------------------------------------------------------------------------
# 16. RateLimiterManager -- token bucket rate limiting (InMemoryRateLimitAdapter)
# ---------------------------------------------------------------------------
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import (
    InMemoryRateLimitAdapter,
)

# ---------------------------------------------------------------------------
# Context propagation primitives -- demonstrate set/get contextvars
# ---------------------------------------------------------------------------
from core_infrastructure.common.context import (
    get_context_snapshot,
    get_correlation_id,
    get_tenant_id,
    new_correlation_id,
    set_principal_id,
    set_tenant_id,
)


# ===========================================================================
# Demo Pipeline -- demonstrates ALL 16 managers in a realistic document flow
# ===========================================================================


async def main() -> None:
    """Demonstrate all 16 core-cenf managers working together.

    This is NOT a real document processor -- it demonstrates the INTEGRATION
    PATTERN for each manager: constructor injection, method calls, and the
    dependency wiring between managers that real consumers use.
    """
    print("=" * 72)
    print("  CENF Core Infrastructure -- Full Demo (all 16 managers)")
    print("  Document Processing Pipeline")
    print("=" * 72)

    # -----------------------------------------------------------------------
    # 1. CONFIG MANAGER -- Bootstrap configuration
    # -----------------------------------------------------------------------
    # In a real app, config comes from env vars + YAML. Here we use a dict
    # that seeds sections for all downstream managers (cache, database,
    # alert, dynamic_prompting, etc.).
    print("\n[ 1/16] ConfigManager -- loading configuration...")

    config = InMemoryConfigAdapter(
        initial_data={
            "app": {"name": "document-pipeline", "version": "0.1.0"},
            "env": "dev",
            "log_level": "DEBUG",
            "cache": {
                "default_ttl": 300,
                "max_size": 1000,
                "backend": "memory",
            },
            "database": {
                "host": "localhost",
                "port": 5432,
                "max_connections": 10,
            },
            "alert": {
                "channels": {
                    "slack": {"webhook_url": "https://hooks.slack.com/mock/xxx"},
                },
            },
            "dynamic_prompting": {
                "max_blocks": 16,
                "default_priority": 10,
            },
        }
    )
    # Demonstrate key ConfigManager methods
    env = config.get_env()
    app_name = config.get_string("app.name")
    debug_enabled_cfg = config.get_boolean("debug_mode", default_value=False)
    cache_section = config.get_section("cache")
    json_schema = config.get_json_schema()

    print(f"   [OK] env={env}, app={app_name}, cache_ttl={cache_section.get('default_ttl')}")
    assert env == "dev", f"Expected dev, got {env}"
    assert app_name == "document-pipeline"

    # -----------------------------------------------------------------------
    # 2. LOGGER MANAGER -- Structured logging with context
    # -----------------------------------------------------------------------
    print("\n[ 2/16] LoggerManager -- initializing structured logging...")

    logger = InMemoryLoggerAdapter(
        initial_context={"service": "document-pipeline", "env": env}
    )
    # Demonstrate all log levels and structured kwargs
    logger.info("Pipeline starting", step="bootstrap")
    logger.debug("Config loaded", keys=list(cache_section.keys()))
    logger.warn("This is a demo", detail="no real documents processed")

    # Demonstrate mask() for sensitive values
    masked = logger.mask("sk-proj-secret-key-1234abcd", visible_chars=4)
    logger.info("API key masked for display", masked_key=masked)

    # Demonstrate bind() -- creates a new logger with additional context
    bound_logger = logger.bind(component="parser", document_id="doc-001")
    bound_logger.info("Parser initialized")

    logs = logger.get_logs()
    print(f"   [OK] {len(logs)} log records captured (DEBUG/INFO/WARN all fired)")
    assert len(logs) >= 4, f"Expected at least 4 log records, got {len(logs)}"
    assert masked.endswith("abcd"), f"Mask should reveal last 4 chars, got: {masked}"

    # -----------------------------------------------------------------------
    # 3. SECRET MANAGER -- Retrieve and rotate secrets
    # -----------------------------------------------------------------------
    print("\n[ 3/16] SecretManager -- managing credentials...")

    secrets = InMemorySecretAdapter(
        config=SecretConfig(cache_ttl_seconds=30)
    )
    # Pre-populate secrets that downstream managers will use
    secrets.set_secret("auth_signing_key", "demo-hs256-signing-key-32chars!!")
    secrets.set_secret("api_key", "sk-demo-project-key-12345")
    secrets.set_secret("db_password", "demo-password-123")

    # Demonstrate get_secret (async) and rotation
    api_key = await secrets.get_secret("api_key")
    signing_key = await secrets.get_secret("auth_signing_key")

    # Rotate a secret
    await secrets.rotate_secret("api_key", "sk-demo-rotated-key-67890")
    rotated_key = await secrets.get_secret("api_key")

    # Invalidate cache
    secrets.invalidate_cache("api_key")

    print(f"   [OK] api_key_original={logger.mask(api_key)}")
    print(f"   [OK] signing_key_retrieved={'yes' if signing_key else 'no'}")
    print(f"   [OK] rotated_key={logger.mask(rotated_key)}")
    assert api_key != rotated_key, "Rotation should change the secret value"

    # -----------------------------------------------------------------------
    # 4. OBSERVABILITY MANAGER -- Metrics and tracing
    # -----------------------------------------------------------------------
    print("\n[ 4/16] ObservabilityManager -- recording metrics and spans...")

    observability = InMemoryObservabilityAdapter()

    # RED metrics: Rate, Errors, Duration
    observability.increment_counter(
        "cenf.documents.processed_total",
        value=1.0,
        attributes={"status": "success"},
    )
    observability.record_histogram(
        "cenf.documents.processing_duration_seconds",
        value=0.247,
        attributes={"file_type": "pdf"},
    )

    # Demonstrate span tracing with context manager
    with observability.start_span(
        "DocumentPipeline.process",
        attributes={"step": "extract_text"},
    ) as span:
        trace_id = observability.get_trace_id()
        current_span = observability.get_current_span()
        # Simulate work inside the span
        observability.increment_counter(
            "cenf.documents.pages_processed",
            value=3.0,
        )

    metrics = observability.get_metrics()
    spans = observability.get_spans()

    print(f"   [OK] {len(metrics)} metrics recorded")
    print(f"   [OK] {len(spans)} span(s) captured, trace_id={trace_id[:8]}...")
    assert len(metrics) == 3
    assert len(spans) >= 1
    assert trace_id, "Trace ID should be set after start_span"

    # -----------------------------------------------------------------------
    # 5. ERROR HANDLING MANAGER -- @handle_errors decorator
    # -----------------------------------------------------------------------
    print("\n[ 5/16] ErrorHandlingManager -- classifying and capturing errors...")

    # CapturingErrorAdapter captures errors instead of re-raising (test mode)
    error_handler = CapturingErrorAdapter(config, logger, observability)

    # Demonstrate @handle_errors decorator on a pipeline step
    @error_handler.handle_errors()
    def process_document(doc_id: str) -> dict[str, Any]:
        """Simulated document processing step."""
        if not doc_id:
            raise ValidationError(
                "Document ID must not be empty",
                details={"field": "doc_id"},
            )
        if doc_id == "fail":
            raise TransientError(
                "External service temporarily unavailable",
                details={"service": "ocr-api"},
            )
        return {"doc_id": doc_id, "status": "processed", "pages": 5}

    # Happy path
    result = process_document("doc-001")
    assert result is not None
    assert result["status"] == "processed"
    print(f"   [OK] Happy path: {result}")

    # Error path -- CapturingErrorAdapter returns None, does NOT raise
    failed_result = process_document("fail")
    assert failed_result is None, "Capturing adapter should return None on error"
    captured = error_handler.get_captured()
    assert len(captured) == 1
    assert isinstance(captured[0], TransientError)

    # Demonstrate classify() and report() manually
    classification = error_handler.classify(captured[0])
    error_handler.report(captured[0], context={"source": "demo"})

    print(f"   [OK] Captured error: {type(captured[0]).__name__}")
    print(f"   [OK] Classification: {classification.name}")
    assert classification.name == "TRANSIENT"

    # -----------------------------------------------------------------------
    # 6. AUTH MANAGER -- Validate JWT token, extract claims, set context
    # -----------------------------------------------------------------------
    print("\n[ 6/16] AuthManager -- validating JWT token and extracting claims...")

    # Generate a real HS256 JWT token (requires python-jose installed)
    from jose import jwt as jose_jwt  # type: ignore[import-untyped]

    # Build test claims
    now = int(_time.time())
    test_payload = {
        "sub": "svc-document-processor",
        "iss": "https://auth.cenf.tech",
        "aud": "document-pipeline",
        "exp": now + 3600,
        "iat": now,
        "nbf": now - 60,
        "scopes": ["read:documents", "write:documents", "admin"],
        "tenant_id": "tenant-abc",
        "principal_id": "principal-xyz",
    }

    # Encode the JWT using the signing key from SecretManager
    token = jose_jwt.encode(
        test_payload,
        signing_key,
        algorithm="HS256",
    )

    # Create AuthConfig and JwtAuthAdapter
    auth_config = AuthConfig(
        issuer="https://auth.cenf.tech",
        audience="document-pipeline",
        algorithms=["HS256"],
        token_leeway=60,
    )
    auth = JwtAuthAdapter(config, secrets, logger, observability, auth_config)

    # Validate the token -- this also sets tenant_id + principal_id contextvars
    claims: TokenClaims = await auth.validate_token(token)

    # Demonstrate scope validation
    has_admin = auth.validate_scopes(claims, ["admin"])
    has_super = auth.validate_scopes(claims, ["superadmin"])

    print(f"   [OK] Token validated: sub={claims.sub}, iss={claims.iss}")
    print(f"   [OK] Scopes: {claims.scopes}")
    print(f"   [OK] Context propagated: tenant_id={get_tenant_id()}")
    print(f"   [OK] Has admin scope: {has_admin}, Has superadmin: {has_super}")
    assert has_admin is True
    assert has_super is False
    assert get_tenant_id() == "tenant-abc"

    # -----------------------------------------------------------------------
    # 7. CACHE MANAGER -- Cache document metadata with stampede protection
    # -----------------------------------------------------------------------
    print("\n[ 7/16] CacheManager -- caching document metadata with stampede protection...")

    cache = MemoryCacheAdapter(
        config=config,
        logger=logger,
        error_handler=error_handler,
        stampede_config=StampedeConfig(beta=1.0, delta=0.5),
    )

    # Demonstrate basic set/get/exists
    doc_metadata = {
        "title": "Q4 Financial Report",
        "author": "Finance Team",
        "pages": 42,
        "format": "pdf",
    }
    cache.set("doc:metadata:report-001", doc_metadata, ttl=300)
    assert cache.exists("doc:metadata:report-001") is True

    cached = cache.get("doc:metadata:report-001")
    assert cached == doc_metadata

    # Demonstrate get_or_set with stampede mitigation (factory pattern)
    call_counter: int = 0

    def fetch_from_db() -> dict[str, str]:
        """Simulate expensive database fetch for cache miss."""
        nonlocal call_counter
        call_counter += 1
        return {"title": "Expensive DB Result", "source": "postgres"}

    # First call: cache miss -> factory called
    result1 = cache.get_or_set(
        "doc:metadata:report-002",
        fetch_from_db,
        ttl=300,
    )
    # Second call: cache hit -> factory NOT called
    result2 = cache.get_or_set(
        "doc:metadata:report-002",
        fetch_from_db,
        ttl=300,
    )

    print(f"   [OK] Cached metadata: {cached['title']} ({cached['pages']} pages)")
    print(f"   [OK] get_or_set factory called: {call_counter} time(s)")
    print(f"   [OK] Stampede protection active (XFetch: beta=1.0, delta=0.5)")
    assert call_counter == 1, "Factory should only be called once (cache hit on 2nd)"
    assert result1 == result2

    # Demonstrate delete
    cache.delete("doc:metadata:report-001")
    assert cache.exists("doc:metadata:report-001") is False
    print(f"   [OK] Cache eviction works (key deleted)")

    # -----------------------------------------------------------------------
    # 8. DATABASE MANAGER -- Store document records in a transaction
    # -----------------------------------------------------------------------
    print("\n[ 8/16] DatabaseManager -- storing document records...")

    db = MemoryDatabaseAdapter(config, logger, observability, error_handler)

    # get_repository returns a GenericRepository-like interface keyed by type
    repo = db.get_repository(dict)  # type: ignore[type-abstract]

    # Insert document records
    doc1 = await repo.insert({
        "filename": "report_q4.pdf",
        "size_bytes": 1048576,
        "status": "pending",
        "tenant_id": get_tenant_id(),
    })
    doc2 = await repo.insert({
        "filename": "invoice_2024.pdf",
        "size_bytes": 256000,
        "status": "processed",
        "tenant_id": get_tenant_id(),
    })

    # Demonstrate find_by_id
    found = await repo.find_by_id(doc1["id"])
    assert found is not None
    assert found["filename"] == "report_q4.pdf"

    # Demonstrate find_all with filters and pagination
    pending_docs = await repo.find_all(
        filters={"status": "pending"},
        order_by="filename",
        limit=10,
        offset=0,
    )

    # Demonstrate count
    total = await repo.count(filters={"status": "pending"})

    print(f"   [OK] Inserted docs: {doc1['id'][:8]}... and {doc2['id'][:8]}...")
    print(f"   [OK] Found by id: {found['filename']} (status={found['status']})")
    print(f"   [OK] Pending docs: {len(pending_docs)} (count={total})")
    assert total == 1

    # Demonstrate transaction with commit (async context manager)
    async with db.transaction() as tx:
        doc3 = await repo.insert({
            "filename": "contract_signed.pdf",
            "size_bytes": 512000,
            "status": "pending",
            "tenant_id": get_tenant_id(),
        })
        await tx.commit()
    # After commit, the doc should be persisted
    committed = await repo.find_by_id(doc3["id"])
    assert committed is not None
    print(f"   [OK] Transaction committed: {committed['filename']} persisted")

    # -----------------------------------------------------------------------
    # 9. FILE STORAGE MANAGER -- Upload/download a sample document
    # -----------------------------------------------------------------------
    print("\n[ 9/16] FileStorageManager -- uploading and downloading documents...")

    storage = MemoryStorageAdapter(config=StorageConfig())

    # Upload a document
    sample_content = b"This is a sample document body for the demo pipeline."
    upload_result = await storage.upload(
        bucket="documents",
        key="incoming/report_q4.pdf",
        data=sample_content,
        content_type="application/pdf",
    )

    # Check existence
    exists = await storage.exists("documents", "incoming/report_q4.pdf")
    assert exists is True

    # Download the document
    downloaded = await storage.download("documents", "incoming/report_q4.pdf")
    assert downloaded == sample_content

    # Generate a pre-signed URL
    presigned = await storage.generate_presigned_url(
        "documents",
        "incoming/report_q4.pdf",
        expiry=3600,
    )

    # List objects in bucket
    objects = await storage.list_objects("documents", prefix="incoming/")

    print(f"   [OK] Uploaded: {upload_result.key} (etag={upload_result.etag[:8]}...)")
    print(f"   [OK] Downloaded: {len(downloaded)} bytes match original")
    print(f"   [OK] Pre-signed URL: {presigned}")
    print(f"   [OK] Objects in bucket: {len(objects)}")

    # Demonstrate delete
    await storage.delete("documents", "incoming/report_q4.pdf")
    assert await storage.exists("documents", "incoming/report_q4.pdf") is False
    print(f"   [OK] Deleted successfully")

    # -----------------------------------------------------------------------
    # 10. TASK QUEUE MANAGER -- Enqueue, dequeue, ack a processing job
    # -----------------------------------------------------------------------
    print("\n[10/16] TaskQueueManager -- enqueuing and dequeuing processing jobs...")

    task_queue = MemoryTaskQueueAdapter(config=QueueConfig())

    # Enqueue a document processing job
    job_ref = await task_queue.enqueue(
        queue_name="document-processing",
        payload={
            "document_id": "doc-001",
            "operation": "extract_text",
            "priority": "high",
        },
        max_retries=3,
    )
    print(f"   [OK] Enqueued job: {job_ref.id[:8]}... (status={job_ref.status})")

    # Dequeue the job
    job = await task_queue.dequeue("document-processing")
    assert job is not None
    print(f"   [OK] Dequeued job: payload={job.payload}")

    # Ack (acknowledge successful completion)
    await task_queue.ack(job.id)

    # Verify job state
    verified = await task_queue.get_job(job.id)
    assert verified is not None
    print(f"   [OK] Job acked: status={verified.status.name}")

    # Schedule a deferred job (for the demo, schedule 1 second from now is fine)
    from datetime import UTC, datetime, timedelta

    future_time = datetime.now(UTC) + timedelta(seconds=1)
    scheduled_ref = await task_queue.schedule(
        queue_name="document-processing",
        payload={"document_id": "doc-002", "operation": "ocr"},
        execute_at=future_time,
        max_retries=2,
    )
    print(f"   [OK] Scheduled job: {scheduled_ref.id[:8]}... (execute_at={future_time.isoformat()})")

    # DLQ check -- should be empty
    dlq_jobs = await task_queue.get_dlq_jobs("document-processing")
    print(f"   [OK] DLQ is empty: {len(dlq_jobs)} dead jobs")

    # -----------------------------------------------------------------------
    # 11. EXTERNAL API MANAGER -- Call a mock external API
    # -----------------------------------------------------------------------
    print("\n[11/16] ExternalAPIManager -- calling mock external API...")

    http_client = MockHTTPAdapter()

    # Configure a mock response for a GET endpoint
    http_client.set_response(
        "GET",
        "https://ocr-api.example.com/v1/status",
        status_code=200,
        body={"status": "healthy", "version": "2.1.0"},
    )

    # Configure a mock response for a POST endpoint
    http_client.set_response(
        "POST",
        "https://ocr-api.example.com/v1/extract",
        status_code=201,
        body={"job_id": "ocr-12345", "status": "processing"},
    )

    # Demonstrate GET
    get_response = await http_client.get("https://ocr-api.example.com/v1/status")
    print(f"   [OK] GET response: status={get_response.status_code}, body={get_response.body}")

    # Demonstrate POST
    post_response = await http_client.post(
        "https://ocr-api.example.com/v1/extract",
        body={"document_url": "memory://documents/incoming/report_q4.pdf"},
    )
    print(f"   [OK] POST response: status={post_response.status_code}, body={post_response.body}")

    # Demonstrate circuit breaker inspection
    host = "ocr-api.example.com"
    circuit_state = http_client.get_circuit_state(host)
    print(f"   [OK] Circuit state for {host}: {circuit_state.name}")

    assert get_response.status_code == 200
    assert post_response.status_code == 201
    assert circuit_state.name == "CLOSED"

    # -----------------------------------------------------------------------
    # 12. FEATURE FLAG MANAGER -- Check if "new_parser" is enabled
    # -----------------------------------------------------------------------
    print("\n[12/16] FeatureFlagManager -- checking feature flags...")

    feature_flags = MemoryFeatureFlagAdapter(config=FlagConfig(default_all=False))

    # Register flags
    feature_flags.set_flag(
        FeatureFlag(
            key="new_parser",
            enabled=True,
            value={"parser_version": "v2", "engine": "rust-pdf"},
        )
    )
    feature_flags.set_flag(
        FeatureFlag(
            key="experimental_ocr",
            enabled=False,
            value={"ocr_engine": "tesseract-v5"},
        )
    )
    feature_flags.set_flag(
        FeatureFlag(
            key="staging_only_feature",
            enabled=True,
            rules=[
                {"attribute": "environment", "operator": "eq", "value": "staging"},
            ],
        )
    )

    # Evaluate flags with context
    ctx = FlagContext(
        tenant_id=get_tenant_id(),
        environment="dev",
    )

    new_parser_enabled = feature_flags.is_enabled("new_parser", context=ctx)
    experimental_ocr = feature_flags.is_enabled("experimental_ocr", context=ctx)
    staging_feature = feature_flags.is_enabled("staging_only_feature", context=ctx)
    unknown_flag = feature_flags.is_enabled("nonexistent", context=ctx)

    # get_flag_value returns the flag's payload
    parser_value = feature_flags.get_flag_value("new_parser", context=ctx)
    all_flags = feature_flags.get_all_flags(context=ctx)

    print(f"   [OK] new_parser enabled: {new_parser_enabled} (payload: {parser_value})")
    print(f"   [OK] experimental_ocr enabled: {experimental_ocr}")
    print(f"   [OK] staging_only_feature in dev: {staging_feature} (rule mismatch)")
    print(f"   [OK] Unknown flag (fail-safe): {unknown_flag}")
    print(f"   [OK] All flags: {all_flags}")

    assert new_parser_enabled is True
    assert experimental_ocr is False
    assert staging_feature is False  # Rule: environment must be "staging", we're in "dev"
    assert unknown_flag is False  # Fail-safe: unknown flags return False

    # -----------------------------------------------------------------------
    # 13. DEPENDENCY MANAGER -- Register and resolve a dependency
    # -----------------------------------------------------------------------
    print("\n[13/16] DependencyManager -- registering and resolving dependencies...")

    # In-memory dependency adapter -- maps module_path + class_name to objects
    class PdfParser:
        """Mock PDF parser registered as a dependency."""

        def __init__(self) -> None:
            self.name: str = "PdfParser v1.0"

        def parse(self, content: bytes) -> str:
            """Mock parse method."""
            return f"Parsed {len(content)} bytes"

    parser_instance = PdfParser()

    # Create the adapter with an explicit mapping for direct resolution
    dependency_mgr = InMemoryDependencyAdapter(
        mapping={("parsers.pdf", "PdfParser"): parser_instance}
    )

    # Demonstrate register() -- inject a catalog entry
    dependency_mgr.register(
        namespace="parsers",
        key="ocr_parser",
        target=("parsers.ocr", "TesseractParser"),
    )

    # Demonstrate is_known and list_keys
    assert dependency_mgr.is_known("parsers", "pdf_parser") is False
    assert dependency_mgr.is_known("parsers", "ocr_parser") is True
    keys = dependency_mgr.list_keys("parsers")

    # Demonstrate resolve_class -- resolves via the explicit mapping
    resolved = dependency_mgr.resolve_class("parsers.pdf", "PdfParser")
    assert resolved is not None

    parse_result = resolved.parse(b"demo content")
    print(f"   [OK] Registered namespace 'parsers': keys={keys}")
    print(f"   [OK] Resolved PdfParser: {resolved.name}")
    print(f"   [OK] Parse result: {parse_result}")

    # -----------------------------------------------------------------------
    # 14. DYNAMIC PROMPTING MANAGER -- Assemble a system prompt conditionally
    # -----------------------------------------------------------------------
    print("\n[14/16] DynamicPromptingManager -- assembling conditional system prompt...")

    prompt_assembler = ConditionalPromptAdapter(config, logger, error_handler)

    # Define conditional prompt blocks
    blocks = [
        PromptBlock(
            id="persona",
            condition=None,  # Always included
            content="You are a document processing assistant.",
            priority=1,
        ),
        PromptBlock(
            id="pdf-mode",
            condition={"document.format": "pdf"},
            content="Use the PDF extraction pipeline for text analysis.",
            priority=10,
        ),
        PromptBlock(
            id="image-mode",
            condition={"document.format": "image"},
            content="Use the OCR pipeline for image-to-text conversion.",
            priority=10,
        ),
        PromptBlock(
            id="admin-instructions",
            condition={"user.role": "admin"},
            content="You have full access to all documents and metadata.",
            priority=20,
        ),
        PromptBlock(
            id="rate-limit-warning",
            condition={"system.under_load": True},
            content="WARNING: System under high load. Prioritize critical documents.",
            priority=5,
        ),
    ]

    # Validate blocks -- should be clean
    validation_errors = prompt_assembler.validate_blocks(blocks)
    assert len(validation_errors) == 0
    print(f"   [OK] Block validation: {len(validation_errors)} errors")

    # Assemble prompt for a PDF document admin user
    context_pdf_admin = {
        "document": {"format": "pdf", "page_count": 42},
        "user": {"role": "admin", "name": "Alice"},
        "system": {"under_load": False},
    }
    prompt_pdf = await prompt_assembler.assemble(
        base_prompt="You are a helpful assistant.",
        blocks=blocks,
        context_state=context_pdf_admin,
    )
    print(f"   [OK] PDF+Admin prompt ({len(prompt_pdf)} chars):")
    # Show first line of each section
    for line in prompt_pdf.split("\n\n")[:2]:
        print(f"     {line[:80]}...")

    # Assemble prompt for an image document, non-admin user
    context_image_user = {
        "document": {"format": "image"},
        "user": {"role": "viewer"},
        "system": {"under_load": False},
    }
    prompt_image = await prompt_assembler.assemble(
        base_prompt="You are a helpful assistant.",
        blocks=blocks,
        context_state=context_image_user,
    )
    print(f"   [OK] Image+Viewer prompt ({len(prompt_image)} chars) -- admin block excluded")

    # Verify condition matching: admin block should NOT be in the image+viewer prompt
    assert "full access" not in prompt_image
    assert "full access" in prompt_pdf
    print(f"   [OK] Conditional blocks correctly included/excluded by context")

    # -----------------------------------------------------------------------
    # 15. ALERT MANAGER -- Send alert when document fails processing
    # -----------------------------------------------------------------------
    print("\n[15/16] AlertManager -- dispatching alert on document failure...")

    # DispatchAlertAdapter needs ExternalAPIManager for HTTP dispatch
    alert_mgr = DispatchAlertAdapter(
        config=config,
        secret_manager=secrets,
        logger=logger,
        external_api=http_client,
        error_handler=error_handler,
    )

    # Set up a mock response for the Slack webhook URL defined in config
    http_client.set_response(
        "POST",
        "https://hooks.slack.com/mock/xxx",
        status_code=200,
        body={"ok": True},
    )

    # Register an alert rule: fire when a document fails processing
    rule = AlertRule(
        rule_id="doc_processing_failed",
        condition={"event_type": "document_failed", "severity": "critical"},
        level=AlertLevel.CRITICAL,
        channels=["slack"],
        throttle_seconds=0,  # No throttle for demo
    )
    alert_mgr.register_rule(rule)
    print(f"   [OK] Rule registered: {rule.rule_id} (channels={rule.channels})")

    # Evaluate and alert -- the event matches the rule's condition
    await alert_mgr.evaluate_and_alert({
        "event_type": "document_failed",
        "severity": "critical",
        "document_id": "doc-001",
        "error": "OCR engine timeout after 30s",
        "pipeline_step": "extract_text",
    })
    print(f"   [OK] Alert dispatched to slack (via MockHTTPAdapter)")

    # Demonstrate direct send_alert (bypasses rule matching)
    await alert_mgr.send_alert(
        level=AlertLevel.WARNING,
        title="Pipeline throughput degraded",
        message="Processing rate dropped below 10 docs/min",
        metadata={"current_rate": "7.2", "threshold": "10.0"},
    )
    print(f"   [OK] Direct alert sent (WARNING level)")

    # -----------------------------------------------------------------------
    # 16. RATE LIMITER MANAGER -- Rate-limit API calls
    # -----------------------------------------------------------------------
    print("\n[16/16] RateLimiterManager -- rate-limiting API calls...")

    rate_limiter = InMemoryRateLimitAdapter(mode="always_allow")

    # Configure rate limit buckets for different API endpoints
    rate_limiter.configure_bucket(
        bucket_key="api:ocr",
        capacity=100,
        refill_rate=10.0,
        window_type="token_bucket",
    )
    rate_limiter.configure_bucket(
        bucket_key="api:storage",
        capacity=50,
        refill_rate=5.0,
        window_type="token_bucket",
    )

    # Demonstrate is_allowed -- in "always_allow" mode, always True
    for i in range(5):
        allowed = await rate_limiter.is_allowed("api:ocr", cost=1.0)
        assert allowed is True
    print(f"   [OK] 5 OCR API calls allowed (always_allow mode)")

    # Demonstrate get_remaining and get_reset_time
    remaining = await rate_limiter.get_remaining("api:ocr")
    reset_time = await rate_limiter.get_reset_time("api:ocr")
    print(f"   [OK] Remaining tokens: {remaining}, Reset in ~{reset_time - _time.time():.0f}s")

    # Demonstrate "always_deny" mode briefly
    deny_limiter = InMemoryRateLimitAdapter(mode="always_deny")
    denied = await deny_limiter.is_allowed("api:ocr")
    assert denied is False
    print(f"   [OK] always_deny mode: is_allowed()={denied} (rate limit enforced)")

    # ===================================================================
    # SUCCESS
    # ===================================================================
    print("\n" + "=" * 72)
    print("  [SUCCESS] All 16 managers demonstrated successfully!")
    print("=" * 72)

    # Print summary of what was exercised
    print("""
    +------+-------------------------+--------------------------------------+
    |  #   | Manager                 | Key pattern demonstrated             |
    +------+-------------------------+--------------------------------------+
    |  1   | ConfigManager           | get_env, get_string, get_section     |
    |  2   | LoggerManager           | info/debug/warn, mask, bind          |
    |  3   | SecretManager           | set_secret, get_secret, rotate       |
    |  4   | ObservabilityManager    | counter, histogram, span tracing     |
    |  5   | ErrorHandlingManager    | @handle_errors, classify, handle     |
    |  6   | AuthManager             | validate_token, validate_scopes      |
    |  7   | CacheManager            | get/set, get_or_set (XFetch)         |
    |  8   | DatabaseManager         | transaction, repo insert/find/count  |
    |  9   | FileStorageManager      | upload, download, presigned URL      |
    | 10   | TaskQueueManager        | enqueue, dequeue, ack, schedule      |
    | 11   | ExternalAPIManager      | GET, POST, circuit breaker           |
    | 12   | FeatureFlagManager      | is_enabled, get_flag_value, rules    |
    | 13   | DependencyManager       | register, resolve_class, is_known    |
    | 14   | DynamicPromptingManager | assemble, validate_blocks, condition |
    | 15   | AlertManager            | register_rule, evaluate_and_alert    |
    | 16   | RateLimiterManager      | is_allowed, configure_bucket         |
    +------+-------------------------+--------------------------------------+
    """)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    asyncio.run(main())
