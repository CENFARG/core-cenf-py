"""CENF AlertManager — multi-channel alert dispatch with rule-based triggers.

Provides a Protocol-based interface for dispatching alerts to Slack,
Discord, and Email based on configurable dict-based rules. DispatchAlertAdapter
implements the full contract with throttle windows and fire-and-forget semantics.

Security: Alert failures never block the main flow. Channel credentials
    are managed via SecretManager.
Observability: All dispatch events emit RED metrics under cenf.alert.*.
@ai-directive: Dict-based conditions for MVP. CEL evaluation planned for
    future release. Email channel is a placeholder.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.alert.adapters.dispatch_alert_adapter import DispatchAlertAdapter
from core_infrastructure.alert.models import AlertChannel, AlertConfig
from core_infrastructure.alert.ports import AlertLevel, AlertManager, AlertRule

__all__ = [
    "AlertChannel",
    "AlertConfig",
    "AlertLevel",
    "AlertManager",
    "AlertRule",
    "DispatchAlertAdapter",
]
