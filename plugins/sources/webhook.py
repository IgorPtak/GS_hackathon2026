"""Generic webhook source: the request body is the event."""

from typing import Any

from alerting_contracts.config import SourceConfig
from alerting_contracts.events import SourceType

from .base import HttpSourcePlugin
from .registry import register_source_plugin


class WebhookSource(HttpSourcePlugin):
    """One request body -> one event, unchanged."""

    def extract_payloads(self, body: dict[str, Any], source: SourceConfig) -> list[dict[str, Any]]:
        """Return the body as the single payload."""
        return [body]


register_source_plugin(SourceType.webhook, WebhookSource())
