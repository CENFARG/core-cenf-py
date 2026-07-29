"""M24 MaintenanceManager — Auto Error Reporting + Telemetry + GitHub Issues.

Proporciona un pipeline unificado de reporte de errores con:

- Consentimiento GDPR (opt-in, default-off, symmetric UX)
- PII scrubbing (regex-based masking antes de exportar)
- OTLP Telemetry (OpenTelemetry)
- 4 adapters: InMemory, GitHubIssues, Discord, CENFServer, GlitchTip
- Tail-based sampling (solo severity > WARNING reportados)

Uso típico:

    from core_infrastructure.maintenance.ports import MaintenanceManager
    from core_infrastructure.maintenance.adapters.in_memory_maintenance_adapter import (
        InMemoryMaintenanceAdapter,
    )

    mgr: MaintenanceManager = InMemoryMaintenanceAdapter()
    await mgr.request_consent(app_id="my-app", user_id="user-1")
    report = await mgr.capture_error(app_id="my-app", error=ValueError("fail"), context={})
    result = await mgr.report_error(report=report)

@ai-directive: Use MaintenanceManager for GDPR-compliant error reporting with
    PII scrubbing. Always check is_consent_granted() before sending telemetry.
    Consent is default-off — never send data without explicit user opt-in.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from core_infrastructure.maintenance.models import (
    ConsentResult,
    ErrorReport,
    MaintenanceConfig,
    ReportResult,
)
from core_infrastructure.maintenance.ports import MaintenanceManager

__all__ = [
    "ConsentResult",
    "ErrorReport",
    "MaintenanceConfig",
    "MaintenanceManager",
    "ReportResult",
]
