"""FeatureFlagManager adapter implementations.

- MemoryFeatureFlagAdapter: In-memory dict-backed adapter for dev/testing.
"""

from core_infrastructure.feature_flags.adapters.memory_feature_flag_adapter import (
    MemoryFeatureFlagAdapter,
)

__all__ = ["MemoryFeatureFlagAdapter"]
