---
Spec_ID: SPEC_M15
Title: AlertManager Specification
Version: 0.1.0-MVP
Maturity_Level: Semilla
Status: Draft
Target_Agent: sdd-apply
Context_Tags: [alerts, slack, discord, email, cel-rules]
Dependency_Hashes: []
Last_Updated: "2026-06-17"
---

# SPEC_M15: AlertManager

## Purpose

Provide multi-channel alert dispatch (Slack, Discord, Email) based on configurable CEL rules. Consumes events from multiple managers (logs, errors, metrics, circuit breakers) and triggers notifications with rate limiting per channel.

**Does NOT**: Include secrets or PII in alert payloads, block the main flow if alert sending fails.

> **NOTE**: This manager is SPEC ONLY — implementation planned for a future phase.

## Python Protocol

```python
from __future__ import annotations
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

class AlertLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@runtime_checkable
class AlertManager(Protocol):
    """@ai-directive: Use RateLimiterManager to avoid spam. Never block the main flow for an alert."""

    async def send_alert(self, level: AlertLevel, title: str, message: str, metadata: dict[str, Any] | None = None) -> None:
        """Dispatch an alert to configured channels."""
        ...

    def register_rule(self, rule_id: str, condition_cel: str, level: AlertLevel, channels: list[str]) -> None:
        """Register an alert rule with CEL condition."""
        ...

    async def evaluate_and_alert(self, event_context: dict[str, Any]) -> None:
        """Evaluate all registered rules against the event context and dispatch matching alerts."""
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery."""
        ...
```

## Boundary Validation (Pydantic V2)

```python
class AlertSettings(BaseModel):
    slack_webhook_url: str | None = Field(default=None, min_length=1)
    discord_webhook_url: str | None = Field(default=None, min_length=1)
    email_smtp_host: str | None = Field(default=None)
    email_smtp_port: int | None = Field(default=587, ge=1, le=65535)
    email_from: str | None = Field(default=None)
    email_to: list[str] = Field(default_factory=list)
    rules_yaml_path: str | None = Field(default=None)
    rate_limit_per_channel_per_minute: int = Field(default=10, ge=1, le=60)

class AlertRule(BaseModel):
    rule_id: str = Field(min_length=1, max_length=128)
    condition_cel: str = Field(min_length=1, description="CEL expression that triggers the alert")
    level: AlertLevel = Field(default=AlertLevel.WARNING)
    channels: list[str] = Field(min_length=1, description="Target channels: slack, discord, email")
    cooldown_seconds: int = Field(default=300, ge=60, le=3600)
```

## Gherkin Scenarios

### Scenario: Send alert to Slack

- GIVEN Slack webhook URL is configured
- WHEN `send_alert(AlertLevel.CRITICAL, "DB Down", "PostgreSQL unreachable")` is called
- THEN a POST request is sent to the Slack webhook
- AND the message includes title, level, and timestamp

### Scenario: CEL rule triggers alert

- GIVEN rule registered: `error_rate > 0.05` → CRITICAL → ["slack"]
- WHEN `evaluate_and_alert({"error_rate": 0.10})` is called
- THEN the CEL expression evaluates to True
- AND a CRITICAL alert is sent to Slack

### Scenario: Rate limiting prevents spam

- GIVEN rate limit is 10 alerts per channel per minute
- WHEN 15 alerts are sent to Slack within 1 minute
- THEN only the first 10 are delivered
- AND the remaining 5 are dropped with a warning log

### Scenario: Alert failure does not block main flow

- GIVEN the Slack webhook is unreachable
- WHEN `send_alert()` is called
- THEN the error is logged at ERROR level
- AND the method returns without raising
- AND the main application flow continues uninterrupted

### Scenario: No PII in alert payloads

- GIVEN an alert triggered by an AuthError with user details
- WHEN the alert is dispatched
- THEN the message does NOT include raw tokens, passwords, or PII
- AND only sanitized error type and context are included

### Scenario: Multi-channel dispatch

- GIVEN rule targets ["slack", "discord", "email"]
- WHEN the rule condition is met
- THEN alerts are sent to all three channels concurrently
- AND failure in one channel does not prevent delivery to others

## Error Classification

| Error | Classification | Handling |
|-------|---------------|----------|
| Webhook unreachable | TRANSIENT | Log error, return silently (fire-and-forget) |
| Invalid CEL rule | VALIDATION | Log at registration time, skip rule |
| SMTP misconfiguration | PERMANENT | Log at startup, disable email channel |
| Rate limit exceeded | — | Drop alert, log warning |

## RED Metrics

- `cenf.alert.sent_total{channel="..."}` (counter)
- `cenf.alert.errors_total` (counter)
- `cenf.alert.send_duration_seconds` (histogram)
- `cenf.alert.rate_limited_total{channel="..."}` (counter)

## Test Requirements

- **Unit**: `InMemoryAlertAdapter` — collects alerts in list for assertions.
- **Integration**: `MultiChannelAlertAdapter` with mock HTTP endpoints for Slack/Discord.
- **E2E**: Verify fire-and-forget behavior (alert failure doesn't block main flow).

## Do's and Don'ts

**Do**:
- Configure channels via YAML (slack_webhook_url, discord_webhook_url, email_smtp)
- Use CEL rules for trigger conditions
- Integrate RateLimiterManager per channel to prevent spam
- Use async HTTP I/O — never block the event-loop
- Fire-and-forget with error logging

**Don't**:
- Include secrets or PII in alert payloads
- Block the main operation if alert sending fails
- Send alerts synchronously (must be async)
