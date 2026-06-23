# core-cenf-py — CENF Core Infrastructure (Python)

[![CI/CD](https://github.com/CENFARG/core-cenf-py/actions/workflows/ci.yml/badge.svg)](https://github.com/CENFARG/core-cenf-py/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-orange.svg)](CHANGELOG.md)
[![Managers](https://img.shields.io/badge/managers-20-brightgreen.svg)](AGENTS_API.md)

Core horizontal transversal infrastructure for all CENF developments. 20 reusable managers following Clean Architecture / Hexagonal (Ports & Adapters) with full SDD + TDD methodology. Designed for both human developers and AI coding agents.

## Managers

| # | Manager | Dependencies | Status |
|---|---------|-------------|--------|
| M01 | ConfigManager | None | 🔴 Pending |
| M02 | LoggerManager | Config | 🔴 Pending |
| M03 | SecretManager | Config, Logger | 🔴 Pending |
| M04 | ErrorHandlingManager | Config, Logger, Observability | 🔴 Pending |
| M05 | ObservabilityManager | Config, Secret, Logger | 🔴 Pending |
| M06 | AuthManager | Config, Secret, Logger, Observability | 🔴 Pending |
| M07 | CacheManager | Config, Secret, Logger, Error | 🔴 Pending |
| M08 | DatabaseManager | Config, Secret, Logger, Observability, Error | 🔴 Pending |
| M09 | FileStorageManager | Config, Secret, Logger, Error | 🔴 Pending |
| M10 | TaskQueueManager | Config, Secret, Logger, Error, Cache | 🔴 Pending |
| M11 | ExternalAPIManager | Config, Secret, Logger, Observability, Error, Auth | 🔴 Pending |
| M12 | FeatureFlagManager | Config, Secret, Logger, Error, ExternalAPI, Cache | 🔴 Pending |

## Architecture

- **Python 3.12+** with modern typing (Protocol, PEP 695)
- **Clean Architecture / Hexagonal**: ports (Protocols) + adapters (implementations)
- **Structured Concurrency**: `asyncio.TaskGroup`, no bare `asyncio.gather`
- **Boundary Validation**: Pydantic V2 for runtime validation at every I/O boundary
- **OpenTelemetry**: RED metrics (Rate, Errors, Duration) per manager
- **Zero-Trust Security**: OWASP 2025 aligned, PII redaction, immutable audit logs

## Quick Start

```bash
uv venv .venv
.venv\Scripts\activate
uv pip install -e ".[dev]"
python -m pytest
```

## License

MIT — see [LICENSE](LICENSE) file.
