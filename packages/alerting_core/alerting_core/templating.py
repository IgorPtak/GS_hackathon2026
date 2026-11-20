"""`{{ path }}` templates rendered against an event context. Never raises on missing data."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from alerting_contracts.alerts import AlertField
from alerting_contracts.config import Presentation

from .rules.field_paths import MISSING, lookup_segments, split_field_path

_PLACEHOLDER = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")


@dataclass(frozen=True)
class RenderedText:
    """Rendered text plus placeholders whose field was absent (rendered as empty)."""

    text: str
    missing_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CompiledTemplate:
    """Literal chunks interleaved with placeholder paths: chunks[i] + path[i] + chunks[i+1]."""

    chunks: tuple[str, ...]
    paths: tuple[str, ...]
    segments: tuple[tuple[str, ...], ...]


@lru_cache(maxsize=2048)
def compile_template(template: str) -> CompiledTemplate:
    """Parse a template once; cached because rules reuse the same strings per event."""
    chunks: list[str] = []
    paths: list[str] = []
    position = 0
    for match in _PLACEHOLDER.finditer(template):
        chunks.append(template[position : match.start()])
        paths.append(match.group(1))
        position = match.end()
    chunks.append(template[position:])
    return CompiledTemplate(
        tuple(chunks), tuple(paths), tuple(split_field_path(path) for path in paths)
    )


def format_value(value: Any) -> str:
    """Text form of a value: integral floats as ints, dict/list as compact JSON."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, dict | list | tuple):
        try:
            return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def render_template(template: str, context: Mapping[str, Any]) -> RenderedText:
    """Fill placeholders from the context; missing ones become '' and are listed."""
    compiled = compile_template(template)
    if not compiled.paths:
        return RenderedText(template)
    parts: list[str] = [compiled.chunks[0]]
    missing: list[str] = []
    for index, segments in enumerate(compiled.segments):
        value = lookup_segments(context, segments)
        if value is MISSING:
            missing.append(compiled.paths[index])
        else:
            parts.append(format_value(value))
        parts.append(compiled.chunks[index + 1])
    return RenderedText("".join(parts), missing)


def render_presentation(
    presentation: Presentation, context: Mapping[str, Any]
) -> tuple[str, str, list[AlertField]]:
    """Render a rule's title and body and collect its `fields` values (None when missing)."""
    title = render_template(presentation.title, context).text
    body = render_template(presentation.body, context).text
    fields = []
    for path in presentation.fields:
        value = lookup_segments(context, split_field_path(path))
        fields.append(AlertField(path=path, value=None if value is MISSING else value))
    return title, body, fields
