"""Pure per-event evaluation: profile -> normalized fields -> matching rules -> rendered alert text.

Everything compilable (profiles, rule conditions, templates) is compiled once per config snapshot
into a `RuleSet`; `evaluate_event` then does only lookups and comparisons. No I/O happens here.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from alerting_contracts.alerts import AlertField
from alerting_contracts.common import Severity
from alerting_contracts.config import Rule, SchemaProfile
from alerting_contracts.events import EventEnvelope, NormalizedFields
from alerting_core.config.registry import ConfigSnapshot
from alerting_core.events import ProfileMatcher, compute_fingerprint
from alerting_core.grouping import group_key
from alerting_core.logging import get_logger
from alerting_core.rules import build_context, compile_condition, index_rules_by_type
from alerting_core.rules.conditions import CompiledCondition
from alerting_core.templating import render_presentation

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CompiledRule:
    rule: Rule
    matches: CompiledCondition


@dataclass(frozen=True, slots=True)
class RuleMatch:
    """One rule that matched one event, with everything needed to create or fold an alert."""

    rule: Rule
    fingerprint: str
    severity: Severity
    title: str
    body: str
    fields: list[AlertField]
    group_key: str | None = None  # set for rules with `group`: they go to a group window


@dataclass(frozen=True, slots=True)
class EventOutcome:
    envelope: EventEnvelope
    profile: SchemaProfile
    normalized: NormalizedFields
    is_unknown_shape: bool
    matches: list[RuleMatch]


class RuleSet:
    """Profiles and enabled rules of one config snapshot, compiled for the hot path."""

    def __init__(self, snapshot: ConfigSnapshot) -> None:
        self.snapshot = snapshot
        profiles: Mapping[str, SchemaProfile] = snapshot.of_kind("schema_profile")
        self.profiles = ProfileMatcher(list(profiles.values()))
        compiled_rules: list[CompiledRule] = []
        rules: Mapping[str, Rule] = snapshot.of_kind("rule")
        for rule in rules.values():
            if not rule.enabled:
                continue
            try:
                compiled_rules.append(CompiledRule(rule, compile_condition(rule.when)))
            except (ValueError, TypeError) as error:
                # A rule that cannot compile is skipped, never fatal: other rules keep working.
                log.error("rule_skipped", extra={"rule_id": rule.id, "error": str(error)})
        # Only rules whose `normalized.type` constraint fits the event are evaluated per event.
        self.rules = index_rules_by_type((c, c.rule.when) for c in compiled_rules)
        self.rule_count = len(compiled_rules)
        log.info("rule_set_compiled", extra={"rules": self.rule_count})


def evaluate_event(rule_set: RuleSet, envelope: EventEnvelope) -> EventOutcome:
    """Normalize the event and return every enabled rule that matches it (never raises on data)."""
    payload = envelope.payload
    profile, is_unknown_shape = rule_set.profiles.select_with_flag(payload)
    normalized = rule_set.profiles.normalize(envelope, profile)
    context = build_context(payload, normalized.model_dump(mode="json"))
    matches: list[RuleMatch] = []
    # A resolution event closes alerts (A-18); it must never open a new one.
    if not normalized.is_resolution:
        for compiled in rule_set.rules.candidates(normalized.type):
            if compiled.matches(context):
                matches.append(_render_match(compiled.rule, normalized, context))
    return EventOutcome(envelope, profile, normalized, is_unknown_shape, matches)


def _render_match(
    rule: Rule, normalized: NormalizedFields, context: Mapping[str, Any]
) -> RuleMatch:
    fingerprint = (
        compute_fingerprint(context, rule.dedup.fingerprint)
        if rule.dedup.fingerprint
        else normalized.fingerprint
    )
    title, body, fields = render_presentation(rule.present, context)
    return RuleMatch(
        rule=rule,
        fingerprint=fingerprint,
        severity=rule.severity or normalized.severity,
        title=title,
        body=body,
        fields=fields,
        group_key=group_key(rule, context) if rule.group is not None else None,
    )
