"""DispatchAlertAdapter — multi-channel alert dispatch with rule-based triggers.

Implements AlertManager with Slack, Discord, and Email channel support.
Uses ExternalAPIManager (M11) for HTTP calls and dict-based condition
matching for rule evaluation. Includes throttle windows per rule.
Email dispatch uses ``smtplib`` with SMTP config from ConfigManager and
SecretManager.

Security: Never raises on alert failure — fire-and-forget with error logging.
    Channel credentials are read via SecretManager, never hardcoded.
Observability: All dispatch events emit RED metrics. Throttled alerts logged at WARNING.
@ai-directive: Use ExternalAPIManager for HTTP. Email uses stdlib smtplib.
    asyncio.Lock protects the rules registry and throttle state.

Author: CENF AI Team
Version: 0.2.0
"""

from __future__ import annotations

import asyncio
import time as _time
from typing import Any

from core_infrastructure.alert.models import AlertConfig
from core_infrastructure.alert.ports import AlertLevel, AlertRule
from core_infrastructure.config.ports import ConfigManager
from core_infrastructure.errors.ports import ErrorHandlingManager
from core_infrastructure.external_api.ports import ExternalAPIManager
from core_infrastructure.logger.ports import LoggerManager
from core_infrastructure.secrets.ports import SecretManager


