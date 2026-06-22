---
sidebar_position: 15
---

# AlertManager (M15)

Multi-channel alert dispatch with rule-based triggers. Supports Slack, Discord, and Email channels. Rules use dict-based condition matching with throttle windows per rule to prevent alert storms. **Fire-and-forget — never block main flow if alert dispatch fails.**

## Protocol

`AlertManager` is a `@runtime_checkable` `Protocol` in `core_infrastructure.alert.ports`.

### `async send_alert(level, title, message, metadata) → None`

Dispatch an alert to all configured channels. Formats the message per channel (Slack, Discord, Email) and dispatches concurrently. Failures in one channel do not prevent delivery to others.

```python
async def send_alert(
    self,
    level: AlertLevel,
    title: str,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `level` | `AlertLevel` | Severity: `INFO`, `WARNING`, `CRITICAL` |
| `title` | `str` | Short alert title |
| `message` | `str` | Detailed alert message body |
| `metadata` | `dict \| None` | Optional structured metadata (host, service, error details) |

---

### `register_rule(rule) → None`

Register an alert rule with dict-based condition. Overwrites previous rule with same `rule_id`.

```python
def register_rule(self, rule: AlertRule) -> None: ...
```

| Param | Type | Description |
|-------|------|-------------|
| `rule` | `AlertRule` | The rule to register |

---

### `async evaluate_and_alert(event_context) → None`

Evaluate all registered rules against `event_context` and dispatch matching alerts. Respects throttle windows — rules that fired within `throttle_seconds` are skipped.

```python
async def evaluate_and_alert(self, event_context: dict[str, Any]) -> None: ...
```

---

### `get_json_schema() → dict[str, Any]` *(static)*

Return JSON Schema for agent discovery (AX).

```python
@staticmethod
def get_json_schema() -> dict[str, Any]: ...
```

---

## Models

**File:** `core_infrastructure.alert.ports` (AlertLevel, AlertRule), `core_infrastructure.alert.models` (AlertConfig, AlertChannel)

### `AlertLevel` (StrEnum)

| Value | Meaning |
|-------|---------|
| `INFO` | Informational, no action required |
| `WARNING` | Potential issue, attention recommended |
| `CRITICAL` | Immediate action required |

### `AlertRule`

Frozen Pydantic model (`extra="forbid"`).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `rule_id` | `str` (1–128) | required | Unique rule identifier |
| `condition` | `dict[str, Any]` | required | Dict of key:value pairs. ALL must match to fire. Dot-notation keys supported |
| `level` | `AlertLevel` | `WARNING` | Alert severity level |
| `channels` | `list[str]` (≥1) | required | Target channels: `"slack"`, `"discord"`, `"email"` |
| `throttle_seconds` | `int` (0–3600) | `60` | Minimum seconds between repeated firings |

### `AlertChannel` (StrEnum)

`SLACK`, `DISCORD`, `EMAIL` (email is a future placeholder — SMTP not yet implemented).

### `AlertConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `channels` | `dict[str, dict[str, str]]` | `{}` | Per-channel config. Keys: `"slack"`, `"discord"`, `"email"`. Webhook URLs reference SecretManager keys |

---

## Adapters

| Adapter | Backend | Use Case |
|---------|---------|----------|
| `DispatchAlertAdapter` | `ExternalAPIManager` + `smtplib` | Production — Slack/Discord via HTTP webhooks, Email via SMTP |

**Channel dispatch:** Slack and Discord use `ExternalAPIManager` (M11) for HTTP POST to webhook URLs. Email uses `smtplib` with SMTP config from ConfigManager and credentials from SecretManager. Rule evaluation uses dict-based condition matching identical to `DynamicPromptingManager`. `asyncio.Lock` protects the rules registry and throttle state.

---

## Usage Example

```python
from core_infrastructure.alert.adapters.dispatch_alert_adapter import DispatchAlertAdapter
from core_infrastructure.alert.ports import AlertLevel, AlertRule

# DispatchAlertAdapter depends on ExternalAPIManager for HTTP dispatch
alert_mgr = DispatchAlertAdapter(
    config=config,
    secret_manager=secrets,
    logger=logger,
    external_api=http_client,
    error_handler=error_handler,
)

# Register a rule: fire when a document fails processing
rule = AlertRule(
    rule_id="doc_processing_failed",
    condition={"event_type": "document_failed", "severity": "critical"},
    level=AlertLevel.CRITICAL,
    channels=["slack"],
    throttle_seconds=60,
)
alert_mgr.register_rule(rule)

# Evaluate and alert — rule fires when condition matches
await alert_mgr.evaluate_and_alert({
    "event_type": "document_failed",
    "severity": "critical",
    "document_id": "doc-001",
    "error": "OCR engine timeout after 30s",
    "pipeline_step": "extract_text",
})

# Direct send (bypasses rule matching)
await alert_mgr.send_alert(
    level=AlertLevel.WARNING,
    title="Pipeline throughput degraded",
    message="Processing rate dropped below 10 docs/min",
    metadata={"current_rate": "7.2", "threshold": "10.0"},
)

# Register multiple rules with different channels
alert_mgr.register_rule(AlertRule(
    rule_id="high_error_rate",
    condition={"metrics.error_rate": 0.05},
    level=AlertLevel.CRITICAL,
    channels=["slack", "email"],
    throttle_seconds=300,
))
```

---

## @ai-directive

> **Fire-and-forget. Never block main flow if alert dispatch fails.** All channel credentials are read via SecretManager. Dict-based condition matching for MVP — CEL integration is planned for a future release. Never include secrets or PII in alert payloads. Email channel is a future placeholder — SMTP not yet implemented.

## Related

- [ExternalAPIManager](external-api-manager.md) — used for Slack/Discord HTTP webhook dispatch
- [SecretManager](secret-manager.md) — supplies channel credentials (webhook URLs, SMTP auth)
- [ConfigManager](config-manager.md) — supplies `alert.channels` config section
- [DynamicPromptingManager](dynamic-prompting-manager.md) — same dict-based condition matching pattern
