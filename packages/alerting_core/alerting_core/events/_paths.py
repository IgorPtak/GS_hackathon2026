"""Dot-path lookup in raw payloads (numeric segments index into lists)."""

from functools import lru_cache
from typing import Any

MISSING: Any = object()


@lru_cache(maxsize=4096)
def _split(path: str) -> tuple[str, ...]:
    return tuple(path.split("."))


def get_path(payload: Any, path: str) -> Any:
    """Return the value at `path`, or MISSING when any segment is absent."""
    current = payload
    for segment in _split(path):
        if isinstance(current, dict):
            current = current.get(segment, MISSING)
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            current = current[index] if index < len(current) else MISSING
        else:
            return MISSING
        if current is MISSING:
            return MISSING
    return current
