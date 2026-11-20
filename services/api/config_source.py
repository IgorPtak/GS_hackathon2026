"""Config access for the api: ConfigRegistry (A-03), directory reader as DB-less fallback."""

from pathlib import Path
from typing import Protocol

import yaml
from alerting_contracts.api import ConfigLists
from alerting_contracts.config import ActionConfig, ChannelConfig, Recipient, SourceConfig, Team
from alerting_core.config import ConfigRegistry


class ConfigSource(Protocol):
    """What the api needs from the config layer."""

    def get_config_lists(self) -> ConfigLists:
        """All read-only config lists for the UI dropdowns."""
        ...


class RegistryConfigSource:
    """Config lists from the hot-reloaded A-03 ConfigRegistry snapshot.

    Until some service has synced config/ into Postgres (sync_config_files), the registry is
    empty; `fallback` then answers so the UI team picker is never empty.
    """

    def __init__(self, registry: ConfigRegistry, fallback: ConfigSource | None = None) -> None:
        self._registry = registry
        self._fallback = fallback

    def get_config_lists(self) -> ConfigLists:
        """Build the lists from the registry's current typed accessors."""
        registry = self._registry
        if self._fallback is not None and not registry.teams():
            return self._fallback.get_config_lists()
        return ConfigLists(
            teams=list(registry.teams().values()),
            recipients=list(registry.recipients().values()),
            channels=list(registry.channels().values()),
            actions=list(registry.actions().values()),
            sources=list(registry.sources().values()),
        )


class DirectoryConfigSource:
    """Fallback when Postgres is down at startup: reads config/*/*.yaml on each call."""

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
