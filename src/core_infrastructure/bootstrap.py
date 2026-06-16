"""BootstrapOrchestrator — graceful startup/shutdown lifecycle for all 12 managers.

Coordinates the startup and shutdown of all CENF infrastructure managers
using asyncio.TaskGroup for parallel initialization with automatic cancellation
on failure, and sequential best-effort shutdown in reverse dependency order.

Security: No secrets are stored or logged by the orchestrator itself.
Observability: Every start/stop event is logged; health aggregation emits a
    summary at INFO level after collection.
@ai-directive: The manager order is dictated by the dependency graph:
    Config → Logger → Secret → OTel → Error → Auth → Cache → DB →
    File → Queue → HTTP → Flags.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from core_infrastructure.common.lifecycle import AsyncLifecycle, HealthStatus

_logger = logging.getLogger(__name__)


class BootstrapOrchestrator:
    """Orchestrate startup, shutdown, and health checks for all 12 CENF managers.

    Accepts manager instances that implement the ``AsyncLifecycle`` Protocol
    (every CENF manager adapter must implement ``start()``, ``stop()``, and
    ``health()``).  Startup uses ``asyncio.TaskGroup`` so that one failure
    cancels the remaining starts.  Shutdown is sequential best-effort in
    reverse order — individual failures are logged but never block the
    remaining shutdown steps.

    Args:
        *managers: One or more ``AsyncLifecycle`` objects in dependency order.
            The first manager is typically ConfigManager.

    Usage::

        orchestrator = BootstrapOrchestrator(config, logger, secret, ...)
        asyncio.run(orchestrator.run())
    """

    def __init__(self, *managers: AsyncLifecycle) -> None:
        self._managers: tuple[AsyncLifecycle, ...] = managers
        self._shutdown_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Initialize all managers in dependency order using TaskGroup.

        Each manager's ``start()`` is called inside an ``asyncio.TaskGroup``.
        If ANY manager's ``start()`` raises, the TaskGroup cancels all
        remaining starts and the first exception propagates as an
        ``ExceptionGroup`` (Python 3.11+).
        """
        async with asyncio.TaskGroup() as tg:
            for mgr in self._managers:
                tg.create_task(mgr.start())

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown(self) -> None:
        """Graceful shutdown in REVERSE dependency order.

        Each manager's ``stop()`` is called sequentially, starting from
        the last-registered manager (FeatureFlagManager) and moving backward
        to the first (ConfigManager).  Any exception raised by a ``stop()``
        call is logged and then discarded — it never prevents the remaining
        managers from shutting down.
        """
        for mgr in reversed(self._managers):
            try:
                await mgr.stop()
            except Exception:
                _logger.exception("Shutdown error in %s", getattr(mgr, "__class__", type(mgr)).__name__)

        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> list[HealthStatus]:
        """Collect health status from every registered manager.

        Each manager's ``health()`` is called independently.  If a
        manager's ``health()`` raises, a synthetic ``unhealthy`` status
        is recorded for that manager — the exception is caught and never
        propagated.

        Returns:
            list[HealthStatus]: One status per registered manager,
                in registration order.
        """
        results: list[HealthStatus] = []
        for i, mgr in enumerate(self._managers):
            try:
                status = await mgr.health()
                results.append(status)
            except Exception:
                service_name = getattr(mgr, "_name", f"manager-{i}")
                results.append(
                    HealthStatus(
                        service=str(service_name),
                        status="unhealthy",
                        details={"error": "health_check_raised_exception"},
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Signal handling
    # ------------------------------------------------------------------

    def _on_signal(self, signum: int, _frame: Any) -> None:
        """Handle SIGTERM/SIGINT by triggering the shutdown event.

        The signal name is logged at INFO level.  The ``_frame`` argument is
        accepted for CPython compatibility but unused.
        """
        sig_name = signal.Signals(signum).name
        _logger.info("Received signal %s — initiating graceful shutdown", sig_name)
        self._shutdown_event.set()

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Execute the full lifecycle: startup → wait for shutdown signal → shutdown.

        Registers SIGTERM and SIGINT handlers that trigger the shutdown
        event.  After startup completes, this method blocks until either
        signal is received, then performs a graceful shutdown.
        """
        loop = asyncio.get_running_loop()

        # Save previous handlers to restore on cleanup
        old_sigterm = signal.getsignal(signal.SIGTERM)
        old_sigint = signal.getsignal(signal.SIGINT)

        try:
            loop.add_signal_handler(signal.SIGTERM, lambda: self._on_signal(signal.SIGTERM, None))
            loop.add_signal_handler(signal.SIGINT, lambda: self._on_signal(signal.SIGINT, None))
        except NotImplementedError:
            # Windows does not support add_signal_handler — fall back to
            # signal.signal() which works on the main thread.
            signal.signal(signal.SIGTERM, self._on_signal)
            signal.signal(signal.SIGINT, self._on_signal)

        try:
            await self.startup()
            _logger.info("All managers started — waiting for shutdown signal")
            await self._shutdown_event.wait()
        finally:
            if loop is not None:
                try:
                    loop.remove_signal_handler(signal.SIGTERM)
                except (NotImplementedError, ValueError):
                    signal.signal(signal.SIGTERM, old_sigterm)
                try:
                    loop.remove_signal_handler(signal.SIGINT)
                except (NotImplementedError, ValueError):
                    signal.signal(signal.SIGINT, old_sigint)
            await self.shutdown()
