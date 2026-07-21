"""TaskQueueManager adapter implementations.

- MemoryTaskQueueAdapter: In-memory list-backed adapter for dev/testing.
- SaQAdapter: Redis-backed SAQ adapter for production.
"""

from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import (
    MemoryTaskQueueAdapter,
)
try:
    from core_infrastructure.taskqueue.adapters.saq_adapter import SaQAdapter
except ImportError:
    SaQAdapter = None  # type: ignore[assignment,misc]

__all__ = ["MemoryTaskQueueAdapter", "SaQAdapter"]
