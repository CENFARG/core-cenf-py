"""MaintenanceManager Protocol — the contract every maintenance adapter must satisfy.

Defines the telemetry and error reporting interface consumed by all
CENF products (Arca SaaS, grama, arcaMCP, instaldorAgentico) for
GDPR-compliant automatic capture, PII-scrubbed error transport, and
structured issue creation.

Security:
    - Consent gating: is_consent_granted() MUST return False by default.
    - PII scrubbing: capture_error() MUST mask PII before returning.
    - Telemetry: send_telemetry() MUST anonymize user identifiers.
Observability:
    - Error events emit RED metrics via ObservabilityManager.
    - report_error() SHOULD fire-and-forget to avoid blocking main flow.
@ai-directive: Use MaintenanceManager to capture, scrub, and report errors
    with GDPR compliance. Always check is_consent_granted() before sending
    any telemetry data. Never send data without explicit user opt-in.
    capture_error() MUST strip PII (email, tokens, passwords) before
    returning the ErrorReport. revoke_consent() MUST purge all user data.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MaintenanceManager(Protocol):
    """GDPR-compliant error capture, telemetry, and reporting contract.

    All CENF products that need auto error reporting consume this interface.
    Concrete adapters provide consent management, PII-scrubbed capture,
    OTLP telemetry transport, and structured issue creation.

    Rules:
        - is_consent_granted() MUST return False until user explicitly opts in.
        - request_consent() records explicit opt-in with timestamp.
        - revoke_consent() MUST purge all telemetry data for the user.
        - capture_error() MUST scrub PII before returning ErrorReport.
        - report_error() SHOULD fire-and-forget — never block main flow.
        - send_telemetry() MUST anonymize user identifiers.

    Security:
        - Consent is default-off. Never send data without consent.
        - PII is scrubbed at capture time, never after storage.
    """

    async def is_consent_granted(self, *, app_id: str) -> bool:
        """Check whether the user has granted telemetry consent.

        Args:
            app_id: The application identifier.

        Returns:
            bool: True if consent has been granted for this app,
                False otherwise (default).
        """
        ...

    async def request_consent(
        self,
        *,
        app_id: str,
        user_id: str,
    ) -> Any:
        """Record explicit user consent for telemetry.

        Stores the consent grant with timestamp. After this call,
        is_consent_granted() MUST return True for this app_id.

        Args:
            app_id: The application identifier.
            user_id: The user identifier granting consent.

        Returns:
            ConsentResult: With status GRANTED and current timestamp.

        Raises:
            PermanentError: If consent state cannot be persisted.
        """
        ...

    async def revoke_consent(self, *, app_id: str, user_id: str) -> None:
        """Revoke consent and purge all telemetry data (right to erasure).

        After this call:
            - is_consent_granted() MUST return False for this app_id.
            - All stored telemetry data for this user MUST be deleted.

        Args:
            app_id: The application identifier.
            user_id: The user identifier revoking consent.
        """
        ...

    async def capture_error(
        self,
        *,
        app_id: str,
        error: Exception,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Capture an error with PII scrubbing and produce an ErrorReport.

        The implementation MUST:
            1. Extract stack trace from the exception.
            2. Scrub PII (email, token, password, credit card patterns).
            3. Return an ErrorReport with app_id, version, OS, and masked data.

        Args:
            app_id: The application identifier.
            error: The exception to capture.
            context: Optional dictionary of additional context.

        Returns:
            ErrorReport: PII-scrubbed error report ready for transport.
        """
        ...

    async def report_error(self, *, report: Any) -> Any:
        """Send an ErrorReport to the configured transport.

        SHOULD fire-and-forget. If the primary transport fails (e.g., GitHub
        API unreachable), the adapter SHOULD fall back to secondary transport
        (e.g., Discord webhook). MUST NOT crash the main application.

        Args:
            report: An ErrorReport to transmit.

        Returns:
            ReportResult: With success status and target identifier.
        """
        ...

    async def send_telemetry(
        self,
        *,
        app_id: str,
        metrics: dict[str, Any],
    ) -> None:
        """Send telemetry metrics via OTLP transport.

        User identifiers MUST be anonymized (UUID instead of email).
        Metrics include: app_id, version, OS, uptime, error_count.

        Args:
            app_id: The application identifier.
            metrics: Dictionary of metric key-value pairs.
        """
        ...

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Describe this manager contract for agent discovery.

        Returns a JSON Schema that tools/agents can use to understand
        how to call the MaintenanceManager.

        Returns:
            dict[str, Any]: JSON Schema describing the MaintenanceManager
                interface (methods, parameters, return types).
        """
        ...
