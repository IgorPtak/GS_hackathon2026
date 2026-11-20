"""Registry of configuration kinds: which directory holds them and how to parse them.

Built-in kinds map one directory to one contract model. Other tracks (runbooks, B-06) add a kind
with `register_kind` without editing this package.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from alerting_contracts.config import (
    ActionConfig,
    ChannelConfig,
    Recipient,
    Rule,
    SchemaProfile,
    SourceConfig,
    Team,
)
from pydantic import BaseModel

FileLoader = Callable[[Path], BaseModel]
DocumentValidator = Callable[[dict[str, Any]], BaseModel]


@dataclass(frozen=True)
class KindSpec:
    """How one configuration kind is stored on disk and validated."""

    kind: str
    directory: str
    load_file: FileLoader
    validate_document: DocumentValidator
    suffixes: frozenset[str] = frozenset({".yaml", ".yml"})


def _model_spec(kind: str, directory: str, model: type[BaseModel]) -> KindSpec:
    def load_file(path: Path) -> BaseModel:
        return model.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    return KindSpec(kind, directory, load_file, model.model_validate)


_KINDS: dict[str, KindSpec] = {
    spec.kind: spec
    for spec in (
        _model_spec("source", "sources", SourceConfig),
        _model_spec("schema_profile", "schemas", SchemaProfile),
        _model_spec("rule", "rules", Rule),
        _model_spec("recipient", "recipients", Recipient),
        _model_spec("team", "teams", Team),
        _model_spec("channel", "channels", ChannelConfig),
        _model_spec("action", "actions", ActionConfig),
    )
}


def register_kind(
    kind: str,
    directory: str,
    loader_fn: FileLoader,
    validate_document: DocumentValidator,
    suffixes: frozenset[str] = frozenset({".yaml", ".yml"}),
) -> None:
    """Add a configuration kind (for example `runbook`).

    `loader_fn(path)` parses one file into a Pydantic model with an `id` attribute.
    `validate_document(dict)` rebuilds that model from the stored jsonb (usually the model's
    `model_validate`); it is required because the registry reloads from the database.
    """
    _KINDS[kind] = KindSpec(kind, directory, loader_fn, validate_document, suffixes)


def get_kind(kind: str) -> KindSpec:
    """Return the spec for `kind` or raise KeyError."""
    return _KINDS[kind]


def registered_kinds() -> list[KindSpec]:
    """All kinds currently registered, built-ins first."""
    return list(_KINDS.values())


def kind_for_directory(directory: str) -> KindSpec | None:
    """Find the kind stored in `config/<directory>/`, if any."""
    return next((s for s in _KINDS.values() if s.directory == directory), None)