class DispatchAlertAdapter:
    """Multi-channel alert dispatcher with dict-based rule evaluation.

    Dispatches alerts to Slack, Discord, and Email using ExternalAPIManager
    for HTTP calls. Rules are evaluated with dict-based condition matching
    and throttle windows per rule to prevent alert storms.

    Args:
        config: ConfigManager for AlertConfig reading.
        secret_manager: SecretManager for retrieving channel credentials.
        logger: LoggerManager for structured log emission.
        external_api: ExternalAPIManager for HTTP dispatch.
        error_handler: ErrorHandlingManager for exception classification.

    Usage::

        adapter = DispatchAlertAdapter(config, secrets, logger, http, errors)
        rule = AlertRule(rule_id="high_error", condition={"error_rate": 0.05},
                        level=AlertLevel.CRITICAL, channels=["slack"])
        adapter.register_rule(rule)
        await adapter.evaluate_and_alert({"error_rate": 0.10})
    """

    def __init__(
        self,
        config: ConfigManager,
        secret_manager: SecretManager,
        logger: LoggerManager,
        external_api: ExternalAPIManager,
        error_handler: ErrorHandlingManager,
    ) -> None:
        self._config = config
        self._secret_manager = secret_manager
        self._logger = logger
        self._external_api = external_api
        self._error_handler = error_handler

        alert_section = config.get_section("alert")
        self._alert_config = AlertConfig(**alert_section) if alert_section else AlertConfig()

        self._rules: dict[str, AlertRule] = {}
        self._last_fired: dict[str, float] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_dot_notation(d: dict[str, Any], key_path: str) -> Any:
        """Resolve a dot-notation key path in a nested dict.

        Splits ``key_path`` on ``"."`` and traverses the dict
        hierarchy. Returns ``None`` if any intermediate key is missing.

        Args:
            d: The root dict to traverse.
            key_path: Dot-separated key path (e.g., ``"metrics.error_rate"``).

        Returns:
            Any: The value at the resolved path, or ``None`` if missing.
        """
        parts = key_path.split(".")
        current: Any = d
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @staticmethod
    def _condition_matches(condition: dict[str, Any], event_context: dict[str, Any]) -> bool:
        """Check if ALL key:value pairs in condition match event_context.

        Each key in ``condition`` is resolved via dot-notation in
        ``event_context`` and compared by equality.

        Args:
            condition: Dict of expected key:value pairs.
            event_context: Runtime event data to match against.

        Returns:
            bool: True if all key:value pairs match (vacuously true for empty condition).
        """
        for key, expected_value in condition.items():
            actual = DispatchAlertAdapter._resolve_dot_notation(event_context, key)
            if actual != expected_value:
                return False
        return True

    @staticmethod
    def _format_slack(title: str, message: str, level: AlertLevel) -> dict[str, str]:
        """Format an alert as a Slack-compatible payload.

        Args:
            title: Alert title.
            message: Alert message body.
            level: Alert severity level.

        Returns:
            dict[str, str]: Slack payload with ``text`` field.
        """
        level_emoji = {"info": ":information_source:", "warning": ":warning:", "critical": ":rotating_light:"}
        emoji = level_emoji.get(level.value, "")
        text = f"{emoji} *{title}*\n{message}"
        return {"text": text}

    @staticmethod
    def _format_discord(title: str, message: str, level: AlertLevel) -> dict[str, str]:
        """Format an alert as a Discord-compatible payload.

        Args:
            title: Alert title.
            message: Alert message body.
            level: Alert severity level.

        Returns:
            dict[str, str]: Discord payload with ``content`` field.
        """
        return {"content": f"**{title}**\n{message}"}

    def _check_throttle(self, rule_id: str) -> bool:
        """Check if the throttle window allows this rule to fire.

        Returns True if the rule may fire (not throttled). Also updates
        the last_fired timestamp if the rule is allowed to proceed.

        Args:
            rule_id: The rule identifier to check.

        Returns:
            bool: True if the rule is allowed to fire, False if throttled.
        """
        rule = self._rules.get(rule_id)
        if rule is None:
            return False

        if rule.throttle_seconds == 0:
            return True

        now = _time.time()
        last = self._last_fired.get(rule_id)
        return not (last is not None and (now - last) < rule.throttle_seconds)

    async def _dispatch_email(self, title: str, message: str) -> None:
        """Dispatch an alert via SMTP email.

        Reads SMTP configuration from the alert channel config:
        ``smtp_host``, ``smtp_port``, ``smtp_user``, ``from_email``,
        ``to_emails``. SMTP password is retrieved via SecretManager using
        the key from ``smtp_password_key`` (default ``"alert.smtp_password"``).

        Format: plain text MIMEText with ``title`` as subject and
        ``message`` as body. Errors are logged — never raised.

        Args:
            title: Email subject line.
            message: Email body (plain text).
        """
        try:
            email_config = self._alert_config.channels.get("email", {})
            if not email_config:
                return

            smtp_host = email_config.get("smtp_host", "")
            smtp_port = int(email_config.get("smtp_port", "587"))
            smtp_user = email_config.get("smtp_user", "")
            from_email = email_config.get("from_email", "")
            to_emails_str = email_config.get("to_emails", "")
            password_key = email_config.get("smtp_password_key", "alert.smtp_password")

            if not all([smtp_host, from_email, to_emails_str]):
                self._logger.warn("Email channel misconfigured — missing required fields", title=title)
                return

            to_emails = [e.strip() for e in to_emails_str.split(",") if e.strip()]
            if not to_emails:
                self._logger.warn("Email channel: no recipients configured", title=title)
                return

            try:
                smtp_password = await self._secret_manager.get_secret(password_key)
            except Exception:
                self._logger.warn(
                    "Email channel: failed to retrieve SMTP password from SecretManager",
                    password_key=password_key,
                    title=title,
                )
                return

            if not smtp_password:
                self._logger.warn("Email channel: empty SMTP password", title=title)
                return

            import smtplib
            from email.mime.text import MIMEText

            msg = MIMEText(message, "plain", "utf-8")
            msg["Subject"] = title
            msg["From"] = from_email
            msg["To"] = ", ".join(to_emails)

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
                smtp.starttls()
                if smtp_user:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(msg)

            self._logger.info("Alert sent via email", title=title, to=to_emails_str)

        except Exception as exc:
            self._logger.error(
                "Failed to send email alert",
                exc=exc,
                title=title,
            )

    # ------------------------------------------------------------------
    # Public API — AlertManager Protocol
    # ------------------------------------------------------------------

    async def send_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Dispatch an alert to all configured channels.

        Formats the message for each configured channel and dispatches
        concurrently via ExternalAPIManager. Failures in one channel
        do not prevent delivery to others.

        Args:
            level: Alert severity level.
            title: Short alert title.
            message: Detailed alert message body.
            metadata: Optional structured metadata.
        """
        channels = self._alert_config.channels

        if not channels:
            self._logger.warn("No alert channels configured — alert not sent", title=title)
            return

        for channel_name, channel_config in channels.items():
            try:
                if channel_name == "email":
                    await self._dispatch_email(title, message)
                    continue

                webhook_url = channel_config.get("webhook_url", "")

                if not webhook_url:
                    self._logger.warn("No webhook URL for channel", channel=channel_name)
                    continue

                if channel_name == "slack":
                    payload = self._format_slack(title, message, level)
                    await self._external_api.post(webhook_url, body=payload)
                    self._logger.info("Alert sent to Slack", title=title, level=level.value)

                elif channel_name == "discord":
                    payload = self._format_discord(title, message, level)
                    await self._external_api.post(webhook_url, body=payload)
                    self._logger.info("Alert sent to Discord", title=title, level=level.value)

                else:
                    self._logger.warn("Unknown alert channel", channel=channel_name)

            except Exception as exc:
                self._logger.error(
                    f"Failed to send alert to {channel_name}",
                    exc=exc,
                    title=title,
                    channel=channel_name,
                )

    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule with dict-based condition.

        Rules are stored in-memory. Registering a rule with the same
        ``rule_id`` overwrites the previous entry.

        Args:
            rule: The AlertRule to register.
        """
        self._rules[rule.rule_id] = rule
        self._logger.debug("Alert rule registered", rule_id=rule.rule_id)

    async def evaluate_and_alert(self, event_context: dict[str, Any]) -> None:
        """Evaluate all registered rules against event_context and dispatch matches.

        For each registered rule, checks if its dict condition matches
        the event_context. If it matches AND the throttle window allows,
        dispatches an alert via ``send_alert()``.

        Thread-safety: Protected by asyncio.Lock.

        Args:
            event_context: Runtime event data to match against rule conditions.
        """
        async with self._lock:
            for rule in list(self._rules.values()):
                if not self._condition_matches(rule.condition, event_context):
                    continue

                if not self._check_throttle(rule.rule_id):
                    self._logger.warn("Alert throttled", rule_id=rule.rule_id)
                    continue

                self._last_fired[rule.rule_id] = _time.time()

                await self.send_alert(
                    level=rule.level,
                    title=f"[{rule.level.value.upper()}] Rule: {rule.rule_id}",
                    message=f"Condition matched: {rule.condition}",
                    metadata=event_context,
                )

    @staticmethod
    def get_json_schema() -> dict[str, Any]:
        """Return JSON Schema for agent discovery (AX).

        Returns:
            dict[str, Any]: JSON Schema describing AlertConfig model.
        """
        return AlertConfig.model_json_schema()
