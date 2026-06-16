"""FeatureFlagManager — dynamic feature activation with context evaluation.

Provides the FeatureFlagManager Protocol contract and in-memory adapter
for development and testing. Production adapters use Unleash.
"""

from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)
from core_infrastructure.feature_flags.models import FeatureFlag, FlagConfig, FlagContext
from core_infrastructure.feature_flags.ports import FeatureFlagManager

__all__ = [
    "FeatureFlag",
    "FeatureFlagManager",
    "FlagConfig",
    "FlagContext",
    "MemoryFeatureFlagAdapter",
]
