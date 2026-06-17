"""CENF DynamicPromptingManager — conditional system prompt assembly.

Provides a Protocol-based interface for assembling system prompts
conditionally based on runtime state using dict-based condition matching.
ConditionalPromptAdapter implements the full contract with dot-notation
key resolution and priority-based block ordering.

Security: Never uses eval() or exec() — all condition matching is pure
    dict value comparison.
Observability: All assemble() events emit RED metrics via ObservabilityManager.
@ai-directive: MVP uses dict conditions only. CEL integration is planned
    for a future release.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.dynamic_prompting.adapters.conditional_prompt_adapter import ConditionalPromptAdapter
from core_infrastructure.dynamic_prompting.models import PromptConfig
from core_infrastructure.dynamic_prompting.ports import DynamicPromptingManager, PromptBlock

__all__ = [
    "ConditionalPromptAdapter",
    "DynamicPromptingManager",
    "PromptBlock",
    "PromptConfig",
]
