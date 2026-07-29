# Proposal: M24 MaintenanceManager — Auto Error Reporting + Telemetry + GitHub Issues

## Intent

CENF products (Arca SaaS, grama, arcaMCP, instaldorAgentico) lack a unified error reporting and telemetry pipeline. Today, errors die in local logs. We need GDPR-compliant automatic capture, PII-scrubbed telemetry transport, and structured issue creation in GitHub — all default-off with explicit opt-in consent.

## Scope

### In Scope
1. **Protocol** (`ports.py`) — consent, error capture, telemetry, reporting
2. **GDPR Consent** — opt-in (default-off), symmetric UX, per-app `request_consent`/`revoke_consent`
3. **Client-side PII scrubbing** — regex masking of email, token, secret, credit card patterns before OTLP export
4. **OTLP Telemetry** — OpenTelemetry-based capture and OTLP export
5. **InMemoryMaintenanceAdapter** — testing adapter
6. **CENFServerAdapter** — REST API transport to CENF Server
7. **GitHubIssueAdapter** — auto-issue creation vía GitHub App (JWT → installation token, hash-based dedup)
8. **DiscordAlertAdapter** — rich embed alerts via webhook (truncated stack traces, rate-limited)
9. **GlitchTipAdapter** — self-hosted Sentry-compatible error backend
10. **Tail-based sampling** — capture 100% of errors, sample successful traces

### Out of Scope
- Servidor CENF receiver endpoints (FastAPI Gateway) — separate change
- Auto-triage / Auto-fix AI agents (Agno/gentle-ai) — deferred post-M24
- TUF integration for M20 — separate change
- electron-updater / mobile adapters — M20 concern
- Web force-refresh (SPA Service Worker pattern)

## Capabilities

> Contract between proposal and sdd-spec phases.

### New Capabilities
- `maintenance-manager`: M24 — consent management, error capture with OTLP export, telemetry transport, GitHub issue automation, Discord alerts, GlitchTip integration, PII scrubbing, tail-based sampling

### Modified Capabilities
- None — M04 (ErrorHandlingManager) and M05 (ObservabilityManager) remain unchanged. M24 consumes their output as a new orthogonal layer.

## Approach

Clean Architecture (Ports & Adapters) following M20 UpdateManager pattern. Single `MaintenanceManager` protocol with 5+ adapters. OTel SDK for capture, OTLP for transport, regex-based scrubbing before export. Consent stored in local config (default-off). Adapters injected via `BootstrapOrchestrator`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/core_infrastructure/maintenance/` | New | Full M24 package (ports, models, adapters/) |
| `src/core_infrastructure/__init__.py` | Modified | Root lazy imports for MaintenanceManager |
| `pyproject.toml` | Modified | Optional extras: `maintenance` (aiohttp, pygithub, opentelemetry-sdk) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| GDPR non-compliance (implicit consent) | Low | Default-off, explicit opt-in, symmetric UX, client-side PII scrubbing |
| Discord API rate limits | Medium | Token bucket + truncation (stack ≤ 2000 chars) |
| GitHub API rate limit exhaustion | Medium | Hash-based dedup, no duplicates; CENFServer as proxy |
| OTel dependency bloat | Low | Optional extra `core-cenf[maintenance]` with lazy import guard |
| PII leak in stack traces | Low | Regex hooks before OTLP export (password, token, email, credit card) |

## Rollback Plan

1. Remove `maintenance` extra from `pyproject.toml` and reinstall
2. Delete `src/core_infrastructure/maintenance/`
3. Revert `src/core_infrastructure/__init__.py` imports
4. Rollback config: set `maintenance.enabled: false` before redeploy

## Dependencies

- `opentelemetry-sdk` ≥ 1.30 (OTLP exporter)
- `aiohttp` (CENFServerAdapter, DiscordAdapter)
- `PyGithub` (GitHubIssueAdapter)
- `cryptography` (JWT signing for GitHub App auth)
- All adapters optional (`is None` guard) in `core_infrastructure/__init__.py`

## Success Criteria

- [ ] Protocol passes mypy strict with zero errors
- [ ] `request_consent()` blocks telemetry until user opts in
- [ ] `capture_error()` scrubs PII before OTLP export
- [ ] `InMemoryMaintenanceAdapter` captures all calls for test assertions
- [ ] `GitHubIssueAdapter` creates issues with hash-based dedup
- [ ] `DiscordAlertAdapter` sends rich embed with truncated stack
