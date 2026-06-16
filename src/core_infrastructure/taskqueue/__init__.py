"""TaskQueueManager — async task queue with retry, scheduling, and DLQ.

Provides the TaskQueueManager Protocol contract and in-memory adapter
for development and testing. Production adapters use SAQ/Redis.
"""

from core_infrastructure.taskqueue.adapters.memory_taskqueue_adapter import (
    MemoryTaskQueueAdapter,
)
from core_infrastructure.taskqueue.models import Job, JobRef, JobStatus, QueueConfig
from core_infrastructure.taskqueue.ports import TaskQueueManager

__all__ = [
    "Job",
    "JobRef",
    "JobStatus",
    "MemoryTaskQueueAdapter",
    "QueueConfig",
    "TaskQueueManager",
]
