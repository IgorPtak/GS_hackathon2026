"""Extract NormalizedFields from a raw event with a schema profile."""

from datetime import UTC, datetime
from typing import Any

from alerting_contracts.common import Severity
from alerting_contracts.config import FieldMappingSpec, SchemaProfile
from alerting_contracts.events import EventEnvelope, NormalizedFields

from ._matcher import _matches
from ._paths import MISSING, get_path
from .fingerprint import compute_fingerprint

_SEVERITY_KEYS = ("severity", "level", "lvl", "labels.severity")
_TIME_KEYS = ("timestamp", "ts", "at", "time")
_SEVERITY_ALIASES = {
    "warn": "warning",
    "err": "error",
    "crit": "critical",
    "fatal": "critical",
    "page": "critical",
    "information": "info",
}
_VALID_SEVERITIES = {s.value for s in Severity}


def _to_text(value: Any) -> str | None:
    if value is MISSING or value is None or isinstance(value, dict | list):
        return None
    return str(value)


def _extract(spec: Any, payload: dict[str, Any]) -> tuple[Any, FieldMappingSpec]:
    """Return the raw value (MISSING if none) and the spec (a bare string means {path})."""
    if isinstance(spec, str):
        spec = FieldMappingSpec(path=spec)
    if spec.const is not None:
        return spec.const, spec
    if spec.path is None:
        return MISSING, spec
    return get_path(payload, spec.path), spec


def _apply_value_map(text: str, spec: FieldMappingSpec) -> str:
    if not spec.value_map:
        return text
    lowered = {k.lower(): v for k, v in spec.value_map.items()}
    return lowered.get(text.lower(), text)


def _map_text(spec: Any, payload: dict[str, Any]) -> str | None:
    raw, spec = _extract(spec, payload)
    text = _to_text(raw)
    if text is None:
        return spec.default
    return _apply_value_map(text, spec)


def _parse_severity(text: str | None) -> Severity | None:
    if text is None:
        return None
    lowered = text.strip().lower()
    lowered = _SEVERITY_ALIASES.get(lowered, lowered)
    return Severity(lowered) if lowered in _VALID_SEVERITIES else None


def _map_severity(spec: Any, payload: dict[str, Any]) -> Severity | None:
    raw, spec = _extract(spec, payload)
    text = _to_text(raw)
    if text is not None:
        text = _apply_value_map(text, spec)
    return _parse_severity(text) or _parse_severity(spec.default)


def parse_timestamp(raw: Any, fmt: str | None) -> datetime | None:
    """Parse a timestamp; never raises. Without `fmt`, numbers are guessed as seconds or ms."""
    if raw is MISSING or raw is None or isinstance(raw, bool):
        return None
    try:
        if isinstance(raw, str) and fmt in (None, "iso8601"):
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                if fmt == "iso8601":
                    return None
            else:
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        if fmt == "iso8601":
            return None
        number = float(raw)
        if fmt == "epoch_ms" or (fmt is None and number > 1e11):
            return datetime.fromtimestamp(number / 1000, UTC)
        return datetime.fromtimestamp(number, UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _map_occurred_at(spec: Any, payload: dict[str, Any]) -> datetime | None:
    raw, spec = _extract(spec, payload)
    return parse_timestamp(raw, spec.format)


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = get_path(payload, key)
        if value is not MISSING and value is not None:
            return value
    return MISSING


def normalize_event(envelope: EventEnvelope, profile: SchemaProfile) -> NormalizedFields:
    """Apply `profile` to the raw payload. Never raises on bad data; missing values stay None."""
    payload = envelope.payload
    fields = profile.fields
    severity = _map_severity(fields.severity, payload) if fields.severity is not None else None
    occurred_at = (
        _map_occurred_at(fields.occurred_at, payload) if fields.occurred_at is not None else None
    )
    if profile.id == "generic":
        # Heuristics only fill what the explicit mappings left empty.
        if severity is None:
            severity = _parse_severity(_to_text(_first_present(payload, _SEVERITY_KEYS)))
        if occurred_at is None:
            occurred_at = parse_timestamp(_first_present(payload, _TIME_KEYS), None)
    return NormalizedFields(
        schema_profile_id=profile.id,
        type=_map_text(fields.type, payload) if fields.type is not None else None,
        source=_map_text(fields.source, payload) if fields.source is not None else None,
        severity=severity or Severity.warning,
        occurred_at=occurred_at,
        entity=_map_text(fields.entity, payload) if fields.entity is not None else None,
        fingerprint=compute_fingerprint(payload, profile.fingerprint),
        is_resolution=profile.resolution is not None and _matches(profile.resolution, payload),
    )
