"""M24 MaintenanceManager adapters package.

Available adapters:
- InMemoryMaintenanceAdapter (testing, zero deps)
- GitHubIssueAdapter (requires: PyGithub, cryptography)
- DiscordAlertAdapter (requires: aiohttp)
- CENFServerAdapter (requires: aiohttp)
- GlitchTipAdapter (requires: aiohttp)

Usage:

    from core_infrastructure.maintenance.adapters.in_memory_maintenance_adapter import (
        InMemoryMaintenanceAdapter,
    )

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from core_infrastructure.maintenance.adapters.in_memory_maintenance_adapter import (
    InMemoryMaintenanceAdapter,
)

__all__ = [
    "InMemoryMaintenanceAdapter",
]
