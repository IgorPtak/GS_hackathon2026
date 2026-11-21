"""In-memory stand-in for `ConfigRegistry`: same `sources()` and `on_reload` surface."""

from collections.abc import Callable
from typing import Any

from alerting_contracts.config import SourceConfig


class FakeRegistry:
    """Holds sources and fires `on_reload` callbacks when `set_sources` swaps them."""

    def __init__(self, sources: dict[str, SourceConfig]) -> None:
        self._sources = dict(sources)
        self.on_reload: list[Callable[[Any], None]] = []

    def sources(self) -> dict[str, SourceConfig]:
        return self._sources

    def set_sources(self, sources: dict[str, SourceConfig]) -> None:
        self._sources = dict(sources)
        for callback in list(self.on_reload):
            callback(None)
