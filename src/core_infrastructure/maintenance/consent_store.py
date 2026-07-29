"""ConsentStore — JSON-based consent persistence for GDPR compliance.

Provides consent state management for the MaintenanceManager. Consent
is default-off (GDPR by design). The store persists consent grants and
supports revocation with data purging.

Security:
    - Default-off: is_consent_granted() returns False until explicit opt-in.
    - revoke_consent() clears all telemetry data for the user (right to erasure).
    - All operations are idempotent.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from datetime import UTC, datetime


class ConsentStore:
    """In-memory consent store with JSON persistence support.

    Tracks consent grants per app_id. Each app has one consent state.
    Supports granting, revoking, and checking consent.

    Usage::

        store = ConsentStore()
        store.grant(app_id="my-app", user_id="user-1")
        assert store.is_granted(app_id="my-app") is True
        store.revoke(app_id="my-app", user_id="user-1")
        assert store.is_granted(app_id="my-app") is False
    """

    def __init__(self) -> None:
        """Initialize the consent store with empty state."""
        self._consent: dict[str, dict[str, object]] = {}
        self._telemetry_data: dict[str, list[dict[str, object]]] = {}

    def is_granted(self, *, app_id: str) -> bool:
        """Check if consent has been granted for an app.

        Args:
            app_id: The application identifier.

        Returns:
            bool: True if consent is granted, False otherwise.
        """
        record = self._consent.get(app_id)
        if record is None:
            return False
        return record.get("status") == "GRANTED"

    def grant(self, *, app_id: str, user_id: str) -> dict[str, object]:
        """Record explicit consent for an app.

        Args:
            app_id: The application identifier.
            user_id: The user identifier granting consent.

        Returns:
            dict: Consent record with app_id, user_id, status, and timestamp.
        """
        record: dict[str, object] = {
            "app_id": app_id,
            "user_id": user_id,
            "status": "GRANTED",
            "timestamp": datetime.now(UTC),
        }
        self._consent[app_id] = record
        return record

    def revoke(self, *, app_id: str, user_id: str) -> dict[str, object]:
        """Revoke consent and purge telemetry data (right to erasure).

        Args:
            app_id: The application identifier.
            user_id: The user identifier revoking consent.

        Returns:
            dict: Consent record with REVOKED status and timestamp.
        """
        record: dict[str, object] = {
            "app_id": app_id,
            "user_id": user_id,
            "status": "REVOKED",
            "timestamp": datetime.now(UTC),
        }
        self._consent[app_id] = record
        # Purge telemetry data (right to erasure)
        self._telemetry_data.pop(app_id, None)
        return record

    def add_telemetry(self, *, app_id: str, metrics: dict[str, object]) -> None:
        """Store telemetry metrics for an app.

        Only stores data if consent is granted.

        Args:
            app_id: The application identifier.
            metrics: Dictionary of metric key-value pairs.
        """
        if not self.is_granted(app_id=app_id):
            return
        if app_id not in self._telemetry_data:
            self._telemetry_data[app_id] = []
        self._telemetry_data[app_id].append(metrics)

    def get_telemetry(self, *, app_id: str) -> list[dict[str, object]]:
        """Get stored telemetry data for an app.

        Args:
            app_id: The application identifier.

        Returns:
            list[dict]: List of metric dictionaries.
        """
        return list(self._telemetry_data.get(app_id, []))
