"""TaskQueueManager adapter implementations.

- MemoryTaskQueueAdapter: In-memory list-backed adapter for dev/testing.
"""

from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import (
    MemoryTaskQueueAdapter,
)

__all__ = ["MemoryTaskQueueAdapter"]
