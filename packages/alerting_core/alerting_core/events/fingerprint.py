"""Fingerprint: sha256 of the canonical JSON of the fingerprint field values."""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

import orjson

from alerting_core.rules.field_paths import MISSING, lookup_segments, split_field_path

_INT_MIN = -(2**63)
_INT_MAX = 2**64 - 1


def _canonical(value: Any) -> Any:
    """Make equal-meaning values serialize identically (25000000.0 is 25000000)."""
    if value is None or isinstance(value, str | bool):
        return value  # bool before int: True must never become 1
    if isinstance(value, float):
        if math.isfinite(value) and value == int(value):
            return _canonical(int(value))
        return value
    if isinstance(value, int):
        return value if _INT_MIN <= value <= _INT_MAX else str(value)
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]
    return str(value)


def fingerprint_values(payload: Mapping[str, Any], segments: Sequence[tuple[str, ...]]) -> str:
    """Hash values looked up with pre-split path segments (missing -> null). Never raises."""
    values = [None if (v := lookup_segments(payload, s)) is MISSING else v for s in segments]
    try:
        canonical = orjson.dumps(_canonical(values), option=orjson.OPT_SORT_KEYS)
    except (TypeError, ValueError, RecursionError):
        canonical = json.dumps(values, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def compute_fingerprint(payload: Mapping[str, Any], paths: Sequence[str]) -> str:
    """Hash the values at `paths` in order (missing -> null). Rules may pass their own paths."""
    return fingerprint_values(payload, [split_field_path(p) for p in paths])
