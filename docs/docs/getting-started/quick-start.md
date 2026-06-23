# Quick Start

Bootstrap all 16 core-cenf managers and run a working pipeline in 5 minutes.

## What You'll Build

A minimal document processing pipeline that demonstrates every manager: config loading,
structured logging, secret retrieval, metrics, error handling, JWT validation, caching,
database transactions, file uploads, task queuing, HTTP calls, feature flags, dependency
resolution, prompt assembly, alert dispatch, and rate limiting.

All adapters are **in-memory** — no external services, no network, no filesystem. You can
run this anywhere.

## Step 1: Wire ConfigManager (root — zero dependencies)

```python
from core_infrastructure.config.adapters.in_memory_config_adapter import InMemoryConfigAdapter

config = InMemoryConfigAdapter(
    initial_data={
        "app": {"name": "my-app", "version": "0.1.0"},
        "env": "dev",
        "log_level": "DEBUG",
        "cache": {"default_ttl": 300, "max_size": 1000, "backend": "memory"},
        "database": {"host": "localhost", "port": 5432, "max_connections": 10},
        "alert": {"channels": {"slack": {"webhook_url": "https://hooks.slack.com/mock/xxx"}}},
    }
)

env = config.get_env()          # "dev"
app_name = config.get_string("app.name")  # "my-app"
cache_ttl = config.get_section("cache").get("default_ttl")  # 300
```

## Step 2: Wire LoggerManager

```python
from core_infrastructure.logger.adapters.in_memory_logger_adapter import InMemoryLoggerAdapter

logger = InMemoryLoggerAdapter(initial_context={"service": "my-app", "env": env})

logger.info("Pipeline starting", step="bootstrap")
logger.debug("Config loaded", ttl=cache_ttl)

# Mask sensitive values before logging
masked = logger.mask("sk-proj-secret-key-1234abcd", visible_chars=4)
# → "sk-p...abcd"

# Bind creates a child logger with extra context
bound = logger.bind(component="parser", document_id="doc-001")
bound.info("Parser initialized")
```

## Step 3: Wire SecretManager

```python
from core_infrastructure.secrets.adapters.in_memory_secret_adapter import InMemorySecretAdapter
from core_infrastructure.secrets.models import SecretConfig

secrets = InMemorySecretAdapter(config=SecretConfig(cache_ttl_seconds=30))
secrets.set_secret("auth_signing_key", "demo-hs256-signing-key-32chars!!")
secrets.set_secret("api_key", "sk-demo-project-key-12345")

api_key = await secrets.get_secret("api_key")  # async retrieval
await secrets.rotate_secret("api_key", "sk-rotated-67890")
```

## Step 4: Wire ObservabilityManager

```python
from core_infrastructure.observability.adapters.in_memory_observability_adapter import (
    InMemoryObservabilityAdapter,
)

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

# Span tracing
with observability.start_span("DocumentPipeline.process",
                               attributes={"step": "extract_text"}) as span:
    trace_id = observability.get_trace_id()
    # ... work inside span ...
```

## Step 5: Wire ErrorHandlingManager

```python
from core_infrastructure.errors.adapters.capturing_error_adapter import CapturingErrorAdapter
from core_infrastructure.common.errors import TransientError, ValidationError

error_handler = CapturingErrorAdapter(config, logger, observability)

@error_handler.handle_errors()
def process_document(doc_id: str) -> dict:
    if not doc_id:
        raise ValidationError("Document ID must not be empty",
                              details={"field": "doc_id"})
    if doc_id == "fail":
        raise TransientError("External service unavailable",
                             details={"service": "ocr-api"})
    return {"doc_id": doc_id, "status": "processed", "pages": 5}

result = process_document("doc-001")
# → {"doc_id": "doc-001", "status": "processed", "pages": 5}

# CapturingErrorAdapter returns None on error, does NOT raise
failed = process_document("fail")
# → None

classification = error_handler.classify(error_handler.get_captured()[0])
# → ErrorType.TRANSIENT
```

