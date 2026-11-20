"""Extract NormalizedFields from a raw event with a schema profile."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from alerting_contracts.common import Severity
from alerting_contracts.config import SchemaProfile
from alerting_contracts.events import EventEnvelope, NormalizedFields

from alerting_core.rules.field_paths import MISSING, lookup_segments, split_field_path

from .compiled import CompiledMapping, CompiledProfile, compile_profile
from .fingerprint import fingerprint_values

_SEVERITY_KEYS = tuple(split_field_path(k) for k in ("severity", "level", "lvl", "labels.severity"))
_TIME_KEYS = tuple(split_field_path(k) for k in ("timestamp", "ts", "at", "time"))
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


def _raw(mapping: CompiledMapping, payload: Mapping[str, Any]) -> Any:
    if mapping.const is not None:
        return mapping.const
    if mapping.segments is None:
        return MISSING
    return lookup_segments(payload, mapping.segments)


def _mapped_text(mapping: CompiledMapping, payload: Mapping[str, Any]) -> str | None:
    text = _to_text(_raw(mapping, payload))
    if text is None:
        return mapping.default
    return mapping.value_map.get(text.lower(), text) if mapping.value_map else text


def _parse_severity(text: str | None) -> Severity | None:
    if text is None:
        return None
    lowered = text.strip().lower()
    lowered = _SEVERITY_ALIASES.get(lowered, lowered)
    return Severity(lowered) if lowered in _VALID_SEVERITIES else None


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


def _first_present(payload: Mapping[str, Any], keys: tuple[tuple[str, ...], ...]) -> Any:
    for segments in keys:
        value = lookup_segments(payload, segments)
        if value is not MISSING and value is not None:
            return value
    return MISSING


def normalize_compiled(envelope: EventEnvelope, compiled: CompiledProfile) -> NormalizedFields:
    """Apply a precompiled profile to the raw payload. Never raises on bad data."""
    payload = envelope.payload
    mappings = compiled.mappings
    severity: Severity | None = None
    occurred_at: datetime | None = None
    if (m := mappings.get("severity")) is not None:
        severity = _parse_severity(_mapped_text(m, payload)) or _parse_severity(m.default)
    if (m := mappings.get("occurred_at")) is not None:
        occurred_at = parse_timestamp(_raw(m, payload), m.fmt)
    if compiled.profile.id == "generic":
        # Heuristics only fill what the explicit mappings left empty.
        if severity is None:
            severity = _parse_severity(_to_text(_first_present(payload, _SEVERITY_KEYS)))
        if occurred_at is None:
            occurred_at = parse_timestamp(_first_present(payload, _TIME_KEYS), None)
    type_m, source_m, entity_m = (
        mappings.get("type"),
        mappings.get("source"),
        mappings.get("entity"),
    )
    return NormalizedFields(
        schema_profile_id=compiled.profile.id,
        type=_mapped_text(type_m, payload) if type_m else None,
        source=_mapped_text(source_m, payload) if source_m else None,
        severity=severity or Severity.warning,
        occurred_at=occurred_at,
        entity=_mapped_text(entity_m, payload) if entity_m else None,
        fingerprint=fingerprint_values(payload, compiled.fingerprint_segments),
        is_resolution=compiled.resolution is not None and compiled.resolution(payload),
    )


def normalize_event(envelope: EventEnvelope, profile: SchemaProfile) -> NormalizedFields:
    """Apply `profile` to the raw payload (compiles first; hot path: ProfileMatcher.normalize)."""
    return normalize_compiled(envelope, compile_profile(profile))
