"""Regenerate every contract artifact derived from the Pydantic models in ``contracts/alerting_contracts``.

Writes:
  * ``contracts/schemas/*.schema.json``      one JSON Schema per top-level model
  * ``contracts/openapi.yaml``               ONLY the ``components.schemas`` block (spliced textually,
                                             so ``paths`` and the rest stay byte-identical)
  * ``web/src/api/schema.gen.ts``            via ``npx -y openapi-typescript@7``

Also validates that every ``$ref`` in openapi.yaml resolves and that every YAML file in
``contracts/examples/<kind>/`` validates against its model's JSON Schema.

Invocation (no pyproject yet; run from the repo root)::

    PYTHONPATH=contracts uv run --no-project --with pydantic --with pyyaml --with jsonschema \\
        python scripts/generate_contracts.py [--check]

``--check`` writes nothing into the repo and exits 1, listing differing files, when output on disk is stale.
"""

from __future__ import annotations

import argparse
import enum
import inspect
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import alerting_contracts.alerts as m_alerts
import alerting_contracts.api as m_api
import alerting_contracts.config as m_config
import alerting_contracts.events as m_events
import alerting_contracts.proposals as m_proposals
import alerting_contracts.runbooks as m_runbooks
import alerting_contracts.sse as m_sse
import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
SCHEMAS_DIR = CONTRACTS / "schemas"
OPENAPI = CONTRACTS / "openapi.yaml"
EXAMPLES = CONTRACTS / "examples"
TS_OUT = ROOT / "web" / "src" / "api" / "schema.gen.ts"
REF_PREFIX = "#/components/schemas/"

log = logging.getLogger("generate_contracts")

MODULES = [m_alerts, m_api, m_config, m_events, m_proposals, m_runbooks, m_sse]

# Standalone JSON Schema files: file stem -> model name. Config models are prefixed `config.`.
CONFIG_SCHEMA_MODELS = [
    "ActionConfig", "ChannelConfig", "Recipient", "Rule", "RunbookYamlDocument",
    "SchemaProfile", "SourceConfig", "Team",
]  # fmt: skip
PLAIN_SCHEMA_MODELS = [
    "ActionRun", "Alert", "AlertStatus", "ApprovalRequest", "AuditEntry", "Delivery", "DeliveryJob",
    "EventEnvelope", "FixProposal", "NormalizedFields", "OutboxEntry", "RenderedRunbook", "Runbook",
    "RunbookJob", "RunbookRevisionProposal", "RunbookStep", "SchemaProfileProposal", "SseEvent",
]  # fmt: skip

# examples/<dir> -> model name
EXAMPLE_KINDS = {
    "actions": "ActionConfig",
    "channels": "ChannelConfig",
    "recipients": "Recipient",
    "rules": "Rule",
    "runbooks": "RunbookYamlDocument",
    "schemas": "SchemaProfile",
    "sources": "SourceConfig",
    "teams": "Team",
}


def _log(event: str, **kw: Any) -> None:
    print(json.dumps({"event": event, **kw}), file=sys.stderr)


def _public_types() -> dict[str, Any]:
    """Every public model/enum defined in the contract modules, plus the SseEvent union."""
    found: dict[str, Any] = {}
    for mod in MODULES:
        for name, obj in vars(mod).items():
            if (
                name.startswith("_")
                or not inspect.isclass(obj)
                or obj.__module__ != mod.__name__
            ):
                continue
            if issubclass(obj, BaseModel) or issubclass(obj, enum.Enum):
                found[name] = obj
    found["SseEvent"] = m_sse.SseEvent
    return found


def _adapter(tp: Any) -> TypeAdapter[Any]:
    return TypeAdapter(tp)


def _standalone_schema(tp: Any) -> dict[str, Any]:
    """JSON Schema for one type with its own ``$defs``."""
    schema = _adapter(tp).json_schema()
    return _sorted_top(schema)


def _sorted_top(schema: dict[str, Any]) -> dict[str, Any]:
    """Top-level keys sorted; ``properties`` keep declaration order (it is meaningful)."""
    return {k: schema[k] for k in sorted(schema)}


def build_components(types: dict[str, Any]) -> dict[str, Any]:
    """``components.schemas`` mapping, sorted by name, refs rewritten to ``#/components/schemas/``."""
    out: dict[str, Any] = {}
    for name, tp in types.items():
        schema = _adapter(tp).json_schema(ref_template=REF_PREFIX + "{model}")
        defs = schema.pop("$defs", {})
        for dname, dschema in defs.items():
            out.setdefault(dname, dschema)
        if name == "SseEvent":
            out[name] = schema
        else:
            out.setdefault(name, schema)
    return {k: _sorted_top(out[k]) for k in sorted(out)}


