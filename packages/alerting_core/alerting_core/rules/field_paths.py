"""Dot-path lookup over an event context (raw payload root + `normalized` + `alert`)."""

from __future__ import annotations

from collections import ChainMap
from collections.abc import Mapping
from typing import Any, Final


class _Missing:
    """Type of the MISSING sentinel; falsy and printable."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Final = _Missing()


def split_field_path(path: str) -> tuple[str, ...]:
    """Split `a.b.0.c` into segments; compiled conditions and templates call this once."""
    return tuple(path.split("."))


def lookup_segments(context: Any, segments: tuple[str, ...]) -> Any:
    """Walk pre-split segments. Numeric segments index lists. Returns MISSING when absent."""
    current = context
    for segment in segments:
        # EAFP: mapping access is the hot case and avoids slow ABC isinstance checks.
        try:
            current = current[segment]
        except KeyError:
            return MISSING
        except TypeError:
            if not isinstance(current, list | tuple):
                return MISSING
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return MISSING
    return current


def resolve_field_path(context: Any, path: str) -> tuple[bool, Any]:
    """Return `(found, value)` for a dot path; a present `null` is found with value None."""
    value = lookup_segments(context, split_field_path(path))
    if value is MISSING:
        return False, None
    return True, value


def build_context(
    payload: Mapping[str, Any],
    normalized: Mapping[str, Any],
    alert: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Layer `normalized` (and `alert`) over the raw payload without copying the payload.

    `normalized` and `alert` shadow same-named raw keys, which keeps `normalized.*` paths
    reliable whatever the producer sends.
    """
    layer: dict[str, Any] = {"normalized": normalized}
    if alert is not None:
        layer["alert"] = alert
    return ChainMap(layer, payload)  # type: ignore[arg-type]
