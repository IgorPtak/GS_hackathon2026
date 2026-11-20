"""Fingerprint: sha256 of the canonical JSON of the fingerprint field values."""

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

import orjson

from ._paths import MISSING, get_path


def compute_fingerprint(payload: Mapping[str, Any], paths: Sequence[str]) -> str:
    """Hash the values at `paths` in order (missing -> null). Rules may pass their own paths."""
    values = [None if (v := get_path(payload, p)) is MISSING else v for p in paths]
    return hashlib.sha256(orjson.dumps(values, option=orjson.OPT_SORT_KEYS)).hexdigest()
