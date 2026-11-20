"""LLM-first schema-profile proposal (B-21) with a deterministic heuristic fallback.

The LLM output is a proposal: it is validated as `SchemaProfile`, every mapped dot path must exist
in the sample event and the profile must match the sample. Anything else returns the heuristic
proposal, so the endpoint never fails because of the LLM.
"""

import json
import re
from collections.abc import Collection
from pathlib import Path
from typing import Any

from alerting_contracts.config import (
    ConditionAll,
    ConditionLeaf,
    ConditionNot,
    FieldMappingSpec,
    SchemaProfile,
)
from alerting_contracts.proposals import SchemaProfileProposal
from alerting_core.events.compiled import compile_profile
from alerting_core.llm import LlmClient, LlmError, redact_secrets
from alerting_core.logging import get_logger
from alerting_core.rules.field_paths import resolve_field_path
from pydantic import BaseModel, ValidationError

from .schema_proposal import propose_profile_heuristic

log = get_logger(__name__)

PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages/alerting_core/alerting_core/llm/prompts/schema_profile.md"
)
_NORMALIZED_FIELDS = ("type", "source", "severity", "occurred_at", "entity")


class SchemaProfileAnswer(BaseModel):
    """LLM answer: a draft profile plus reviewer notes."""

    profile: SchemaProfile
    notes: list[str] = []


def _leaf_fields(condition: Any) -> list[ConditionLeaf]:
    """All leaves of a condition tree (the `not` child is exposed as `not_`)."""
    if isinstance(condition, ConditionLeaf):
        return [condition]
    if isinstance(condition, ConditionNot):
        return _leaf_fields(condition.not_)
    children = condition.all if isinstance(condition, ConditionAll) else condition.any
    return [leaf for child in children for leaf in _leaf_fields(child)]


def _exists(sample: dict[str, Any], path: str) -> bool:
    return resolve_field_path(sample, path)[0]


def _clean_profile(
    profile: SchemaProfile, sample: dict[str, Any], notes: list[str]
) -> SchemaProfile | None:
    """Drop mappings whose path is absent from the sample; None when the profile is unusable."""
    fields = profile.fields.model_dump(exclude_none=True)
    for name in _NORMALIZED_FIELDS:
        spec = getattr(profile.fields, name)
        path = spec if isinstance(spec, str) else spec.path if spec is not None else None
        if path is not None and not _exists(sample, path):
            fields.pop(name, None)
            notes.append(f"Dropped {name} mapping: path {path!r} does not exist in the sample.")
        elif isinstance(spec, FieldMappingSpec) and spec.path is None and spec.const is None:
            fields.pop(name, None)
    for leaf in _leaf_fields(profile.match):
        absent_ok = leaf.op == "exists" and leaf.value is False
        if not absent_ok and not _exists(sample, leaf.field):
            log.warning("schema_llm_rejected", extra={"reason": f"match path {leaf.field!r}"})
            return None
    fingerprint = [p for p in profile.fingerprint if _exists(sample, p)]
    if not fingerprint:
        return None
    return profile.model_copy(
        update={
            "fields": type(profile.fields).model_validate(fields),
            "fingerprint": fingerprint,
            "resolution": None,
        }
    )


def _unique_id(wanted: str | None, proposed: str, existing: Collection[str]) -> str:
    base = wanted or proposed
    candidate = base
    suffix = 2
    while candidate in existing and wanted is None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _build_prompt(
    sample: dict[str, Any],
    heuristic: SchemaProfileProposal,
    profile_id: str | None,
    existing: Collection[str],
) -> str:
    # Redacted here as well as inside LlmClient.generate: the sample is the only untrusted input.
    sample_json = redact_secrets(json.dumps(sample, indent=2, sort_keys=True))
    return (
        f"Sample event:\n{sample_json}\n\n"
        f"Normalized fields available: {', '.join(_NORMALIZED_FIELDS)}\n"
        f"Requested profile id: {profile_id or '(none, choose one)'}\n"
        f"Existing profile ids: {', '.join(sorted(existing)) or '(none)'}\n\n"
        "Heuristic proposal to improve on:\n"
        f"{json.dumps(heuristic.profile.model_dump(mode='json', exclude_none=True), indent=2)}\n"
    )


async def _ask_llm(
    client: LlmClient,
    sample: dict[str, Any],
    heuristic: SchemaProfileProposal,
    profile_id: str | None,
    existing: Collection[str],
) -> SchemaProfileProposal | None:
    system = PROMPT_PATH.read_text(encoding="utf-8")
    try:
        answer = await client.generate(
            _build_prompt(sample, heuristic, profile_id, existing),
            SchemaProfileAnswer,
            system=system,
        )
    except LlmError as error:
        log.warning("schema_llm_fallback", extra={"reason": type(error).__name__})
        return None
    assert isinstance(answer, SchemaProfileAnswer)
    notes = list(answer.notes)
    profile = _clean_profile(answer.profile, sample, notes)
    if profile is None:
        log.warning("schema_llm_fallback", extra={"reason": "semantic validation failed"})
        return None
    profile = profile.model_copy(
        update={"id": _unique_id(profile_id, profile.id, existing), "priority": 10}
    )
    try:
        profile = SchemaProfile.model_validate(profile.model_dump(mode="json"))
        matches = compile_profile(profile).match(sample)
    except (ValidationError, ValueError, TypeError, re.error) as error:
        log.warning("schema_llm_fallback", extra={"reason": f"invalid profile: {error}"})
        return None
    if not matches:
        log.warning("schema_llm_fallback", extra={"reason": "profile does not match the sample"})
        return None
    return SchemaProfileProposal(
        profile=profile, generated_by="llm", model=client.model, notes=notes
    )


async def propose_profile(
    sample: dict[str, Any],
    profile_id: str | None,
    client: LlmClient | None,
    existing_ids: Collection[str] = (),
) -> SchemaProfileProposal:
    """LLM proposal when possible, otherwise the heuristic one; raises only like the heuristic."""
    heuristic = propose_profile_heuristic(sample, profile_id)
    if client is None:
        log.info("schema_llm_fallback", extra={"reason": "llm disabled"})
        return heuristic
    proposal = await _ask_llm(client, sample, heuristic, profile_id, existing_ids)
    return proposal or heuristic