## Step 6: Wire AuthManager

```python
import time
from jose import jwt as jose_jwt
from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter
from core_infrastructure.auth.models import AuthConfig

signing_key = await secrets.get_secret("auth_signing_key")

# Build and encode a JWT
now = int(time.time())
token = jose_jwt.encode(
    {
        "sub": "svc-processor", "iss": "https://auth.cenf.tech",
        "aud": "my-app", "exp": now + 3600, "iat": now,
        "scopes": ["read:documents", "admin"],
        "tenant_id": "tenant-abc", "principal_id": "principal-xyz",
    },
    signing_key, algorithm="HS256",
)

auth = JwtAuthAdapter(
    config, secrets, logger, observability,
    AuthConfig(issuer="https://auth.cenf.tech", audience="my-app",
               algorithms=["HS256"], token_leeway=60),
)

claims = await auth.validate_token(token)
has_admin = auth.validate_scopes(claims, ["admin"])  # True

# AuthManager sets contextvars automatically
from core_infrastructure.common.context import get_tenant_id
print(get_tenant_id())  # "tenant-abc"
```

## Step 7: Wire Remaining Managers

The pattern repeats for all 16 managers. Each follows **constructor DI**: instantiate
with its dependencies, call methods. Here is the condensed wiring for the remaining
managers (in dependency order):

```python
# M07: CacheManager
from core_infrastructure.cache.adapters.memory_cache_adapter import MemoryCacheAdapter
cache = MemoryCacheAdapter(config=config, logger=logger, error_handler=error_handler)
cache.set("doc:meta:001", {"title": "Q4 Report", "pages": 42}, ttl=300)
cached = cache.get_or_set("doc:meta:002", lambda: {"title": "From DB"}, ttl=300)

# M08: DatabaseManager
from core_infrastructure.database.adapters.memory_database_adapter import MemoryDatabaseAdapter
db = MemoryDatabaseAdapter(config, logger, observability, error_handler)
repo = db.get_repository(dict)
doc = await repo.insert({"filename": "report.pdf", "size_bytes": 1048576, "status": "pending"})
async with db.transaction() as tx:
    await repo.insert({"filename": "contract.pdf", "status": "pending"})
    await tx.commit()

# M09: FileStorageManager
from core_infrastructure.filestorage.adapters.memory_storage_adapter import MemoryStorageAdapter
storage = MemoryStorageAdapter(config=StorageConfig())
await storage.upload("documents", "incoming/report.pdf", b"file body", content_type="application/pdf")
downloaded = await storage.download("documents", "incoming/report.pdf")

# M10: TaskQueueManager
from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import MemoryTaskQueueAdapter
queue = MemoryTaskQueueAdapter(config=QueueConfig())
job_ref = await queue.enqueue("processing", {"doc_id": "doc-001", "op": "extract"})
job = await queue.dequeue("processing")
await queue.ack(job.id)

# M11: ExternalAPIManager
from core_infrastructure.external_api.adapters.mock_http_adapter import MockHTTPAdapter
http = MockHTTPAdapter()
http.set_response("GET", "https://ocr.example.com/status", status_code=200,
                  body={"status": "healthy"})
resp = await http.get("https://ocr.example.com/status")
# resp.status_code == 200

# M12: FeatureFlagManager
from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FeatureFlag, FlagConfig, FlagContext
flags = MemoryFeatureFlagAdapter(config=FlagConfig(default_all=False))
flags.set_flag(FeatureFlag(key="new_parser", enabled=True))
ctx = FlagContext(tenant_id="tenant-abc", environment="dev")
new_parser = flags.is_enabled("new_parser", context=ctx)  # True

# M13: DependencyManager
from core_infrastructure.dependency.adapters.in_memory_dependency_adapter import InMemoryDependencyAdapter
class PdfParser:
    def parse(self, content): return f"Parsed {len(content)} bytes"
deps = InMemoryDependencyAdapter(
    mapping={("parsers.pdf", "PdfParser"): PdfParser()}
)
resolved = deps.resolve_class("parsers.pdf", "PdfParser")

# M14: DynamicPromptingManager
from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import (
    ConditionalPromptAdapter,
)
from core_infrastructure.dynamic_prompting.ports import PromptBlock
prompt_mgr = ConditionalPromptAdapter(config, logger, error_handler)
blocks = [
    PromptBlock(id="base", condition=None, content="You are a document assistant.", priority=1),
    PromptBlock(id="pdf", condition={"doc.format": "pdf"},
                content="Use the PDF pipeline.", priority=10),
]
result = await prompt_mgr.assemble("You are helpful.", blocks, {"doc": {"format": "pdf"}})

# M15: AlertManager
from core_infrastructure.alert.adapters.dispatch_alert_adapter import DispatchAlertAdapter
from core_infrastructure.alert.ports import AlertLevel, AlertRule
alert = DispatchAlertAdapter(config=config, secret_manager=secrets, logger=logger,
                              external_api=http, error_handler=error_handler)
alert.register_rule(AlertRule(rule_id="doc_failed",
    condition={"event_type": "doc_failed"}, level=AlertLevel.CRITICAL,
    channels=["slack"], throttle_seconds=0))
await alert.evaluate_and_alert({"event_type": "doc_failed", "severity": "critical"})

# M16: RateLimiterManager
from core_infrastructure.ratelimit.adapters.in_memory_ratelimit_adapter import InMemoryRateLimitAdapter
rate = InMemoryRateLimitAdapter(mode="always_allow")
rate.configure_bucket("api:ocr", capacity=100, refill_rate=10.0, window_type="token_bucket")
allowed = await rate.is_allowed("api:ocr", cost=1.0)  # True
```

