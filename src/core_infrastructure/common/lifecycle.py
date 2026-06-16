"""CENF lifecycle management — AsyncLifecycle Protocol and HealthStatus model.

Defines the startup/shutdown/health-check contract that all 12 infrastructure
managers implement. The LifecycleManager aggregator allows BootstrapOrchestrator
to start, stop, and health-check all managers in dependency order.

Security: HealthStatus.details MUST NOT contain secrets or credentials.
Observability: Every health() call is logged at DEBUG; degraded/unhealthy
    statuses emit WARN-level logs via LoggerManager.
@ai-directive: All managers implementing AsyncLifecycle MUST make start()
    idempotent and stop() safe to call multiple times.

Author: CENF AI Team
Version: 0.1.0
"""

from datetime import UTC, datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# HealthStatus model
# ---------------------------------------------------------------------------


class HealthStatus(BaseModel):
    """Health-check response for a single infrastructure manager.

    Returned by every manager's ``health()`` method. Aggregated by
    ``LifecycleManager.health_all()`` and used by ``BootstrapOrchestrator``
    to determine system-wide health.

    Attributes:
        service: Manager name (e.g., "config", "logger", "cache").
        status: One of ``healthy``, ``degraded``, or ``unhealthy``.
        version: Semver string of the manager implementation.
        timestamp: UTC timestamp when the check was performed.
        details: Optional structured context (no secrets).
    """

    service: str = Field(..., min_length=1, max_length=128)
    status: Literal["healthy", "degraded", "unhealthy"] = Field(default="healthy")
    version: str = Field(default="0.1.0", pattern=r"^\d+\.\d+\.\d+")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, str] = Field(default_factory=dict)

    def is_healthy(self) -> bool:
        """Return True only when status is exactly 'healthy'.

        Returns:
            bool: ``True`` if ``status == "healthy"``, ``False`` otherwise.
        """
        return self.status == "healthy"


# ---------------------------------------------------------------------------
# AsyncLifecycle Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AsyncLifecycle(Protocol):
    """Contract for asynchronous service lifecycle management.

    Every CENF infrastructure manager MUST implement this protocol.
    ``BootstrapOrchestrator`` uses it to coordinate startup and shutdown
    of all 12 managers using ``asyncio.TaskGroup``.

    Rules:
        - ``start()`` MUST be idempotent (track ``_started`` flag).
        - ``stop()`` MUST be safe to call multiple times (track ``_stopped``).
        - ``health()`` MUST NEVER raise — return ``status="degraded"`` on
          internal failure instead.

    @ai-directive: Do NOT add new methods to this protocol without updating
        LifecycleManager and all 12 manager adapters.
    """

    async def start(self) -> None:
        """Initialize resources (connections, pools, caches).

        Must be idempotent. Called once during bootstrap startup sequence.
        """
        ...

    async def stop(self) -> None:
        """Release resources gracefully (close connections, flush buffers).

        Must be safe to call multiple times. Called during shutdown in
        reverse dependency order.
        """
        ...

    async def health(self) -> HealthStatus:
        """Return the current health status of this manager.

        Must NEVER raise. On internal failure, return a HealthStatus
        with ``status="degraded"`` and diagnostic details.
        """
        ...


# ---------------------------------------------------------------------------
# LifecycleManager aggregator
# ---------------------------------------------------------------------------


class LifecycleManager:
    """Aggregates multiple AsyncLifecycle objects for batch health checks.

    Used by BootstrapOrchestrator to query health across all 12 managers
    and determine system-wide health status.

    Observability: Each health() call is individually wrapped — a single
        failure does not block other managers from reporting.
    """

    def __init__(self) -> None:
        self._services: list[tuple[str, AsyncLifecycle]] = []

    def register(self, service: AsyncLifecycle) -> None:
        """Register a lifecycle-managed service.

        Args:
            service: Any object implementing AsyncLifecycle Protocol.

        Security: The service name is extracted from its health() output.
        """
        self._services.append(("pending", service))

    async def health_all(self) -> dict[str, HealthStatus]:
        """Query health() on every registered service.

        Each service is queried independently — a failure in one does not
        prevent others from reporting.

        Returns:
            dict[str, HealthStatus]: Mapping of service name to health status.
        """
        result: dict[str, HealthStatus] = {}
        for _name, svc in self._services:
            try:
                status = await svc.health()
                result[status.service] = status
            except Exception:
                # Use a fallback HealthStatus when health() itself raises.
                fallback = HealthStatus(
                    service="unknown",
                    status="unhealthy",
                    details={"error": "health_check_raised_exception"},
                )
                result[fallback.service] = fallback
        return result

    async def is_system_healthy(self) -> bool:
        """Return True only if ALL registered services report healthy.

        Returns:
            bool: ``True`` if every service's ``is_healthy()`` returns True.
        """
        statuses = await self.health_all()
        return all(hs.is_healthy() for hs in statuses.values())
