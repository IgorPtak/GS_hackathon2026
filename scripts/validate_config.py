"""Validate config/ YAML and runbook files against the contract models (task S-03).

Usage: PYTHONPATH=contracts python scripts/validate_config.py config/
Exits 1 when a file fails to load, its id does not match its file name, or a reference dangles.
"""

import sys
from pathlib import Path

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
from alerting_contracts.runbooks import RunbookYamlDocument
from pydantic import ValidationError

MODELS = {
    "actions": ActionConfig,
    "channels": ChannelConfig,
    "recipients": Recipient,
    "rules": Rule,
    "schemas": SchemaProfile,
    "sources": SourceConfig,
    "teams": Team,
}
RUNBOOK_SUFFIXES = {".yaml", ".md", ".txt"}


def load(path: Path, subdir: str) -> object | None:
    """Return the parsed model, or None for a non-YAML runbook (only checked non-empty)."""
    text = path.read_text(encoding="utf-8")
    if subdir == "runbooks":
        if path.suffix not in RUNBOOK_SUFFIXES:
            raise ValueError(f"unsupported runbook suffix {path.suffix!r}")
        if path.suffix != ".yaml":
            if not text.strip():
                raise ValueError("runbook is empty")
            return None
        return RunbookYamlDocument.model_validate(yaml.safe_load(text))
    return MODELS[subdir].model_validate(yaml.safe_load(text))


def references(doc: object) -> list[tuple[str, str, str]]:
    """(label, referenced id, subdirectory it must exist in)."""
    if isinstance(doc, Rule):
        refs = [
            ("team", doc.team, "teams"),
            *[("route channel", c, "channels") for c in doc.route.channels],
        ]
        return refs + ([("runbook", doc.runbook, "runbooks")] if doc.runbook else [])
    if isinstance(doc, Team):
        return [("on_call", r, "recipients") for r in doc.on_call]
    if isinstance(doc, Recipient):
        prefs = [
            ("channel preference", c, "channels")
            for p in doc.channel_preferences
            for c in p.channels
        ]
        return [("team", t, "teams") for t in doc.teams] + prefs
    if isinstance(doc, ChannelConfig) and doc.fallback_channel_id:
        return [("fallback channel", doc.fallback_channel_id, "channels")]
    if isinstance(doc, RunbookYamlDocument):
        steps = [("step action", s.action, "actions") for s in doc.steps if s.action]
        return steps + ([("team", doc.team, "teams")] if doc.team else [])
    return []


def main(root: Path) -> int:
    failures: list[str] = []
    ids: dict[str, set[str]] = {}
    parsed: list[tuple[Path, object]] = []
    for subdir in [*MODELS, "runbooks"]:
        ids[subdir] = set()
        if not (root / subdir).is_dir():
            failures.append(f"{root / subdir}: directory missing")
            continue
        for path in sorted((root / subdir).iterdir()):
            if path.name == ".gitkeep" or path.is_dir():
                continue
            try:
                doc = load(path, subdir)
                doc_id = path.stem if doc is None else doc.id
                if doc_id != path.stem:
                    raise ValueError(f"id {doc_id!r} does not match file name")
                ids[subdir].add(doc_id)
                if doc is not None:
                    parsed.append((path, doc))
            except ValidationError as exc:
                details = "; ".join(
                    f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()
                )
                failures.append(f"{path}: {details}")
            except (ValueError, yaml.YAMLError, OSError) as exc:
                failures.append(f"{path}: {exc}")
    for path, doc in parsed:
        for label, ref_id, target in references(doc):
            if ref_id not in ids[target]:
                failures.append(f"{path}: {label} {ref_id!r} not found in {target}/")
    for failure in failures:
        print(f"FAIL {failure}")
    status = "FAILED" if failures else "OK"
    document_count = sum(map(len, ids.values()))
    print(f"{status}: {document_count} documents, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config")))
