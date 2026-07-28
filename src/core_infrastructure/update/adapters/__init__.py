"""UpdateManager adapter implementations."""

from core_infrastructure.update.adapters.in_memory_update_adapter import (
    InMemoryUpdateAdapter,
)
from core_infrastructure.update.adapters.http_update_adapter import (
    HttpUpdateAdapter,
)
from core_infrastructure.update.adapters.pip_update_adapter import (
    PipUpdateAdapter,
)
from core_infrastructure.update.adapters.web_update_adapter import (
    WebUpdateAdapter,
)
from core_infrastructure.update.adapters.github_release_adapter import (
    GitHubReleaseAdapter,
)
from core_infrastructure.update.adapters.android_update_adapter import (
    AndroidUpdateAdapter,
)

__all__ = [
    "InMemoryUpdateAdapter",
    "HttpUpdateAdapter",
    "PipUpdateAdapter",
    "WebUpdateAdapter",
    "GitHubReleaseAdapter",
    "AndroidUpdateAdapter",
]
