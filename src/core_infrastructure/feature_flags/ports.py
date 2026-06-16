"""FeatureFlagManager Protocol — the contract every feature flag adapter must satisfy.

Defines the feature flag interface consumed by infrastructure managers
that need runtime-conditional feature activation. Flags support context-based
evaluation for staged rollouts and multi-tenant isolation.

Security: FlagContext.tenant_id is NEVER sent to external providers.
    Evaluation returns False for unknown flags (fail-safe).
Observability: Every evaluation emits counters under cenf.feature_flags.*.
@ai-directive: is_enabled() MUST return False for unknown flags — never throw.
    get_flag_value() returns default on cache miss. refresh() is async for
    Unleash polling but may be sync for memory adapters.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from core_infrastructure.feature_flags.models import FlagContext


@runtime_checkable
class FeatureFlagManager(Protocol):
    """Feature flag contract with context-based evaluation.

    All infrastructure managers that need runtime feature toggling consume
    this interface. Concrete adapters provide in-memory dict (dev/testing)
    or Unleash backend (production).

    Rules:
        - is_enabled() returns False for unknown flags — never raises.
        - get_flag_value() returns the provided default on cache miss.
        - get_all_flags() evaluates rules against context for each flag.
        - refresh() is async — memory adapters may return immediately.
        - Context evaluation: rules are applied via simple environment matching.
          Only "eq" operator is supported; all rules must match for flag to be enabled.
    """

    def is_enabled(
        self,
        flag_key: str,
        context: FlagContext | None = None,
    ) -> bool:
        """Check if a feature flag is enabled.

        Args:
            flag_key: The feature flag identifier.
            context: Optional evaluation context for rule-based decisions.

        Returns:
            bool: True if the flag is enabled and all rules pass.
        """
        ...

    def get_flag_value(
        self,
        flag_key: str,
        context: FlagContext | None = None,
        default: Any = None,
    ) -> Any:
        """Get the value (payload) of a feature flag.

        Args:
            flag_key: The feature flag identifier.
            context: Optional evaluation context.
            default: Value returned if the flag is not found.

        Returns:
            Any: The flag's value, or default if not found.
        """
        ...

    def get_all_flags(
        self,
        context: FlagContext | None = None,
    ) -> dict[str, bool]:
        """Get the enabled state of all feature flags.

        Args:
            context: Optional evaluation context for rule-based decisions.

        Returns:
            dict[str, bool]: Map of flag keys to their enabled state.
        """
        ...

    async def refresh(self) -> None:
        """Refresh the local flag cache from the provider.

        For memory adapters, this is a no-op. For Unleash adapters,
        this polls the Unleash API for updated flag definitions.
        """
        ...
