"""Payload shape: the set of key paths, used to group unknown-schema samples."""

import hashlib
from collections.abc import Mapping
from typing import Any


def _collect(value: Any, prefix: str, out: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            out.add(path)
            _collect(child, path, out)
    elif isinstance(value, list):
        for child in value:
            _collect(child, f"{prefix}[]", out)


def key_paths(payload: Mapping[str, Any]) -> list[str]:
    """Sorted unique key paths; list elements collapse to `[]` (e.g. `alerts[].labels.job`)."""
    out: set[str] = set()
    _collect(payload, "", out)
    return sorted(out)


def shape_hash(payload: Mapping[str, Any]) -> str:
    """sha256 hex of the sorted key paths; equal for payloads with the same shape."""
    return hashlib.sha256("\n".join(key_paths(payload)).encode()).hexdigest()