def build_schema_files(types: dict[str, Any]) -> dict[Path, str]:
    """Relative-to-root path -> file content for every contracts/schemas file."""
    files: dict[Path, str] = {}
    stems = [(f"config.{n}", n) for n in CONFIG_SCHEMA_MODELS] + [
        (n, n) for n in PLAIN_SCHEMA_MODELS
    ]
    for stem, name in stems:
        files[SCHEMAS_DIR / f"{stem}.schema.json"] = (
            json.dumps(_standalone_schema(types[name]), indent=2) + "\n"
        )
    return files


def _dump_components_block(components: dict[str, Any]) -> str:
    body = yaml.safe_dump(
        {"schemas": components}, sort_keys=False, width=118, allow_unicode=True
    )
    return "".join(
        ("  " + line if line.strip() else line)
        for line in body.splitlines(keepends=True)
    )


def splice_openapi(text: str, components: dict[str, Any]) -> str:
    """Replace only the ``  schemas:`` block inside top-level ``components:``."""
    start = re.search(r"^components:\n", text, re.MULTILINE)
    if not start:
        raise SystemExit("openapi.yaml has no top-level components:")
    m = re.compile(r"^  schemas:\n", re.MULTILINE).search(text, start.end())
    if not m:
        raise SystemExit("openapi.yaml has no components.schemas")
    nxt = re.compile(r"^(?:  \S|\S)", re.MULTILINE).search(text, m.end())
    end = nxt.start() if nxt else len(text)
    return text[: m.start()] + _dump_components_block(components) + text[end:]


def check_refs(openapi_text: str) -> list[str]:
    """Return unresolved ``$ref`` strings (local refs only)."""
    doc = yaml.safe_load(openapi_text)
    bad: list[str] = []

    def resolve(ref: str) -> bool:
        if not ref.startswith("#/"):
            return False
        node: Any = doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or part not in node:
                return False
            node = node[part]
        return True

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "$ref" and isinstance(v, str) and not resolve(v):
                    bad.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    return bad


def validate_examples(types: dict[str, Any]) -> list[str]:
    """Validate every YAML example against its model's JSON Schema; return error strings."""
    try:
        import jsonschema
    except (
        ImportError
    ):  # fall back to the models themselves (they generated the schema)
        jsonschema = None
        _log("jsonschema_missing", fallback="pydantic TypeAdapter validation")

    errors: list[str] = []
    for kind, model in EXAMPLE_KINDS.items():
        schema = _standalone_schema(types[model])
        for path in sorted((EXAMPLES / kind).glob("*")):
            if path.suffix not in (".yaml", ".yml"):
                continue
            data = yaml.safe_load(path.read_text())
            if jsonschema is None:
                try:
                    _adapter(types[model]).validate_python(data)
                except ValidationError as exc:
                    errors.append(f"{path.relative_to(ROOT)}: {exc}")
                continue
            for err in jsonschema.Draft202012Validator(schema).iter_errors(data):
                errors.append(
                    f"{path.relative_to(ROOT)}: {'/'.join(map(str, err.path))}: {err.message}"
                )
    return errors


def run_typescript(openapi: Path, out: Path) -> None:
    """Run openapi-typescript v7 on ``openapi`` writing ``out``."""
    out.parent.mkdir(parents=True, exist_ok=True)
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("npx not found on PATH")
    subprocess.run(
        [npx, "-y", "openapi-typescript@7", str(openapi), "-o", str(out)],
        check=True,
        cwd=ROOT,
    )


def main() -> int:
    """Entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if generated files differ; write nothing",
    )
    args = ap.parse_args()

    types = _public_types()
    components = build_components(types)
    original = OPENAPI.read_text()
    new_openapi = splice_openapi(original, components)

    bad = check_refs(new_openapi)
    if bad:
        _log("unresolved_refs", refs=sorted(set(bad)))
        return 1
    errs = validate_examples(types)
    if errs:
        _log("example_validation_failed", errors=errs)
        return 1

    files: dict[Path, str] = build_schema_files(types)
    files[OPENAPI] = new_openapi

    with tempfile.TemporaryDirectory() as tmp:
        tmp_openapi = Path(tmp) / "openapi.yaml"
        tmp_openapi.write_text(new_openapi)
        tmp_ts = Path(tmp) / "schema.gen.ts"
        run_typescript(tmp_openapi, tmp_ts)
        files[TS_OUT] = tmp_ts.read_text()

    if args.check:
        differing = [
            p for p, c in files.items() if not p.exists() or p.read_text() != c
        ]
        expected = {p.name for p in files if p.parent == SCHEMAS_DIR}
        differing += [
            p for p in SCHEMAS_DIR.glob("*.schema.json") if p.name not in expected
        ]
        if differing:
            _log("drift", files=[str(p.relative_to(ROOT)) for p in differing])
            return 1
        _log("ok", files=len(files))
        return 0

    for p in SCHEMAS_DIR.glob("*.schema.json"):
        if p not in files:
            p.unlink()
    for p, c in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists() or p.read_text() != c:
            p.write_text(c)
            _log("wrote", file=str(p.relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
