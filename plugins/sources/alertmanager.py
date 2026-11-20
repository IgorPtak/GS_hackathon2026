"""Alertmanager webhook source: one event per item of `alerts[]`."""

from typing import Any

from alerting_contracts.config import SourceConfig
from alerting_contracts.events import SourceType

from .base import HttpSourcePlugin
from .registry import register_source_plugin


class AlertmanagerSource(HttpSourcePlugin):
    """Splits an Alertmanager batch so every alert is routed, deduplicated and delivered alone."""

    def extract_payloads(self, body: dict[str, Any], source: SourceConfig) -> list[dict[str, Any]]:
        """Return the alert objects with `status`, `receiver` and `groupKey` copied in."""
        alerts = body.get("alerts")
        if not isinstance(alerts, list):
            return []
        payloads = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            payload = dict(alert)
            # The item status wins: a batch can mix firing and resolved alerts.
            payload["status"] = alert.get("status", body.get("status"))
            for key in ("receiver", "groupKey"):
                if key in body:
                    payload[key] = body[key]
            payloads.append(payload)
        return payloads

    def idempotency_key(self, payload: dict[str, Any], source: SourceConfig) -> str | None:
        """fingerprint + status + startsAt: drops re-sends, keeps firing -> resolved transitions."""
        fingerprint = payload.get("fingerprint")
        if fingerprint is None:
            return None
        return f"{source.id}:{fingerprint}:{payload.get('status')}:{payload.get('startsAt')}"


register_source_plugin(SourceType.alertmanager, AlertmanagerSource())
