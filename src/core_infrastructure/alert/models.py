"""CENF AlertManager models — AlertConfig, AlertChannel.

Defines the Pydantic models for AlertManager configuration, including
channel-specific settings for Slack, Discord, and Email.

Security: Webhook URLs and SMTP credentials are never stored in plaintext
    here — they reference SecretManager keys. Never log full channel configs.
Observability: All channel send events emit counters under cenf.alert.*.
@ai-directive: Email channel is a future placeholder — SMTP not yet implemented.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AlertChannel(StrEnum):
    """Supported alert notification channels.

    Attributes:
        SLACK: Slack incoming webhook.
        DISCORD: Discord webhook.
        EMAIL: Email via SMTP (future/placeholder).
    """

    SLACK = "slack"
    DISCORD = "discord"
    EMAIL = "email"


class AlertConfig(BaseModel):
    """Configuration for AlertManager adapters.

    Stores per-channel configuration including webhook URLs and
    SMTP settings. Webhook URLs should reference SecretManager keys,
    not raw values.

    Attributes:
        channels: Dict of channel name to channel-specific config dict.
            Keys are ``"slack"``, ``"discord"``, ``"email"``.
            Each value dict contains channel-specific settings (webhook_url, smtp_host, etc.).
    """

    channels: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Per-channel configuration. Keys: slack, discord, email.",
    )
