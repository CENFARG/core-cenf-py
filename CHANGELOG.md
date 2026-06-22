# Changelog

All notable changes to core-cenf are documented in this file.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).  
Versioning follows [SemVer 2.0.0](https://semver.org/).

## [0.1.0] — 2026-06-22

### Added
- **20 infrastructure managers** (M01-M20) following Clean Architecture (Ports & Adapters)
- **Base Infrastructure**: ConfigManager, LoggerManager, SecretManager, ErrorHandlingManager, ObservabilityManager, AuthManager
- **Data Layer**: CacheManager (Redis + in-memory, XFetch stampede), DatabaseManager (SQLAlchemy 2.0 + asyncpg + Alembic, GenericRepository), FileStorageManager (Local + S3 + GCS + Azure)
- **Service Layer**: TaskQueueManager (SAQ + DLQ), ExternalAPIManager (Circuit Breaker + retry), FeatureFlagManager (YAML + Unleash-ready), DependencyManager (importlib lazy + allowlist), DynamicPromptingManager (conditional prompt assembly), AlertManager (Slack/Discord/Email + rules), RateLimiterManager (Token Bucket + Sliding Window)
- **Enterprise Layer**: I18nManager (YAML translations), PermissionManager (RBAC+ABAC hybrid, pycasbin, human-agent delegation with TTL), LicenceManager (JWT signed claims, RS256, online/offline, grace period), UpdateManager (TUF-inspired, Ed25519 + SHA-256, rollback)
- **Cross-cutting**: contextvars propagation (6 variables), error taxonomy (5 classes), AsyncLifecycle Protocol, BootstrapOrchestrator (asyncio.TaskGroup)
- **CI/CD**: GitHub Actions (ruff + mypy strict + pytest + Trivy security scan + CycloneDX SBOM)
- **Pre-commit hooks**: ruff format, mypy strict, CENF rules (no regex spaces, no asyncio.gather, no hardcoded paths, file size limit)
- **Documentation**: Docusaurus site (29 pages, Diátaxis framework), AGENTS.md, AGENTS_API.md, agents/api-catalog.json, MCP FTS5 server
- **CodeGraph**: Pre-indexed knowledge graph (3,279 nodes, 5,961 edges)
- **Scaffolding CLI**: `cenf new <project>` generates complete CENF project skeleton
- **CoreForge Integration Team**: 4-agent system prompts for future Agno implementation

### Testing
- ~1,400 tests (unit + integration + E2E + stress)
- Strict TDD methodology enforced
- mypy --strict: 0 errors
- ruff: 0 errors
