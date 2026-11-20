"""Load and validate every file under a config directory.

Errors name the file and the field path (`rules/x.yaml: when.all.0.op: ...`) so an author can fix
the file without reading a stack trace.
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from .kinds import KindSpec, registered_kinds


@dataclass(frozen=True)
class ConfigFileError:
    """One problem in one file; `path` is the dotted field path ('' for whole-file problems)."""

    file: str
    path: str
    message: str

    def __str__(self) -> str:
        if self.path:
            return f"{self.file}: {self.path}: {self.message}"
        return f"{self.file}: {self.message}"


@dataclass(frozen=True)
class LoadedDocument:
    """A validated file."""

    kind: str
    id: str
    model: BaseModel
    file: Path


@dataclass
class LoadResult:
    """Everything valid plus everything invalid; callers decide whether errors are fatal."""

    documents: list[LoadedDocument] = field(default_factory=list)
    errors: list[ConfigFileError] = field(default_factory=list)


def load_config_file(spec: KindSpec, file: Path) -> LoadedDocument | list[ConfigFileError]:
    """Validate one file; returns the document or the list of errors."""
    name = f"{spec.directory}/{file.name}"
    try:
        model = spec.load_file(file)
    except ValidationError as exc:
        return [
            ConfigFileError(name, ".".join(str(part) for part in err["loc"]), err["msg"])
            for err in exc.errors()
        ]
    except (yaml.YAMLError, OSError, ValueError) as exc:
        return [ConfigFileError(name, "", f"{type(exc).__name__}: {exc}")]
    document_id = str(getattr(model, "id", ""))
    if document_id != file.stem:
        return [
            ConfigFileError(
                name, "id", f"id {document_id!r} does not match file name {file.stem!r}"
            )
        ]
    return LoadedDocument(spec.kind, document_id, model, file)


def load_config_directory(path: Path | str) -> LoadResult:
    """Validate every file in `<path>/<directory>/` for each registered kind."""
    root = Path(path)
    result = LoadResult()
    for spec in registered_kinds():
        directory = root / spec.directory
        if not directory.is_dir():
            continue
        for file in sorted(directory.iterdir()):
            if file.suffix not in spec.suffixes:
                continue
            outcome = load_config_file(spec, file)
            if isinstance(outcome, LoadedDocument):
                result.documents.append(outcome)
            else:
                result.errors.extend(outcome)
    return result
