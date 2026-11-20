"""Interface for HTTP source plugins."""

from abc import ABC, abstractmethod
from typing import Any

from alerting_contracts.config import SourceConfig


class HttpSourcePlugin(ABC):
    """Turns one parsed HTTP request body into the raw event payloads to ingest.

    Ingest wraps every returned payload in its own `EventEnvelope`. Plugins do no I/O.
    """

    @abstractmethod
    def extract_payloads(self, body: dict[str, Any], source: SourceConfig) -> list[dict[str, Any]]:
        """Return the payload dicts for `body` (webhook: `[body]`)."""
