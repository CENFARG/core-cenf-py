# M24 MaintenanceManager — Technical Design

## Architecture

```
MaintenanceManager (Protocol)
├── InMemoryMaintenanceAdapter (testing)
├── GitHubIssueAdapter (creates issues via GitHub App)
├── DiscordAlertAdapter (webhook to Discord)
├── CENFServerAdapter (REST API to CENF server)
└── GlitchTipAdapter (self-hosted error tracking)

Helpers:
├── pii_scrubber.py → regex-based PII masking
├── consent_store.py → JSON-based consent persistence
└── telemetry_collector.py → OTLP metric collection
```

## Protocol (6 methods)

| Method | Returns | Description |
|--------|---------|-------------|
| `is_consent_granted(app_id)` | `bool` | Check GDPR consent |
| `request_consent(app_id, user_id)` | `ConsentResult` | Record explicit consent |
| `revoke_consent(app_id, user_id)` | `None` | Purge all user data |
| `capture_error(app_id, error, context)` | `ErrorReport` | Capture + scrub PII |
| `report_error(report)` | `ReportResult` | Send to transport |
| `send_telemetry(app_id, metrics)` | `None` | OTLP metrics |

## Key Decisions

1. **GDPR by design**: Consent gate BEFORE any data leaves the client. "Default-off".
2. **PII scrubbing**: Regex-based at capture time. Never send raw data.
3. **Tail-based sampling**: Filtered at adapter level — only severity > WARNING.
4. **Adapter fallback**: Primary adapter fails → secondary adapter (Discord).
5. **GitHub App** (not PAT): JWT-based ephemeral tokens, granular permissions.
6. **OTLP transport**: OpenTelemetry standard, no vendor lock-in.

## Files

| File | Purpose |
|------|---------|
| `ports.py` | MaintenanceManager Protocol |
| `models.py` | ErrorReport, ConsentResult, ReportResult |
| `adapters/__init__.py` | Exports |
| `adapters/in_memory_maintenance_adapter.py` | Testing |
| `adapters/github_issue_adapter.py` | GitHub Issues |
| `adapters/discord_alert_adapter.py` | Discord webhook |
| `adapters/cenf_server_adapter.py` | CENF REST API |
| `adapters/glitchtip_adapter.py` | GlitchTip self-hosted |
| `pii_scrubber.py` | PII masking |
| `consent_store.py` | JSON consent persistence |
