"""Schema profiles precompiled once per config load, so per-event work allocates nothing new."""

from dataclasses import dataclass, field
from typing import Any

from alerting_contracts.config import FieldMappingSpec, SchemaProfile

from alerting_core.rules import CompiledCondition, compile_condition
from alerting_core.rules.field_paths import split_field_path


@dataclass(frozen=True, slots=True)
class CompiledMapping:
    """One field mapping: path segments or const, case-insensitive value_map, default."""

    segments: tuple[str, ...] | None
    const: str | None
    fmt: str | None
    value_map: dict[str, str]
    default: str | None


@dataclass(frozen=True, slots=True, eq=False)
class CompiledProfile:
    """A profile with compiled conditions, split paths and prepared mappings."""

    profile: SchemaProfile
    match: CompiledCondition
    resolution: CompiledCondition | None
    fingerprint_segments: tuple[tuple[str, ...], ...]
    mappings: dict[str, CompiledMapping] = field(default_factory=dict)  # only mapped fields


def _compile_mapping(spec: Any) -> CompiledMapping:
    if isinstance(spec, str):
        spec = FieldMappingSpec(path=spec)
    return CompiledMapping(
        segments=split_field_path(spec.path) if spec.path is not None else None,
        const=spec.const,
        fmt=spec.format,
        value_map={k.lower(): v for k, v in spec.value_map.items()},
        default=spec.default,
    )


def compile_profile(profile: SchemaProfile) -> CompiledProfile:
    """Compile conditions and mappings. Raises ValueError/TypeError for a malformed condition."""
    mappings = {
        name: _compile_mapping(spec)
        for name in ("type", "source", "severity", "occurred_at", "entity")
        if (spec := getattr(profile.fields, name)) is not None
    }
    return CompiledProfile(
        profile=profile,
        match=compile_condition(profile.match),
        resolution=compile_condition(profile.resolution) if profile.resolution else None,
        fingerprint_segments=tuple(split_field_path(p) for p in profile.fingerprint),
        mappings=mappings,
    )
