"""Heuristic schema-profile proposal for a sample event (B-19); pure and deterministic.

`propose_profile_heuristic` is the seam: B-21 adds an LLM variant that falls back to this function.
"""

import re
from typing import Any

from alerting_contracts.config import SchemaProfile
from alerting_contracts.proposals import SchemaProfileProposal
from alerting_core.events.compiled import compile_profile

# Key-name aliases (lowercase, `_`/`-` removed), most preferred first.
_ALIASES: dict[str, tuple[str, ...]] = {
    "severity": ("severity", "level", "lvl", "sev", "priority"),
    "occurred_at": ("occurredat", "createdat", "timestamp", "time", "ts", "at", "eventtime"),
    "id": ("eventid", "id"),
    "type": ("eventtype", "type", "kind", "evt", "event"),
    "source": ("source", "service", "system", "svc"),
    "title": ("title", "summary", "message", "description"),
}
_SEVERITY_VALUES = {
    "critical": "critical", "crit": "critical", "fatal": "critical",
    "error": "error", "err": "error", "high": "error",
    "warn": "warning", "warning": "warning", "medium": "warning",
    "info": "info", "low": "info", "ok": "info",
}  # fmt: skip
_KNOWN = {alias for names in _ALIASES.values() for alias in names}


def _leaves(value: Any, prefix: str, out: dict[str, Any]) -> None:
    """Flatten nested objects to `a.b.c -> value`; lists are not entered."""
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, dict) and child:
                _leaves(child, path, out)
            else:
                out[path] = child


def _norm(path: str) -> str:
    return re.sub(r"[_\-]", "", path.rsplit(".", 1)[-1]).lower()


def _slug(text: str) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", text)
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "profile"


def _pick(leaves: dict[str, Any], names: tuple[str, ...], *, scalar: bool = True) -> str | None:
    """Best path whose key matches `names`: alias order, then shallowest, then alphabetical."""
    best: tuple[int, int, str] | None = None
    for path, value in leaves.items():
        key = _norm(path)
        if key not in names or (scalar and isinstance(value, dict | list)):
            continue
        rank = (names.index(key), path.count("."), path)
        best = rank if best is None or rank < best else best
    return best[2] if best else None


def propose_profile_heuristic(
    sample_event: dict[str, Any], profile_id: str | None = None
) -> SchemaProfileProposal:
    """Draft a SchemaProfile for `sample_event` from key names and values only."""
    leaves: dict[str, Any] = {}
    _leaves(sample_event, "", leaves)
    paths = sorted(p for p in leaves if "[" not in p)
    notes: list[str] = []
    fields: dict[str, Any] = {}

    if (path := _pick(leaves, _ALIASES["type"])) is not None:
        fields["type"] = path
        notes.append(f"type <- {path}: key name looks like an event type.")
    if (path := _pick(leaves, _ALIASES["source"])) is not None:
        fields["source"] = path
        notes.append(f"source <- {path}: key name looks like the emitting service.")
    if (path := _pick(leaves, _ALIASES["severity"])) is not None:
        spec: dict[str, Any] = {"path": path}
        if isinstance(leaves[path], str):
            spec["value_map"] = dict(_SEVERITY_VALUES)
            notes.append(
                f"severity <- {path}: sample value {leaves[path]!r}; value_map covers "
                "critical/crit/fatal, error/err/high, warn/warning/medium, info/low/ok."
            )
        else:
            notes.append(f"severity <- {path}: sample value is not a string, no value_map added.")
        fields["severity"] = spec
    if (path := _pick(leaves, _ALIASES["occurred_at"])) is not None:
        spec = {"path": path}
        value = leaves[path]
        if isinstance(value, int | float) and not isinstance(value, bool):
            spec["format"] = "epoch_ms" if abs(value) >= 1e11 else "epoch_s"
        elif isinstance(value, str):
            spec["format"] = "iso8601"
        fields["occurred_at"] = spec
        notes.append(f"occurred_at <- {path}: timestamp-like key (format {spec.get('format')}).")
    entity = sorted(
        (p for p in paths if _norm(p).endswith("id") and _norm(p) not in _KNOWN),
        key=lambda p: (p.count("."), p),
    )
    if entity:
        fields["entity"] = entity[0]
        notes.append(f"entity <- {entity[0]}: identifier of the affected object.")
    if (path := _pick(leaves, _ALIASES["title"])) is not None:
        notes.append(
            f"{path} looks like a title/message; profiles have no title field, so unmapped."
        )

    # Match: presence of the 2-3 most distinctive (longest, non-generic) key paths.
    distinctive = sorted(
        (p for p in paths if _norm(p) not in _KNOWN), key=lambda p: (-len(p), p)
    ) or sorted(paths, key=lambda p: (-len(p), p))
    chosen = distinctive[:3]
    if len(chosen) < 2:
        chosen += [p for p in sorted(paths, key=lambda p: (-len(p), p)) if p not in chosen][
            : 2 - len(chosen)
        ]
    if not chosen:
        chosen = ["event"]
    leafs = [{"field": p, "op": "exists", "value": True} for p in chosen]
    match: dict[str, Any] = {"all": leafs} if len(leafs) > 1 else leafs[0]
    notes.append(f"match: all of {', '.join(chosen)} must exist (most distinctive keys).")

    id_path = _pick(leaves, _ALIASES["id"])
    if id_path:
        fingerprint = [id_path]
        notes.append(f"fingerprint: {id_path} (id-like key).")
    else:
        fingerprint = [p for p in (fields.get("type"), fields.get("source")) if isinstance(p, str)]
        if fingerprint:
            notes.append(f"fingerprint: {', '.join(fingerprint)} (type and source keys).")
        else:
            fingerprint = chosen[:2]
            notes.append(f"fingerprint: {', '.join(fingerprint)} (no id/type/source key found).")

    final_id = profile_id or _slug(chosen[0])
    notes.append(f"id: {final_id}" + ("" if profile_id else " (slug of the most distinctive key)."))
    profile = SchemaProfile.model_validate(
        {
            "id": final_id,
            "description": "Proposed by heuristic from a sample event; review before saving.",
            "priority": 10,
            "match": match,
            "fields": fields,
            "fingerprint": fingerprint,
        }
    )
    compile_profile(profile)  # fail here rather than at save/test time
    return SchemaProfileProposal(profile=profile, generated_by="heuristic", model=None, notes=notes)
