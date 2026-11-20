"""Typed configuration: load YAML, persist in Postgres, hot-reload through `config.changed`."""

from .kinds import KindSpec, get_kind, register_kind, registered_kinds
from .loader import ConfigFileError, LoadedDocument, LoadResult, load_config_directory
from .registry import ConfigRegistry, ConfigSnapshot
from .store import (
    canonical_document,
    canonical_yaml,
    publish_config_changed,
    save_config_document,
    sync_config_files,
)
from .watcher import handle_config_file_change, watch_config_directory

__all__ = [
    "ConfigFileError",
    "ConfigRegistry",
    "ConfigSnapshot",
    "KindSpec",
    "LoadResult",
    "LoadedDocument",
    "canonical_document",
    "canonical_yaml",
    "get_kind",
    "handle_config_file_change",
    "load_config_directory",
    "publish_config_changed",
    "register_kind",
    "registered_kinds",
    "save_config_document",
    "sync_config_files",
    "watch_config_directory",
]
