"""Group windows, pure part: group keys, buffered event summaries and the summary alert.

Different events of one rule that share the `group.by` values within `group.window` become ONE
group summary alert (CLAUDE.md decision 5; dedup is separate). The processor buffers
`GroupEvent`s in Redis and its flusher calls `summarize_group`; the rule preview (A-17) calls
the same functions on in-memory buffers, so both produce identical alerts.
"""

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from alerting_contracts.alerts import Alert, AlertField, GroupMember
from alerting_contracts.common import SEVERITY_ORDER, Severity
from alerting_contracts.config import Rule
from pydantic import BaseModel, ConfigDict

from .ids import derived_uuid7
from .rules import MISSING
from .rules.field_paths import lookup_segments, split_field_path
from .templating import format_value

# Joins group.by values; a unit separator cannot occur in readable config values.
_KEY_SEPARATOR = "␟"


class GroupEvent(BaseModel):
    """One matched event waiting in `group-buffer:*` (stored as JSON)."""

    model_config = ConfigDict(extra="ignore")

    fingerprint: str
    title: str
    body: str = ""
    severity: Severity
    fields: list[AlertField] = []
    received_at: datetime
    sent_at: datetime | None = None
    source_id: str
    schema_profile_id: str
    source: str | None = None
    payload: dict[str, Any]


def group_key(rule: Rule, context: Mapping[str, Any]) -> str:
    """Readable key from the rule's `group.by` values (missing values become empty)."""
    if rule.group is None:
        raise ValueError(f"rule {rule.id} has no group policy")
    values = []
    for path in rule.group.by:
        value = lookup_segments(context, split_field_path(path))
        values.append("" if value is MISSING else format_value(value))
    return _KEY_SEPARATOR.join(values)


def group_member(rule_id: str, key: str) -> str:
    """`<rule_id>:<group_key>`, the `group-deadlines` member (rule ids never contain ':')."""
    return f"{rule_id}:{key}"


def split_group_member(member: str) -> tuple[str, str]:
    rule_id, _, key = member.partition(":")
    return rule_id, key


def group_alert_id(flush_key: str, deadline_ms: int) -> str:
    """Deterministic id per flushed window, so a re-flush after a crash cannot duplicate."""
    return derived_uuid7(flush_key, deadline_ms)


def summarize_group(
    rule: Rule, key: str, events: Sequence[GroupEvent], alert_id: str, now: datetime
) -> Alert:
    """One group summary alert: members aggregated by fingerprint, count = all events."""
    if not events:
        raise ValueError("a group summary needs at least one event")
    ordered = sorted(events, key=lambda event: event.received_at)
    members: dict[str, GroupMember] = {}
    for event in ordered:
        current = members.get(event.fingerprint)
        members[event.fingerprint] = GroupMember(
            fingerprint=event.fingerprint,
            title=event.title,
            count=(current.count if current else 0) + 1,
            last_seen=event.received_at,
        )
    first, last = ordered[0], ordered[-1]
    severity = max((event.severity for event in ordered), key=SEVERITY_ORDER.__getitem__)
    label = key.replace(_KEY_SEPARATOR, " / ") or "(no value)"
    return Alert(
        id=alert_id,
        rule_id=rule.id,
        team=rule.team,
        schema_profile_id=last.schema_profile_id,
        source_id=last.source_id,
        fingerprint=hashlib.sha256(f"{rule.id}:{key}".encode()).hexdigest(),
        group_key=key,
        is_group_summary=True,
        group_members=sorted(members.values(), key=lambda m: (-m.count, m.fingerprint)),
        severity=severity,
        title=f"{label}: {len(ordered)} events ({len(members)} distinct) — {first.title}",
        body=first.body,
        fields=last.fields,
        color=rule.present.color,
        count=len(ordered),
        first_seen=first.received_at,
        last_seen=last.received_at,
        runbook_id=rule.runbook,
        last_event=last.payload,
        updated_at=now,
    )
