"""M24 MaintenanceManager models — ErrorReport, ConsentResult, ReportResult, MaintenanceConfig.

Defines the Pydantic models for M24 data transfer and configuration.
ErrorReport carries PII-scrubbed error data. ConsentResult tracks GDPR
opt-in/revoke. ReportResult captures transport outcomes.

Security:
    - ErrorReport.stack_trace MUST be scrubbed before storage/transport.
    - ConsentResult.status is validated (GRANTED|REVOKED|PENDING).
    - MaintenanceConfig defaults to enabled=False (consent gate default-off).
Observability:
    - ErrorReport includes severity and tags for filtering.
    - MaintenanceConfig.error_sample_rate controls tail-based sampling.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ErrorReport(BaseModel):
    """PII-scrubbed error report for transport.

    Produced by capture_error() after PII masking. Contains app identity,
    exception message, stack trace, and optional context for debugging.

    Attributes:
        app_id: Application identifier where the error occurred.
        message: Exception message (PII-scrubbed).
        stack_trace: Stack trace text (PII-scrubbed).
        version: App version at time of error (SemVer).
        os: Operating system identifier (e.g., "linux", "windows", "macos").
        arch: CPU architecture (optional, e.g., "x64", "arm64").
        python_version: Python runtime version.
        timestamp: When the error was captured (UTC).
        context: Arbitrary context key-value pairs (PII-scrubbed).
        severity: Error severity level (TRACE|DEBUG|INFO|WARNING|ERROR|CRITICAL).
        tags: Optional key-value tags for filtering.
    """

    model_config = {"extra": "forbid", "frozen": True}

    app_id: str = Field(
        ..., min_length=1, max_length=128,
        description="Application identifier where the error occurred.",
    )
    message: str = Field(
        ..., max_length=8192,
        description="Exception message (PII-scrubbed).",
    )
    stack_trace: str = Field(
        default="", max_length=65536,
        description="Stack trace text (PII-scrubbed).",
    )
    version: str = Field(
        ..., min_length=1, max_length=64,
        description="App version at time of error (SemVer).",
    )
    os: str = Field(
        ..., min_length=1, max_length=32,
        description="Operating system (linux, windows, macos).",
    )
    arch: str | None = Field(
        default=None, max_length=16,
        description="CPU architecture (x64, arm64).",
    )
    python_version: str | None = Field(
        default=None, max_length=32,
        description="Python runtime version.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the error was captured (UTC).",
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Arbitrary context (PII-scrubbed).",
    )
    severity: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="ERROR",
        description="Error severity level.",
    )
    tags: dict[str, str] | None = Field(
        default=None,
        description="Optional key-value tags for filtering.",
    )


class ConsentResult(BaseModel):
    """Result of a consent operation (grant or revoke).

    Attributes:
        app_id: Application identifier.
        user_id: User identifier who granted/revoked consent.
        status: Consent status (GRANTED, REVOKED, or PENDING).
        timestamp: When the consent operation occurred (UTC).
    """

    model_config = {"extra": "forbid", "frozen": True}

    app_id: str = Field(
        ..., min_length=1, max_length=128,
        description="Application identifier.",
    )
    user_id: str = Field(
        ..., min_length=1, max_length=256,
        description="User identifier who granted/revoked consent.",
    )
    status: Literal["GRANTED", "REVOKED", "PENDING"] = Field(
        ..., description="Consent status.",
    )
    timestamp: datetime = Field(
        ..., description="When the consent operation occurred (UTC).",
    )


class ReportResult(BaseModel):
    """Result of a report_error() transport attempt.

    Attributes:
        success: Whether the transport succeeded.
        target: Target identifier (e.g., "discord", "github", "cenf-server").
        error: Error description on failure, or None on success.
    """

    model_config = {"extra": "forbid", "frozen": True}

    success: bool = Field(
        ..., description="Whether the transport succeeded.",
    )
    target: str = Field(
        ..., min_length=1, max_length=64,
        description="Target identifier (discord, github, cenf-server, glitchtip).",
    )
    error: str | None = Field(
        default=None, max_length=2048,
        description="Error description on failure, or None on success.",
    )


class MaintenanceConfig(BaseModel):
    """Configuration for MaintenanceManager adapters.

    Controls error reporting, consent behaviour, GitHub integration,
    Discord alerts, CENF server and GlitchTip endpoints, telemetry,
    and tail-based sampling.

    Security:
        enabled defaults to False — telemetry is off by default.
        consent_required must be True for GDPR compliance.
    Attributes:
        enabled: Master switch for error reporting (default: False).
        consent_required: Whether consent is required before sending data.
        app_id: Default application identifier.
        app_version: Default application version.
        github_repo: GitHub repository for auto-issues (e.g., "owner/repo").
        github_app_id: GitHub App ID for JWT-based auth.
        discord_webhook_url: Discord webhook URL for alerts.
        cenf_server_url: CENF server REST API endpoint.
        glitchtip_dsn: GlitchTip DSN for self-hosted error tracking.
        telemetry_enabled: Whether OTLP telemetry is active.
        error_sample_rate: Tail-based sampling rate (0.0 to 1.0).
    """

    model_config = {"extra": "forbid"}

    enabled: bool = Field(
        default=False,
        description="Master switch for error reporting (default: False).",
    )
    consent_required: bool = Field(
        default=True,
        description="Whether consent is required before sending data.",
    )
    app_id: str = Field(
        default="", max_length=128,
        description="Default application identifier.",
    )
    app_version: str = Field(
        default="0.1.0", max_length=64,
        description="Default application version.",
    )
    github_repo: str | None = Field(
        default=None, max_length=256,
        description="GitHub repository for auto-issues (owner/repo).",
    )
    github_app_id: str | None = Field(
        default=None, max_length=64,
        description="GitHub App ID for JWT-based auth.",
    )
    discord_webhook_url: str | None = Field(
        default=None, max_length=2048,
        description="Discord webhook URL for alerts.",
    )
    cenf_server_url: str | None = Field(
        default=None, max_length=2048,
        description="CENF server REST API endpoint.",
    )
    glitchtip_dsn: str | None = Field(
        default=None, max_length=2048,
        description="GlitchTip DSN for self-hosted error tracking.",
    )
    telemetry_enabled: bool = Field(
        default=False,
        description="Whether OTLP telemetry is active.",
    )
    error_sample_rate: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Tail-based sampling rate (0.0 to 1.0).",
    )

    @field_validator("error_sample_rate")
    @classmethod
    def _validate_sample_rate(cls, v: float) -> float:
        """Ensure sample rate is between 0.0 and 1.0."""
        if v < 0.0 or v > 1.0:
            msg = f"error_sample_rate must be between 0.0 and 1.0, got {v}"
            raise ValueError(msg)
        return v
