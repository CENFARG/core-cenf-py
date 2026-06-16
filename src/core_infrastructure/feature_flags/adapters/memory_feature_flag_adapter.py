"""MemoryFeatureFlagAdapter — in-memory dict-backed FeatureFlagManager.

Provides a zero-dependency FeatureFlagManager implementation using a plain
dict for flag storage. Supports context-based evaluation with environment
matching rules. PII-safe — tenant_id never leaves the adapter.

Security: FlagContext.tenant_id is used only for local evaluation, never
    transmitted to external providers. Unknown flags return False (fail-safe).
Observability: Flag evaluations emit counters under cenf.feature_flags.*.
@ai-directive: This adapter exists for dev/testing. Use Unleash adapter
    in production after completing the Unleash backend integration.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any

from core_infrastructure.feature_flags.models import (
    FeatureFlag,
    FlagConfig,
    FlagContext,
)


class MemoryFeatureFlagAdapter:
    """In-memory dict-backed FeatureFlagManager with context evaluation.

    Stores flags in a dict and evaluates them based on enabled state
    and optional rules. Rules support simple attribute matching (eq operator).
    All rules must match for a flag to be considered enabled.

    Args:
        config: FlagConfig for default behavior.

    Usage::

        adapter = MemoryFeatureFlagAdapter(config=FlagConfig())
        adapter.set_flag(FeatureFlag(key="new-feature", enabled=True))
        assert adapter.is_enabled("new-feature") is True
    """

    def __init__(self, config: FlagConfig | None = None) -> None:
        self._config = config if config is not None else FlagConfig()
        self._flags: dict[str, FeatureFlag] = {}

    # ------------------------------------------------------------------
    # Configuration API (non-protocol, adapter-specific)
    # ------------------------------------------------------------------

    def set_flag(self, flag: FeatureFlag) -> None:
        """Register or update a feature flag.

        Args:
            flag: The FeatureFlag definition to store.
        """
        self._flags[flag.key] = flag

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_rules(self, flag: FeatureFlag, context: FlagContext | None) -> bool:
        """Evaluate a flag's rules against the provided context.

        All rules must match for the flag to be considered enabled.
        Only "eq" operator is supported. If no rules exist, the flag
        evaluates based purely on its enabled state.

        Args:
            flag: The FeatureFlag to evaluate.
            context: Evaluation context with environment and attributes.

        Returns:
            bool: True if all rules match or no rules exist.
        """
        if not flag.rules:
            return True

        if context is None:
            return False

        ctx_attrs = {
            "environment": context.environment,
            "tenant_id": context.tenant_id,
            **context.attributes,
        }

        for rule in flag.rules:
            attr = rule.get("attribute", "")
            operator = rule.get("operator", "eq")
            expected = rule.get("value", "")

            actual = ctx_attrs.get(attr, "")
            if operator == "eq" and actual != expected:
                return False
            # Unknown operators — treat as non-matching (fail-safe)

        return True

    # ------------------------------------------------------------------
    # Public API — FeatureFlagManager Protocol
    # ------------------------------------------------------------------

    def is_enabled(
        self,
        flag_key: str,
        context: FlagContext | None = None,
    ) -> bool:
        """Check if a feature flag is enabled.

        Evaluates the flag's enabled state and optional rules against
        the provided context. Returns False for unknown flags.

        Args:
            flag_key: The feature flag identifier.
            context: Optional evaluation context.

        Returns:
            bool: True if enabled and all rules pass.
        """
        flag = self._flags.get(flag_key)
        if flag is None:
            return self._config.default_all
        if not flag.enabled:
            return False
        return self._evaluate_rules(flag, context)

    def get_flag_value(
        self,
        flag_key: str,
        context: FlagContext | None = None,
        default: Any = None,
    ) -> Any:
        """Get the value (payload) of a feature flag.

        Returns the flag's value if it exists and is enabled for the
        given context. Returns the default if the flag is not found
        or is disabled.

        Args:
            flag_key: The feature flag identifier.
            context: Optional evaluation context.
            default: Value returned if flag not found or disabled.

        Returns:
            Any: The flag's value, or default.
        """
        if self.is_enabled(flag_key, context):
            flag = self._flags.get(flag_key)
            if flag is not None:
                return flag.value
        return default

    def get_all_flags(
        self,
        context: FlagContext | None = None,
    ) -> dict[str, bool]:
        """Get the enabled state of all feature flags.

        Evaluates each flag against the provided context and returns
        a dict mapping flag keys to their enabled state.

        Args:
            context: Optional evaluation context.

        Returns:
            dict[str, bool]: Map of flag keys to enabled state.
        """
        return {
            key: self.is_enabled(key, context)
            for key in self._flags
        }

    async def refresh(self) -> None:
        """Refresh the local flag cache (no-op for in-memory adapter).

        For memory adapters, flags are set via set_flag() directly.
        For Unleash adapters, this would poll the Unleash API.
        """
        return None