## Step 8: Bootstrap Orchestrator (Lifecycle)

```python
from core_infrastructure.bootstrap import BootstrapOrchestrator

# Wrap adapters with AsyncLifecycle (for tests/conftest uses _LifecycleWrapper)
# In production, adapters implement AsyncLifecycle directly.

# Wire all managers in dependency order
orchestrator = BootstrapOrchestrator(
    config, logger, secrets, observability, error_handler,
    auth, cache, db, storage, queue, http, flags,
    deps, prompt_mgr, alert, rate,
)

# Run full lifecycle: startup → wait for SIGTERM → shutdown
await orchestrator.run()
```

## Expected Output

When you run the full demo (`python examples/full_demo.py`), you should see output like:

```
========================================================================
  CENF Core Infrastructure -- Full Demo (all 16 managers)
  Document Processing Pipeline
========================================================================

[ 1/16] ConfigManager -- loading configuration...
   [OK] env=dev, app=document-pipeline, cache_ttl=300

[ 2/16] LoggerManager -- initializing structured logging...
   [OK] 5 log records captured (DEBUG/INFO/WARN all fired)

[ 3/16] SecretManager -- managing credentials...
   [OK] api_key_original=sk-p...12345
   [OK] rotated_key=sk-d...67890

[ 4/16] ObservabilityManager -- recording metrics and spans...
   [OK] 3 metrics recorded
   [OK] 1 span(s) captured, trace_id=abc12345...

...

========================================================================
  [SUCCESS] All 16 managers demonstrated successfully!
========================================================================
```

Process exits with code `0`.

## Next Steps

- Read **[Ports &amp; Adapters](./core-concepts/ports-and-adapters)** to understand the
  architectural pattern behind every manager.
- Read **[Context Propagation](./core-concepts/context-propagation)** to learn how
  correlation IDs flow implicitly across async boundaries.
- Read the **[full demo source](https://github.com/CENFARG/core-cenf-py/blob/main/examples/full_demo.py)**
  for the complete 900-line integration example.
- Dive into individual **[Managers](../managers/config-manager)** for deep-dive
  documentation on each one.
