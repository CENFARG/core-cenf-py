"""CENF FeatureFlagManager models — FeatureFlag, FlagContext, FlagConfig.

Defines the Pydantic models for the feature flag domain: flag definitions
with rules, context for evaluation, and adapter configuration.

Security: FlagContext.tenant_id is local-only — NEVER sent to external providers.
    FeatureFlag.value is untyped (Any) — callers validate shape before using.
Observability: Flag evaluation emits counters under cenf.feature_flags.*.
@ai-directive: Unknown flags return False (fail-safe). Rules support environment
    matching for staged rollouts. PII-safe — tenant_id stays local.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FlagContext(BaseModel):
    """Evaluation context for feature flag resolution.

    Provides the environment and attributes used by rule-based evaluation.
    Tenant isolation is maintained — tenant_id is used for context-aware
    evaluation but never sent to external providers.

    Attributes:
        tenant_id: Tenant identifier for multi-tenant isolation.
        environment: Deployment environment (development, staging, production).
        attributes: Arbitrary key-value pairs for rule matching.
    """

    tenant_id: str = Field(default="global", min_length=1, max_length=64, description="Tenant identifier.")
    environment: str = Field(
        default="development",
        min_length=1,
        max_length=64,
        description="Deployment environment.",
    )
    attributes: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary key-value pairs for rule matching.",
    )


class FlagConfig(BaseModel):
    """Configuration for FeatureFlagManager adapters.

    Controls the feature flag provider, cache TTL, and default behavior
    for unknown flags (default_all = False means unknown flags return False).

    Attributes:
        provider: Flag provider backend (memory or unleash).
        cache_ttl: Cache time-to-live in seconds.
        default_all: Default enabled state for unknown flags (False = fail-safe).
    """

    provider: Literal["memory", "unleash"] = Field(default="memory", description="Flag provider backend.")
    cache_ttl: int = Field(default=60, ge=1, description="Cache TTL in seconds.")
    default_all: bool = Field(default=False, description="Default enabled state for unknown flags.")


class FeatureFlag(BaseModel):
    """A feature flag definition with rules for context-based evaluation.

    Each flag has a key, enabled state, optional value (payload), and
    optional rules for environment/attribute-based evaluation.

    Attributes:
        key: Unique flag identifier.
        enabled: Whether the flag is enabled by default.
        value: Optional payload returned by get_flag_value().
        rules: List of rule dicts for context-based evaluation.
            Each rule: {"attribute": str, "operator": "eq", "value": str}
    """

    key: str = Field(..., min_length=1, max_length=128, description="Unique flag identifier.")
    enabled: bool = Field(default=False, description="Whether the flag is enabled by default.")
    value: Any = Field(default=None, description="Optional flag payload.")
    rules: list[dict[str, str]] = Field(
        default_factory=list,
        description="Context-based evaluation rules.",
    )
