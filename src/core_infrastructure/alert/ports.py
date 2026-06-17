"""AlertManager Protocol — multi-channel alert dispatch with rule-based triggers.

Defines the contract for dispatching alerts to Slack, Discord, and Email
based on configurable dict-based rules. AlertRule models represent trigger
conditions with throttle settings to prevent alert spam.

Security: Never include secrets or PII in alert payloads. All channel
    credentials are read via SecretManager.
Observability: All dispatch events emit RED metrics under cenf.alert.*.
@ai-directive: Dict-based condition matching for MVP. CEL integration
    is planned for a future release.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class AlertLevel(StrEnum):
    """Severity levels for alert dispatch.

    Used by AlertRule to determine urgency and by DispatchAlertAdapter
    to format alert messages appropriately for each channel.

    Attributes:
        INFO: Informational alert, no action required.
        WARNING: Potential issue, attention recommended.
        CRITICAL: Immediate action required.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertRule(BaseModel):
    """A rule that triggers an alert when its condition matches an event.

    Each rule defines a dict-based condition, target channels, severity
    level, and a throttle window to prevent duplicate alerts.

    Attributes:
        rule_id: Unique identifier for the rule.
        condition: Dict of key:value pairs. ALL must match for the rule to fire.
            Keys support dot-notation (e.g., ``"metrics.error_rate"``).
        level: The alert severity level (default WARNING).
        channels: List of target channel names (``"slack"``, ``"discord"``, ``"email"``).
        throttle_seconds: Minimum seconds between repeated firings of the same rule.
    """

    model_config = {"extra": "forbid", "frozen": True}

    rule_id: str = Field(..., min_length=1, max_length=128, description="Unique rule identifier.")
    condition: dict[str, Any] = Field(..., description="Dict of key:value pairs. ALL must match to fire.")
    level: AlertLevel = Field(default=AlertLevel.WARNING, description="Alert severity level.")
    channels: list[str] = Field(..., min_length=1, description="Target channels: slack, discord, email.")
    throttle_seconds: int = Field(
        default=60,
        ge=0,
        le=3600,
        description="Minimum seconds between repeated firings of the same rule.",
    )


@runtime_checkable
class AlertManager(Protocol):
    """Multi-channel alert dispatch contract with rule-based triggers.

    Dispatches alerts to Slack, Discord, and Email based on registered
    AlertRule conditions. Rules are evaluated against event_context dicts
    with throttle windows to prevent alert spam.

    Rules:
        - send_alert() sends to ALL configured channels. Failures are logged, not raised.
        - register_rule() adds a rule to the internal registry.
        - evaluate_and_alert() checks all rules and dispatches matching alerts.
        - Alert failures NEVER block the main flow — fire-and-forget with error logging.
        - Dict-based condition matching: all key:value pairs must match.
    """

    async def send_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Dispatch an alert to all configured channels.

        Formats the message according to each channel's requirements
        (Slack, Discord, Email) and dispatches concurrently. Failures
        in one channel do not prevent delivery to others.

        Args:
            level: Alert severity level.
            title: Short alert title.
            message: Detailed alert message body.
            metadata: Optional structured metadata (e.g., host, service).
        """
        ...

    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule with dict-based condition.

        Rules are stored in-memory and evaluated by ``evaluate_and_alert()``.
        Registering a rule with the same ``rule_id`` overwrites the previous one.

        Args:
            rule: The AlertRule to register.
        """
        ...

    async def evaluate_and_alert(self, event_context: dict[str, Any]) -> None:
        """Evaluate all registered rules against event_context and dispatch matches.

        For each registered rule, checks if its dict condition matches
        the event_context. If it matches AND the throttle window allows,
        dispatches an alert via ``send_alert()``.

        Args:
            event_context: Runtime event data to match against rule conditions.
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: A valid JSON Schema object describing the
                AlertConfig model.
        """
        ...
