"""Config access for the api; replaced by alerting_core.config.ConfigRegistry (A-03)."""

from pathlib import Path
from typing import Protocol

import yaml
from alerting_contracts.api import ConfigLists
from alerting_contracts.config import ActionConfig, ChannelConfig, Recipient, SourceConfig, Team


class ConfigSource(Protocol):
    """What the api needs from the config layer."""

    def get_config_lists(self) -> ConfigLists:
        """All read-only config lists for the UI dropdowns."""
        ...


class DirectoryConfigSource:
    """Temporary: reads config/{teams,recipients,channels,actions,sources}/*.yaml on each call.

    Replaced by alerting_core.config.ConfigRegistry (A-03).
    """

    def __init__(self, config_dir: str) -> None:
        self._dir = Path(config_dir)

    def _load[T](self, folder: str, model: type[T]) -> list[T]:
        paths = sorted((self._dir / folder).glob("*.yaml"))
        return [model.model_validate(yaml.safe_load(p.read_text())) for p in paths]  # type: ignore[attr-defined]

    def get_config_lists(self) -> ConfigLists:
        """Parse every YAML file into its contract model."""
        return ConfigLists(
            teams=self._load("teams", Team),
            recipients=self._load("recipients", Recipient),
            channels=self._load("channels", ChannelConfig),
            actions=self._load("actions", ActionConfig),
            sources=self._load("sources", SourceConfig),
        )
